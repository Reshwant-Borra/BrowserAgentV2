"""Typed, versioned evidence schema for Phase 0 capability experiments.

This is the single machine-readable contract every experiment (browser
non-interference, macOS AX, future Windows UIA, etc.) must emit results
through. It is intentionally generic: it is not coupled to Chrome or to
macOS AX specifically, so the same schema can describe a Playwright
action, an AXUIElement action, or (later) a Windows UIA action.

Design notes:
- Every "observed" field is wrapped in `Measurement`, which distinguishes
  a real value from "unavailable" (with an explicit reason). Nothing here
  fabricates a value when a permission or platform capability is missing.
- Evidence artifacts (screenshots, DOM snapshots, AX snapshots, logs) are
  stored as *references* (paths), never embedded as blobs.
- `from_dict` performs structural validation and raises
  `SchemaValidationError` on malformed input rather than silently
  accepting partial/garbage records.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

SCHEMA_VERSION = "1.0.0"


class SchemaValidationError(ValueError):
    """Raised when a result record does not conform to the evidence schema."""


class Platform(str, Enum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


class ActionMechanism(str, Enum):
    """The execution mechanism used to perform an action.

    This mirrors the InteractionRouter's adapter set (see
    docs/ARCHITECTURE.md) but only lists mechanisms Phase 0 actually
    exercises. It is deliberately not coupled to a single browser/OS.
    """

    PLAYWRIGHT_SEMANTIC = "playwright_semantic"
    MACOS_AX_READ = "macos_ax_read"
    MACOS_AX_MUTATE = "macos_ax_mutate"
    PHYSICAL_INPUT_INJECTION = "physical_input_injection"
    UNKNOWN = "unknown"


class ActionOutcome(str, Enum):
    """Whether the action call itself completed, independent of the
    postcondition. An action can SUCCEED and still fail verification.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class InterferenceClassification(str, Enum):
    """Background-safety classification for a single measured trial.

    This is a *measured* classification, never inferred from model
    confidence or from action success alone (see docs/DECISIONS.md D-011
    and docs/ARCHITECTURE.md's background-safety model). It answers a
    narrower question than the route-level capability labels
    (BACKGROUND_PROVEN / BACKGROUND_BEST_EFFORT / FOREGROUND_REQUIRED)
    used later by the InteractionRouter: this classification is the
    per-trial observation that evidence for those labels is built from.
    """

    BACKGROUND_SAFE = "BACKGROUND_SAFE"
    CURSOR_INTERFERENCE = "CURSOR_INTERFERENCE"
    FOREGROUND_INTERFERENCE = "FOREGROUND_INTERFERENCE"
    FOCUS_INTERFERENCE = "FOCUS_INTERFERENCE"
    MULTIPLE_INTERFERENCE = "MULTIPLE_INTERFERENCE"
    UNSUPPORTED = "UNSUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


_MISSING = object()


@dataclass
class Measurement:
    """A single observed value that may be unavailable.

    `available=False` must always carry a `reason`. Callers must never
    set `available=True` with a fabricated/guessed `value`.
    """

    available: bool
    value: Any = None
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.available and not self.reason:
            raise SchemaValidationError(
                "Measurement marked unavailable must include a reason"
            )

    @classmethod
    def of(cls, value: Any) -> "Measurement":
        return cls(available=True, value=value)

    @classmethod
    def unavailable(cls, reason: str) -> "Measurement":
        return cls(available=False, value=None, reason=reason)

    def to_dict(self) -> dict:
        return {"available": self.available, "value": self.value, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Any) -> "Measurement":
        if not isinstance(data, dict):
            raise SchemaValidationError(f"Measurement must be an object, got {type(data)!r}")
        if "available" not in data:
            raise SchemaValidationError("Measurement missing required field 'available'")
        try:
            return cls(
                available=bool(data["available"]),
                value=data.get("value"),
                reason=data.get("reason"),
            )
        except SchemaValidationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise SchemaValidationError(f"Malformed Measurement: {exc}") from exc


@dataclass
class EvidenceReference:
    """A pointer to a large artifact stored outside the JSON result."""

    kind: str  # "screenshot" | "dom_snapshot" | "accessibility_snapshot" | "log" | ...
    path: str
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "description": self.description}

    @classmethod
    def from_dict(cls, data: Any) -> "EvidenceReference":
        if not isinstance(data, dict):
            raise SchemaValidationError(f"EvidenceReference must be an object, got {type(data)!r}")
        for required in ("kind", "path"):
            if required not in data:
                raise SchemaValidationError(f"EvidenceReference missing required field '{required}'")
        return cls(kind=data["kind"], path=data["path"], description=data.get("description"))


def _enum_from(enum_cls, raw: Any, field_name: str):
    try:
        return enum_cls(raw)
    except ValueError as exc:
        valid = ", ".join(m.value for m in enum_cls)
        raise SchemaValidationError(
            f"Invalid value {raw!r} for field {field_name!r}; expected one of: {valid}"
        ) from exc


@dataclass
class ExperimentObservation:
    """A single trial's full evidence record.

    One instance = one attempted action + its independently observed
    before/after system state + its verified postcondition + its
    measured interference classification.
    """

    schema_version: str
    experiment_id: str
    run_id: str
    trial_id: str
    timestamp: str  # ISO-8601 UTC

    platform: Platform
    os_version: Measurement
    hardware: dict

    action_type: str
    action_mechanism: ActionMechanism
    target_application: Measurement
    target_process: Measurement
    target_window: Measurement

    foreground_app_before: Measurement
    foreground_app_after: Measurement
    focused_window_before: Measurement
    focused_window_after: Measurement
    focused_element_before: Measurement
    focused_element_after: Measurement
    cursor_before: Measurement
    cursor_after: Measurement

    cursor_moved: Optional[bool]
    foreground_changed: Optional[bool]
    focus_changed: Optional[bool]

    action_latency_ms: Optional[float]

    expected_postcondition: str
    observed_postcondition: Measurement
    postcondition_success: Optional[bool]

    action_outcome: ActionOutcome
    error: Optional[dict] = None

    classification: InterferenceClassification = InterferenceClassification.INCONCLUSIVE
    evidence: list = field(default_factory=list)  # list[EvidenceReference]

    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "trial_id": self.trial_id,
            "timestamp": self.timestamp,
            "platform": self.platform.value,
            "os_version": self.os_version.to_dict(),
            "hardware": self.hardware,
            "action_type": self.action_type,
            "action_mechanism": self.action_mechanism.value,
            "target_application": self.target_application.to_dict(),
            "target_process": self.target_process.to_dict(),
            "target_window": self.target_window.to_dict(),
            "foreground_app_before": self.foreground_app_before.to_dict(),
            "foreground_app_after": self.foreground_app_after.to_dict(),
            "focused_window_before": self.focused_window_before.to_dict(),
            "focused_window_after": self.focused_window_after.to_dict(),
            "focused_element_before": self.focused_element_before.to_dict(),
            "focused_element_after": self.focused_element_after.to_dict(),
            "cursor_before": self.cursor_before.to_dict(),
            "cursor_after": self.cursor_after.to_dict(),
            "cursor_moved": self.cursor_moved,
            "foreground_changed": self.foreground_changed,
            "focus_changed": self.focus_changed,
            "action_latency_ms": self.action_latency_ms,
            "expected_postcondition": self.expected_postcondition,
            "observed_postcondition": self.observed_postcondition.to_dict(),
            "postcondition_success": self.postcondition_success,
            "action_outcome": self.action_outcome.value,
            "error": self.error,
            "classification": self.classification.value,
            "evidence": [e.to_dict() for e in self.evidence],
        }
        return d

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentObservation":
        if not isinstance(data, dict):
            raise SchemaValidationError(f"ExperimentObservation must be an object, got {type(data)!r}")

        required_fields = {
            f.name
            for f in dataclasses.fields(cls)
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
        }
        missing = required_fields - data.keys()
        if missing:
            raise SchemaValidationError(f"Missing required field(s): {sorted(missing)}")

        if data.get("schema_version") != SCHEMA_VERSION:
            raise SchemaValidationError(
                f"Unsupported schema_version {data.get('schema_version')!r}; "
                f"expected {SCHEMA_VERSION!r}"
            )

        try:
            measurement_fields = [
                "os_version",
                "target_application",
                "target_process",
                "target_window",
                "foreground_app_before",
                "foreground_app_after",
                "focused_window_before",
                "focused_window_after",
                "focused_element_before",
                "focused_element_after",
                "cursor_before",
                "cursor_after",
                "observed_postcondition",
            ]
            measurements = {mf: Measurement.from_dict(data[mf]) for mf in measurement_fields}

            evidence_raw = data.get("evidence", [])
            if not isinstance(evidence_raw, list):
                raise SchemaValidationError("'evidence' must be a list")
            evidence = [EvidenceReference.from_dict(e) for e in evidence_raw]

            return cls(
                schema_version=data["schema_version"],
                experiment_id=data["experiment_id"],
                run_id=data["run_id"],
                trial_id=data["trial_id"],
                timestamp=data["timestamp"],
                platform=_enum_from(Platform, data["platform"], "platform"),
                os_version=measurements["os_version"],
                hardware=data.get("hardware") or {},
                action_type=data["action_type"],
                action_mechanism=_enum_from(ActionMechanism, data["action_mechanism"], "action_mechanism"),
                target_application=measurements["target_application"],
                target_process=measurements["target_process"],
                target_window=measurements["target_window"],
                foreground_app_before=measurements["foreground_app_before"],
                foreground_app_after=measurements["foreground_app_after"],
                focused_window_before=measurements["focused_window_before"],
                focused_window_after=measurements["focused_window_after"],
                focused_element_before=measurements["focused_element_before"],
                focused_element_after=measurements["focused_element_after"],
                cursor_before=measurements["cursor_before"],
                cursor_after=measurements["cursor_after"],
                cursor_moved=data.get("cursor_moved"),
                foreground_changed=data.get("foreground_changed"),
                focus_changed=data.get("focus_changed"),
                action_latency_ms=data.get("action_latency_ms"),
                expected_postcondition=data["expected_postcondition"],
                observed_postcondition=measurements["observed_postcondition"],
                postcondition_success=data.get("postcondition_success"),
                action_outcome=_enum_from(ActionOutcome, data["action_outcome"], "action_outcome"),
                error=data.get("error"),
                classification=_enum_from(InterferenceClassification, data["classification"], "classification"),
                evidence=evidence,
            )
        except SchemaValidationError:
            raise
        except KeyError as exc:
            raise SchemaValidationError(f"Missing required field: {exc}") from exc
        except Exception as exc:
            raise SchemaValidationError(f"Malformed ExperimentObservation: {exc}") from exc
