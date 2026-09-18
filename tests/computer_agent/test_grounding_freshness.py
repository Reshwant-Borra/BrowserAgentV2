"""Unit tests for computer_agent.grounding (resolve/freshness_check), plus
one deterministic sanity check per Fixture A scenario class, plus the
permanent regression corpus for every seed the M1 adversarial campaign
found to misbehave (docs/IMPLEMENTATION_PLAN.md M1, task item 9).

Pure `resolve`/`freshness_check` tests build `Observation`s directly, with
no Fixture A involved, to keep the resolution contract testable in
isolation from the harness that later exercises it adversarially.
"""

from __future__ import annotations

import pytest

from computer_agent.grounding import freshness_check, resolve
from computer_agent.types import (
    ExecutionRef,
    Observation,
    ObservationVersion,
    ResolutionOutcome,
    TargetCandidate,
    TargetSpec,
)

from .campaign import run_trial
from .fixtures.scenarios import SCENARIO_NAMES


def _candidate(adapter_local_id: str, version: int, **overrides) -> TargetCandidate:
    ref = ExecutionRef(observation_version=ObservationVersion(version), adapter_local_id=adapter_local_id)
    defaults = dict(
        role="button",
        name="Submit",
        text="Submit",
        states={"enabled": True, "visible": True},
        container="panel",
    )
    defaults.update(overrides)
    return TargetCandidate(execution_ref=ref, **defaults)


def _observation(version: int, *candidates: TargetCandidate) -> Observation:
    return Observation(version=ObservationVersion(version), candidates=tuple(candidates))


# -- resolve(): unique / ambiguous / absent / unsupported --------------------------------


def test_resolve_unique_match_is_resolved():
    c = _candidate("h-1", 0)
    result = resolve(TargetSpec(role="button", name="Submit"), _observation(0, c))
    assert result.outcome is ResolutionOutcome.RESOLVED
    assert result.selected == c


def test_resolve_candidate_filtering_by_container_and_state():
    wrong_container = _candidate("h-1", 0, container="dialog")
    disabled = _candidate("h-2", 0, states={"enabled": False, "visible": True})
    match = _candidate("h-3", 0)
    obs = _observation(0, wrong_container, disabled, match)
    result = resolve(
        TargetSpec(role="button", name="Submit", container_hint="panel", state_constraints={"enabled": True}),
        obs,
    )
    assert result.outcome is ResolutionOutcome.RESOLVED
    assert result.selected == match


def test_resolve_text_hint_is_substring_match():
    c = _candidate("h-1", 0, text="Please Submit Now")
    result = resolve(TargetSpec(text_hint="Submit"), _observation(0, c))
    assert result.outcome is ResolutionOutcome.RESOLVED


def test_resolve_multiple_matches_without_discriminator_is_ambiguous():
    a = _candidate("h-1", 0, container="panel_a")
    b = _candidate("h-2", 0, container="panel_b")
    result = resolve(TargetSpec(role="button", name="Submit"), _observation(0, a, b))
    assert result.outcome is ResolutionOutcome.AMBIGUOUS
    assert result.selected is None
    assert list(result.candidates) == [a, b]


def test_resolve_never_guesses_a_candidate_on_ambiguity():
    a = _candidate("h-1", 0, container="panel_a")
    b = _candidate("h-2", 0, container="panel_b")
    result = resolve(TargetSpec(role="button", name="Submit"), _observation(0, a, b))
    assert result.selected is None


def test_resolve_ordinal_disambiguates_explicitly():
    a = _candidate("h-1", 0, container="panel_a")
    b = _candidate("h-2", 0, container="panel_b")
    result = resolve(TargetSpec(role="button", name="Submit", ordinal=1), _observation(0, a, b))
    assert result.outcome is ResolutionOutcome.RESOLVED
    assert result.selected == b


def test_resolve_out_of_range_ordinal_falls_back_to_ambiguous():
    a = _candidate("h-1", 0, container="panel_a")
    b = _candidate("h-2", 0, container="panel_b")
    result = resolve(TargetSpec(role="button", name="Submit", ordinal=5), _observation(0, a, b))
    assert result.outcome is ResolutionOutcome.AMBIGUOUS


def test_resolve_no_match_is_absent():
    c = _candidate("h-1", 0, name="Cancel")
    result = resolve(TargetSpec(role="button", name="Submit"), _observation(0, c))
    assert result.outcome is ResolutionOutcome.ABSENT
    assert result.selected is None


def test_resolve_empty_spec_is_unsupported():
    c = _candidate("h-1", 0)
    result = resolve(TargetSpec(), _observation(0, c))
    assert result.outcome is ResolutionOutcome.UNSUPPORTED


def test_resolve_expected_version_mismatch_is_stale_without_matching():
    c = _candidate("h-1", 5)
    result = resolve(
        TargetSpec(role="button", name="Submit"),
        _observation(5, c),
        expected_version=ObservationVersion(4),
    )
    assert result.outcome is ResolutionOutcome.STALE
    assert result.selected is None


def test_resolve_expected_version_match_still_resolves_normally():
    c = _candidate("h-1", 5)
    result = resolve(
        TargetSpec(role="button", name="Submit"),
        _observation(5, c),
        expected_version=ObservationVersion(5),
    )
    assert result.outcome is ResolutionOutcome.RESOLVED


# -- ephemeral ExecutionRef / observation-version behavior -----------------------------


def test_execution_ref_is_not_reused_across_different_observation_versions():
    c0 = _candidate("h-1", 0)
    c1 = _candidate("h-1", 1)  # same adapter_local_id, different observation version
    assert c0.execution_ref != c1.execution_ref


# -- freshness_check(): unchanged / re-resolved / abstain -------------------------------


def test_freshness_check_unchanged_reuses_same_ref():
    c = _candidate("h-1", 0)
    spec = TargetSpec(role="button", name="Submit")
    fresh_observation = _observation(0, c)  # same version as c's ref: nothing changed
    result = freshness_check(c.execution_ref, spec, fresh_observation)
    assert result.safe_to_dispatch is True
    assert result.execution_ref == c.execution_ref
    assert result.reason == "unchanged since resolution"


def test_freshness_check_re_resolves_after_harmless_mutation():
    stale_ref = _candidate("h-1", 0).execution_ref
    spec = TargetSpec(role="button", name="Submit")
    moved = _candidate("h-2", 1)  # different observation version -> ref is stale
    result = freshness_check(stale_ref, spec, _observation(1, moved))
    assert result.safe_to_dispatch is True
    assert result.execution_ref == moved.execution_ref
    assert result.execution_ref != stale_ref
    assert result.reason == "re-resolved after mutation"


def test_freshness_check_abstains_on_ambiguity_introduced_by_mutation():
    stale_ref = _candidate("h-1", 0).execution_ref
    spec = TargetSpec(role="button", name="Submit")
    a = _candidate("h-2", 1, container="panel_a")
    b = _candidate("h-3", 1, container="panel_b")
    result = freshness_check(stale_ref, spec, _observation(1, a, b))
    assert result.safe_to_dispatch is False
    assert result.execution_ref is None
    assert result.outcome is ResolutionOutcome.AMBIGUOUS


def test_freshness_check_abstains_on_absence_introduced_by_mutation():
    stale_ref = _candidate("h-1", 0).execution_ref
    spec = TargetSpec(role="button", name="Submit")
    result = freshness_check(stale_ref, spec, _observation(1))  # target removed
    assert result.safe_to_dispatch is False
    assert result.execution_ref is None
    assert result.outcome is ResolutionOutcome.ABSENT


# -- one deterministic sanity check per Fixture A scenario class ------------------------


@pytest.mark.parametrize("scenario_name", SCENARIO_NAMES)
def test_scenario_never_produces_wrong_or_stale_dispatch(scenario_name):
    record = run_trial(scenario_name, seed=1)
    assert record.t0_consistent, (
        f"scenario {scenario_name!r} did not reach its own expected T0 outcome "
        f"(got {record.resolution_outcome_t0}, expected {record.expected_t0_outcome}) -- scenario "
        f"construction bug, not a grounding-contract failure"
    )
    assert record.safety not in ("WRONG_TARGET_DISPATCH", "STALE_TARGET_DISPATCH")
    assert record.oracle_agrees_with_resolver_t1


# -- permanent regression corpus ---------------------------------------------------------
# Every (scenario, seed) the adversarial campaign ever found unsafe goes here, forever.
# Empty means no failure has been found (yet) -- see computer_agent/M1_GROUNDING_REPORT.md.

REGRESSION_SEEDS: tuple[tuple[str, int], ...] = ()


@pytest.mark.parametrize("scenario_name,seed", REGRESSION_SEEDS)
def test_known_regression_seed_stays_safe(scenario_name, seed):
    record = run_trial(scenario_name, seed)
    assert record.safety not in ("WRONG_TARGET_DISPATCH", "STALE_TARGET_DISPATCH")
