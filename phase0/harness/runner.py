"""Reusable experiment runner.

Pipeline (see phase0/README.md for the full description):

    capture_before -> execute_action -> capture_after
        -> verify_postcondition -> classify_interference -> persist_result

The action and its verifier are kept logically separate: `ActionSpec.execute`
performs the action and may return an opaque result, but only
`ActionSpec.verify` gets to decide whether the postcondition actually
held, by inspecting independently observable state. A successful
`execute()` call (no exception) never by itself counts as success.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from phase0.harness import observers_macos
from phase0.harness.classification import classify_interference
from phase0.harness.environment import (
    current_platform,
    get_cheap_hardware_metadata,
    get_os_version_measurement,
    utc_now_iso,
)
from phase0.harness.observers_macos import MacObserver
from phase0.schemas.evidence import (
    SCHEMA_VERSION,
    ActionMechanism,
    ActionOutcome,
    EvidenceReference,
    ExperimentObservation,
    Measurement,
)

VerifyResult = Tuple[Optional[bool], Measurement]


@dataclass
class ActionSpec:
    """Describes one trial's action, independent of the runner."""

    action_type: str
    action_mechanism: ActionMechanism
    expected_postcondition: str
    execute: Callable[[], Any]
    verify: Callable[[Any], VerifyResult]
    target_application: Measurement = field(default_factory=lambda: Measurement.unavailable("not specified"))
    target_process: Measurement = field(default_factory=lambda: Measurement.unavailable("not specified"))
    target_window: Measurement = field(default_factory=lambda: Measurement.unavailable("not specified"))
    supported: bool = True
    unsupported_reason: Optional[str] = None
    focus_pid: Optional[int] = None
    evidence: list = field(default_factory=list)  # list[EvidenceReference]


class ExperimentRunner:
    """Runs `ActionSpec`s through the measurement pipeline and persists
    machine-readable `ExperimentObservation` results."""

    def __init__(self, experiment_id: str, run_id: str, observer: Optional[MacObserver] = None):
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.observer = observer or MacObserver()

    def run_trial(self, trial_id: str, spec: ActionSpec) -> ExperimentObservation:
        before = self.observer.snapshot(pid=spec.focus_pid)

        action_outcome = ActionOutcome.SUCCESS
        error: Optional[dict] = None
        result: Any = None

        start = time.monotonic()
        if not spec.supported:
            # Do not attempt an operation known to be unsupported; that
            # would risk an uncontrolled side effect. Record it directly.
            latency_ms = 0.0
        else:
            try:
                result = spec.execute()
            except Exception as exc:  # noqa: BLE001 - trial isolation is intentional
                action_outcome = ActionOutcome.ERROR
                error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            latency_ms = (time.monotonic() - start) * 1000

        after = self.observer.snapshot(pid=spec.focus_pid)

        observed_postcondition: Measurement
        postcondition_success: Optional[bool]

        if not spec.supported:
            observed_postcondition = Measurement.unavailable(
                spec.unsupported_reason or "operation not supported on this platform/target"
            )
            postcondition_success = None
        elif action_outcome == ActionOutcome.ERROR:
            observed_postcondition = Measurement.unavailable(
                "action raised an exception before postcondition could be observed"
            )
            postcondition_success = None
        else:
            try:
                postcondition_success, observed_postcondition = spec.verify(result)
                if postcondition_success is False:
                    action_outcome = ActionOutcome.FAILURE
            except Exception as exc:  # noqa: BLE001
                action_outcome = ActionOutcome.ERROR
                error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
                observed_postcondition = Measurement.unavailable(f"verifier raised: {exc}")
                postcondition_success = None

        c_moved = observers_macos.cursor_moved(before.cursor, after.cursor)
        fg_changed = observers_macos.foreground_changed(before.foreground_app, after.foreground_app)
        f_changed = observers_macos.focus_changed(
            before.focused_window, after.focused_window, before.focused_element, after.focused_element
        )

        classification = classify_interference(
            cursor_moved=c_moved,
            foreground_changed=fg_changed,
            focus_changed=f_changed,
            action_outcome=action_outcome,
            supported=spec.supported,
        )

        return ExperimentObservation(
            schema_version=SCHEMA_VERSION,
            experiment_id=self.experiment_id,
            run_id=self.run_id,
            trial_id=trial_id,
            timestamp=utc_now_iso(),
            platform=current_platform(),
            os_version=get_os_version_measurement(),
            hardware=get_cheap_hardware_metadata(),
            action_type=spec.action_type,
            action_mechanism=spec.action_mechanism,
            target_application=spec.target_application,
            target_process=spec.target_process,
            target_window=spec.target_window,
            foreground_app_before=before.foreground_app,
            foreground_app_after=after.foreground_app,
            focused_window_before=before.focused_window,
            focused_window_after=after.focused_window,
            focused_element_before=before.focused_element,
            focused_element_after=after.focused_element,
            cursor_before=before.cursor,
            cursor_after=after.cursor,
            cursor_moved=c_moved,
            foreground_changed=fg_changed,
            focus_changed=f_changed,
            action_latency_ms=latency_ms,
            expected_postcondition=spec.expected_postcondition,
            observed_postcondition=observed_postcondition,
            postcondition_success=postcondition_success,
            action_outcome=action_outcome,
            error=error,
            classification=classification,
            evidence=list(spec.evidence),
        )
