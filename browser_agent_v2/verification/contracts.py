"""Typed contracts for the Verifier.

The Verifier answers exactly one question, deterministically:

    did the intended postcondition actually become true?

It never answers "probably", never retries, never consults a model, and never
accepts the BrowserKernel's word that a primitive returned without throwing.

Shape follows END_TO_END_SYSTEM_SPEC section 4.7 (`status` / `checks` /
`evidence` / `confidence`) and adds the two fields the result needs to be useful
in a trace: which verifier ran, and a stable machine-greppable reason.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


class VerificationStatus(str, enum.Enum):
    """The only three answers a Verifier may give."""

    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    AMBIGUOUS = "AMBIGUOUS"


class Reason(str, enum.Enum):
    """Stable reason codes.

    These exist so that a controller can branch on *why* verification failed
    without parsing prose, and so that regression tests can assert on the
    reason rather than on a message.
    """

    OK = "OK"

    # value / field
    VALUE_MISMATCH = "VALUE_MISMATCH"
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    FIELD_AMBIGUOUS = "FIELD_AMBIGUOUS"

    # navigation
    URL_MISMATCH = "URL_MISMATCH"

    # dom
    ELEMENT_MISSING = "ELEMENT_MISSING"
    ELEMENT_UNEXPECTEDLY_PRESENT = "ELEMENT_UNEXPECTEDLY_PRESENT"
    TEXT_MISSING = "TEXT_MISSING"
    TEXT_UNEXPECTEDLY_PRESENT = "TEXT_UNEXPECTEDLY_PRESENT"

    # pages
    PAGE_MISSING = "PAGE_MISSING"
    PAGE_UNEXPECTEDLY_PRESENT = "PAGE_UNEXPECTEDLY_PRESENT"
    PAGE_NOT_ACTIVE = "PAGE_NOT_ACTIVE"
    PAGE_WRONG_OPENER = "PAGE_WRONG_OPENER"

    # dialogs
    DIALOG_MISSING = "DIALOG_MISSING"
    DIALOG_MISMATCH = "DIALOG_MISMATCH"
    DIALOG_UNEXPECTEDLY_PRESENT = "DIALOG_UNEXPECTEDLY_PRESENT"

    # downloads
    DOWNLOAD_MISSING = "DOWNLOAD_MISSING"
    DOWNLOAD_MISMATCH = "DOWNLOAD_MISMATCH"
    DOWNLOAD_INCOMPLETE = "DOWNLOAD_INCOMPLETE"

    # consequential operations
    OPERATION_RECORDED = "OPERATION_RECORDED"
    OPERATION_NOT_RECORDED = "OPERATION_NOT_RECORDED"

    # evidence quality — these are the only routes to AMBIGUOUS
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    EVIDENCE_CONTRADICTORY = "EVIDENCE_CONTRADICTORY"

    # composition
    COMPOSITE_FAILED = "COMPOSITE_FAILED"


#: Reasons that legitimately produce AMBIGUOUS. Anything else must resolve to
#: SATISFIED or NOT_SATISFIED. This list is asserted in the test suite so that
#: AMBIGUOUS cannot quietly become a catch-all for bugs.
AMBIGUITY_REASONS = frozenset(
    {
        Reason.EVIDENCE_UNAVAILABLE,
        Reason.STALE_EVIDENCE,
        Reason.EVIDENCE_CONTRADICTORY,
        Reason.FIELD_AMBIGUOUS,
    }
)


@dataclass(frozen=True)
class Check:
    """One atomic comparison. Several may contribute to a single result."""

    name: str
    #: True / False, or None when the check could not be evaluated at all.
    passed: Optional[bool]
    expected: Any = None
    observed: Any = None
    detail: str = ""

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": _compact(self.expected),
            "observed": _compact(self.observed),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    reason: Reason
    #: Which postcondition evaluator produced this (the "verifier type").
    verifier_type: str
    checks: Sequence[Check] = field(default_factory=tuple)
    #: Compact provenance only. Never a whole observation — a result is stored
    #: for every action, and embedding page snapshots would make the trace
    #: unreadable and enormous.
    evidence: Mapping[str, Any] = field(default_factory=dict)
    confidence: str = "deterministic"

    @property
    def satisfied(self) -> bool:
        return self.status is VerificationStatus.SATISFIED

    @property
    def ambiguous(self) -> bool:
        return self.status is VerificationStatus.AMBIGUOUS

    def to_json(self) -> dict:
        return {
            "status": self.status.value,
            "reason": self.reason.value,
            "verifier_type": self.verifier_type,
            "checks": [c.to_json() for c in self.checks],
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
        }

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.status.value}({self.reason.value}) via {self.verifier_type}"


def satisfied(verifier_type: str, checks: Sequence[Check], **evidence) -> VerificationResult:
    return VerificationResult(
        VerificationStatus.SATISFIED, Reason.OK, verifier_type, tuple(checks), evidence
    )


def not_satisfied(
    verifier_type: str, reason: Reason, checks: Sequence[Check], **evidence
) -> VerificationResult:
    if reason in AMBIGUITY_REASONS:
        raise ValueError(f"{reason} is an ambiguity reason; it cannot mean NOT_SATISFIED")
    return VerificationResult(
        VerificationStatus.NOT_SATISFIED, reason, verifier_type, tuple(checks), evidence
    )


def ambiguous(
    verifier_type: str, reason: Reason, checks: Sequence[Check], **evidence
) -> VerificationResult:
    if reason not in AMBIGUITY_REASONS:
        raise ValueError(
            f"{reason} is not an ambiguity reason. AMBIGUOUS is for insufficient or "
            "contradictory evidence, not for a condition that is definitively false."
        )
    return VerificationResult(
        VerificationStatus.AMBIGUOUS, reason, verifier_type, tuple(checks), evidence
    )


def _compact(value: Any, limit: int = 240) -> Any:
    """Keep evidence small enough to store on every step."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<+{len(value) - limit} chars>"
    if isinstance(value, (list, tuple)) and len(value) > 12:
        return list(value[:12]) + [f"...<+{len(value) - 12} more>"]
    return value
