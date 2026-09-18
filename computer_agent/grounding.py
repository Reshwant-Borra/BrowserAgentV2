"""Target resolution and pre-dispatch freshness (M1).

See `docs/ARCHITECTURE.md` "Target resolution contract"/"Recovery
classification", `docs/DECISIONS.md` D-017/D-018,
`docs/IMPLEMENTATION_PLAN.md` M1.

Resolution matches a `TargetSpec` against `Observation`-local
`TargetCandidate`s using only semantic attributes -- never coordinates,
and never a durable cross-observation handle. Ambiguous or absent matches
abstain; they are never resolved by arbitrary tie-breaking. This module
has no notion of "dispatch" -- that boundary belongs to a later milestone
(the InteractionRouter) or, in M1, to the test-only Fixture A harness.
"""

from __future__ import annotations

from .types import (
    ExecutionRef,
    FreshnessResult,
    Observation,
    ObservationVersion,
    ResolutionOutcome,
    ResolutionResult,
    TargetCandidate,
    TargetSpec,
)


def _matches(candidate: TargetCandidate, spec: TargetSpec) -> bool:
    if spec.role is not None and candidate.role != spec.role:
        return False
    if spec.name is not None and candidate.name != spec.name:
        return False
    if spec.text_hint is not None and spec.text_hint not in candidate.text:
        return False
    if spec.container_hint is not None and candidate.container != spec.container_hint:
        return False
    for key, expected in spec.state_constraints.items():
        if candidate.states.get(key) != expected:
            return False
    return True


def resolve(
    spec: TargetSpec,
    observation: Observation,
    *,
    expected_version: ObservationVersion | None = None,
) -> ResolutionResult:
    """Resolve `spec` against one `Observation`.

    `expected_version`, when given, lets a caller (namely `freshness_check`)
    demand that `observation` be exactly the version it last resolved
    against. A mismatch is reported as STALE without attempting to match
    anything -- this models "the world moved on since you last looked"
    without comparing coordinates or reusing a handle across observations.
    """
    if expected_version is not None and observation.version != expected_version:
        return ResolutionResult(
            outcome=ResolutionOutcome.STALE,
            reason=(
                f"observation version {observation.version.sequence} does not match "
                f"expected {expected_version.sequence}"
            ),
        )

    if not spec.is_expressible():
        return ResolutionResult(
            outcome=ResolutionOutcome.UNSUPPORTED,
            reason="TargetSpec has no matching constraint to resolve against",
        )

    matches = tuple(c for c in observation.candidates if _matches(c, spec))

    if not matches:
        return ResolutionResult(outcome=ResolutionOutcome.ABSENT, reason="no candidate matched TargetSpec")

    if len(matches) == 1:
        return ResolutionResult(outcome=ResolutionOutcome.RESOLVED, candidates=matches, selected=matches[0])

    if spec.ordinal is not None and 0 <= spec.ordinal < len(matches):
        return ResolutionResult(
            outcome=ResolutionOutcome.RESOLVED,
            candidates=matches,
            selected=matches[spec.ordinal],
            reason="disambiguated by explicit ordinal",
        )

    return ResolutionResult(
        outcome=ResolutionOutcome.AMBIGUOUS,
        candidates=matches,
        reason=f"{len(matches)} candidates matched TargetSpec without a safe discriminator",
    )


def freshness_check(
    ref: ExecutionRef,
    spec: TargetSpec,
    fresh_observation: Observation,
) -> FreshnessResult:
    """Immediately-before-dispatch freshness gate.

    Never trusts `ref` across a mutation. First checks whether anything
    has changed since `ref` was produced (cheap: an expected-version
    comparison via `resolve`); if the world moved on, re-resolves `spec`
    from scratch against `fresh_observation` and only proceeds if that
    re-resolution is itself unambiguous. Abstains rather than guessing on
    newly introduced ambiguity or absence.

    Adapter contract this relies on: `ObservationVersion` must change
    whenever anything happens that could make a previously-issued
    `ExecutionRef` unsafe to dispatch. Fixture A satisfies this by
    construction (every mutation bumps the version). A real adapter
    (Playwright/AX/UIA, M7) must define its own version/staleness signal
    with the same property -- this contract does not by itself prove that
    any specific real adapter's notion of "version" is trustworthy.
    """
    strict = resolve(spec, fresh_observation, expected_version=ref.observation_version)
    if strict.outcome == ResolutionOutcome.RESOLVED:
        return FreshnessResult(True, ref, ResolutionOutcome.RESOLVED, "unchanged since resolution")

    fresh = resolve(spec, fresh_observation)
    if fresh.outcome == ResolutionOutcome.RESOLVED:
        assert fresh.selected is not None
        return FreshnessResult(
            True,
            fresh.selected.execution_ref,
            ResolutionOutcome.RESOLVED,
            "re-resolved after mutation",
        )

    return FreshnessResult(False, None, fresh.outcome, fresh.reason)
