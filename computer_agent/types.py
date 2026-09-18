"""Core value types for the ComputerAgent grounding/freshness contract (M1).

See `docs/ARCHITECTURE.md` "Target resolution contract" and
`docs/DECISIONS.md` D-017/D-018. `TargetSpec` is semantic intent only --
never a backend handle or coordinate. `TargetCandidate` is evidence from
exactly one `Observation`. `ExecutionRef` is opaque, adapter-local, and
valid only for the `ObservationVersion` that produced it. There is no
durable `UniversalElement`: nothing here is meant to identify an element
across two different observations.

These types are deliberately inert data. Resolution/freshness logic lives
in `computer_agent.grounding`; nothing in this module makes a decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ResolutionOutcome(str, Enum):
    """Authoritative resolution outcomes (docs/BUILD_SPEC.md, docs/IMPLEMENTATION_PLAN.md M1)."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    ABSENT = "ABSENT"  # a.k.a. NOT_FOUND in docs/ARCHITECTURE.md's diagram
    STALE = "STALE"
    UNSUPPORTED = "UNSUPPORTED"


class DispatchSafety(str, Enum):
    """Harness-side safety classification of one trial's dispatch decision.

    No production code in M1 produces this -- it exists as shared
    observability vocabulary (docs/IMPLEMENTATION_PLAN.md M1's "Developer
    Console contract") for the fixture campaign, and later for a real
    controller.
    """

    CORRECT_TARGET_DISPATCH = "CORRECT_TARGET_DISPATCH"
    WRONG_TARGET_DISPATCH = "WRONG_TARGET_DISPATCH"
    STALE_TARGET_DISPATCH = "STALE_TARGET_DISPATCH"
    ABSTAINED = "ABSTAINED"


@dataclass(frozen=True)
class ObservationVersion:
    """Identifies exactly one fresh observation. Never reused as durable identity."""

    sequence: int


@dataclass(frozen=True)
class TargetSpec:
    """Semantic intent only. Never stores a backend handle, node reference, or coordinate.

    `ordinal` disambiguates among otherwise-tied candidates, but only when
    explicitly supplied by the caller -- the resolver never invents an
    ordinal to avoid abstaining (docs/research overnight GROUNDING.md:
    "ordinal ... only when user/task semantics truly imply it").
    """

    role: str | None = None
    name: str | None = None
    text_hint: str | None = None
    container_hint: str | None = None
    state_constraints: Mapping[str, Any] = field(default_factory=dict)
    ordinal: int | None = None

    def is_expressible(self) -> bool:
        """False for a spec with no matching constraint at all -- nothing to resolve."""
        return bool(
            self.role or self.name or self.text_hint or self.container_hint or self.state_constraints
        )


@dataclass(frozen=True)
class ExecutionRef:
    """Opaque, adapter-local, observation-local reference.

    Not durable cross-observation identity. Valid only alongside the
    `ObservationVersion` it was produced against; a real adapter's
    `adapter_local_id` might be a DOM node handle, an AXUIElement, or a
    UIA element -- callers must never interpret it themselves.
    """

    observation_version: ObservationVersion
    adapter_local_id: str


@dataclass(frozen=True)
class TargetCandidate:
    """Observation-local evidence that one element may match a TargetSpec.

    `bounds` is carried for display/debugging only -- resolution never
    matches on geometry (docs/ARCHITECTURE.md: "use semantic constraints
    ... rather than arbitrary coordinates").
    """

    execution_ref: ExecutionRef
    role: str
    name: str
    text: str
    states: Mapping[str, Any]
    container: str | None
    bounds: tuple[int, int, int, int] | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    """A single fresh snapshot of the semantic surface, produced by an adapter."""

    version: ObservationVersion
    candidates: tuple[TargetCandidate, ...]


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of resolving a TargetSpec against one Observation."""

    outcome: ResolutionOutcome
    candidates: tuple[TargetCandidate, ...] = ()
    selected: TargetCandidate | None = None
    reason: str = ""


@dataclass(frozen=True)
class FreshnessResult:
    """Outcome of the pre-dispatch freshness check.

    `execution_ref` is the ref that is actually safe to dispatch now (it
    may be the original ref, if nothing changed, or a freshly re-resolved
    one) -- never the stale input ref when the world has moved on.
    """

    safe_to_dispatch: bool
    execution_ref: ExecutionRef | None
    outcome: ResolutionOutcome
    reason: str


@dataclass(frozen=True)
class CandidateSummary:
    """Display-safe projection of a TargetCandidate for a future Developer Console."""

    role: str
    name: str
    container: str | None
    states: Mapping[str, Any]


def summarize_candidate(candidate: TargetCandidate) -> CandidateSummary:
    return CandidateSummary(
        role=candidate.role,
        name=candidate.name,
        container=candidate.container,
        states=dict(candidate.states),
    )


@dataclass(frozen=True)
class GroundingTrace:
    """One resolve -> freshness -> dispatch/abstain trace, safe for observational display.

    Assembled *after* all decisions are made from already-computed
    results -- it never feeds back into resolution or freshness logic
    (docs/IMPLEMENTATION_PLAN.md M1 "Developer Console contract": UI
    concerns must not influence correctness logic).
    """

    target_spec: TargetSpec
    observation_version: ObservationVersion
    candidate_summaries: tuple[CandidateSummary, ...]
    resolution_outcome: ResolutionOutcome
    resolution_reason: str
    selected_summary: CandidateSummary | None
    freshness_safe: bool
    freshness_outcome: ResolutionOutcome
    freshness_reason: str
    dispatched: bool
    dispatch_safety: DispatchSafety | None = None
    scenario: str | None = None
    seed: int | None = None

    @classmethod
    def build(
        cls,
        *,
        spec: TargetSpec,
        observation: Observation,
        resolution: ResolutionResult,
        freshness: FreshnessResult,
        dispatched: bool,
        dispatch_safety: DispatchSafety | None = None,
        scenario: str | None = None,
        seed: int | None = None,
    ) -> "GroundingTrace":
        return cls(
            target_spec=spec,
            observation_version=observation.version,
            candidate_summaries=tuple(summarize_candidate(c) for c in resolution.candidates),
            resolution_outcome=resolution.outcome,
            resolution_reason=resolution.reason,
            selected_summary=summarize_candidate(resolution.selected) if resolution.selected else None,
            freshness_safe=freshness.safe_to_dispatch,
            freshness_outcome=freshness.outcome,
            freshness_reason=freshness.reason,
            dispatched=dispatched,
            dispatch_safety=dispatch_safety,
            scenario=scenario,
            seed=seed,
        )


class EffectClass(str, Enum):
    """Recovery class of an action's external effect (docs/DECISIONS.md D-020).

    Declared per action kind from measured/known capability -- never inferred
    from a model's belief. Recovery behavior depends on it (computer_agent.recovery).
    """

    IDEMPOTENCY_KEY = "A"  # service dedups on the logical action_id
    QUERYABLE = "B"  # effect can be looked up after the fact (by action_id reference)
    STATE_SET = "C"  # naturally idempotent "ensure X == Y"
    NON_IDEMPOTENT_UNQUERYABLE = "D"  # e.g. a send whose only evidence is transient
