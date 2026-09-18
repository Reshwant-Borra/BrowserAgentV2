"""M1 adversarial campaign: drives Fixture A scenarios through
resolve -> mutate -> freshness_check -> dispatch/abstain, and grades the
outcome against an *independently written* ground-truth oracle.

Grading deliberately does not call `computer_agent.grounding.resolve` to
decide what "correct" means -- reusing the function under test as its own
oracle would let a resolver bug and the grading agree with each other and
hide a wrong-target dispatch. `_ground_truth` is a second, independent
implementation of the same matching semantics, written directly against
Fixture A's hidden `true_id` ground truth.

This module is test/harness code, not production (`computer_agent/`
contains only `types.py`/`grounding.py` for M1 -- no controller, no
InteractionRouter).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from computer_agent.grounding import freshness_check, resolve
from computer_agent.types import DispatchSafety, ResolutionOutcome, TargetSpec

from .fixtures.fixture_a import FixtureElement, MutableUIGraph
from .fixtures.scenarios import SCENARIO_NAMES, build_trial


def _spec_matches_element(spec: TargetSpec, element: FixtureElement) -> bool:
    if spec.role is not None and element.role != spec.role:
        return False
    if spec.name is not None and element.name != spec.name:
        return False
    if spec.text_hint is not None and spec.text_hint not in element.text:
        return False
    if spec.container_hint is not None and element.container != spec.container_hint:
        return False
    state = {"enabled": element.enabled, "visible": element.visible}
    for key, expected in spec.state_constraints.items():
        if state.get(key) != expected:
            return False
    return True


def _ground_truth(elements: list[FixtureElement], spec: TargetSpec) -> tuple[ResolutionOutcome, str | None]:
    """Independent oracle: what a correct resolution against `elements` ought
    to produce. Never calls `computer_agent.grounding.resolve`."""
    if not (spec.role or spec.name or spec.text_hint or spec.container_hint or spec.state_constraints):
        return ResolutionOutcome.UNSUPPORTED, None

    matches = [e for e in elements if _spec_matches_element(spec, e)]

    if not matches:
        return ResolutionOutcome.ABSENT, None
    if len(matches) == 1:
        return ResolutionOutcome.RESOLVED, matches[0].true_id
    if spec.ordinal is not None and 0 <= spec.ordinal < len(matches):
        return ResolutionOutcome.RESOLVED, matches[spec.ordinal].true_id
    return ResolutionOutcome.AMBIGUOUS, None


@dataclass
class TrialRecord:
    seed: int
    scenario: str
    target_spec: dict[str, Any]
    observation_version_t0: int
    observation_version_t1: int
    candidate_count_t0: int
    resolution_outcome_t0: str
    expected_t0_outcome: str
    t0_consistent: bool
    selected_true_id_t0: str | None
    freshness_safe: bool
    freshness_outcome: str
    freshness_reason: str
    dispatched: bool
    dispatch_touched_true_id: str | None
    dispatch_was_stale_ref: bool
    expected_outcome_t1: str
    expected_true_id_t1: str | None
    oracle_agrees_with_resolver_t1: bool
    identity_shifted: bool
    safety: str


def run_trial(scenario_name: str, seed: int) -> TrialRecord:
    setup = build_trial(scenario_name, seed)
    graph: MutableUIGraph = setup.graph
    spec = setup.spec

    observation_0 = graph.observe()
    resolution_0 = resolve(spec, observation_0)
    t0_consistent = resolution_0.outcome == setup.expected_t0_outcome
    selected_true_id_t0 = None
    if resolution_0.selected is not None:
        touch = graph.dispatch(resolution_0.selected.execution_ref)
        selected_true_id_t0 = touch.touched_true_id

    setup.mutate()
    observation_1 = graph.observe()

    dispatched = False
    dispatch_touched_true_id: str | None = None
    dispatch_was_stale_ref = False
    freshness_safe = False
    freshness_outcome = ResolutionOutcome.ABSENT
    freshness_reason = "resolution was not RESOLVED at T0; controller must not attempt dispatch"

    if resolution_0.outcome == ResolutionOutcome.RESOLVED:
        assert resolution_0.selected is not None
        freshness = freshness_check(resolution_0.selected.execution_ref, spec, observation_1)
        freshness_safe = freshness.safe_to_dispatch
        freshness_outcome = freshness.outcome
        freshness_reason = freshness.reason
        if freshness.safe_to_dispatch:
            assert freshness.execution_ref is not None
            attempt = graph.dispatch(freshness.execution_ref)
            dispatched = True
            dispatch_touched_true_id = attempt.touched_true_id
            dispatch_was_stale_ref = attempt.is_stale

    # Independent grading: resolver's own fresh look at T1, for a resolver-
    # correctness signal distinct from dispatch safety.
    resolver_t1 = resolve(spec, observation_1)
    expected_outcome_t1, expected_true_id_t1 = _ground_truth(graph.elements_snapshot(), spec)
    resolver_selected_true_id_t1 = None
    if resolver_t1.selected is not None:
        peek = graph.dispatch(resolver_t1.selected.execution_ref)
        resolver_selected_true_id_t1 = peek.touched_true_id
    oracle_agrees_with_resolver_t1 = (resolver_t1.outcome == expected_outcome_t1) and (
        resolver_selected_true_id_t1 == expected_true_id_t1
    )

    if not dispatched:
        safety = DispatchSafety.ABSTAINED
    elif dispatch_was_stale_ref:
        safety = DispatchSafety.STALE_TARGET_DISPATCH
    elif expected_outcome_t1 != ResolutionOutcome.RESOLVED or dispatch_touched_true_id != expected_true_id_t1:
        safety = DispatchSafety.WRONG_TARGET_DISPATCH
    else:
        safety = DispatchSafety.CORRECT_TARGET_DISPATCH

    identity_shifted = bool(
        dispatched
        and selected_true_id_t0 is not None
        and dispatch_touched_true_id is not None
        and selected_true_id_t0 != dispatch_touched_true_id
    )

    return TrialRecord(
        seed=seed,
        scenario=scenario_name,
        target_spec={
            "role": spec.role,
            "name": spec.name,
            "text_hint": spec.text_hint,
            "container_hint": spec.container_hint,
            "state_constraints": dict(spec.state_constraints),
            "ordinal": spec.ordinal,
        },
        observation_version_t0=observation_0.version.sequence,
        observation_version_t1=observation_1.version.sequence,
        candidate_count_t0=len(observation_0.candidates),
        resolution_outcome_t0=resolution_0.outcome.value,
        expected_t0_outcome=setup.expected_t0_outcome.value,
        t0_consistent=t0_consistent,
        selected_true_id_t0=selected_true_id_t0,
        freshness_safe=freshness_safe,
        freshness_outcome=freshness_outcome.value,
        freshness_reason=freshness_reason,
        dispatched=dispatched,
        dispatch_touched_true_id=dispatch_touched_true_id,
        dispatch_was_stale_ref=dispatch_was_stale_ref,
        expected_outcome_t1=expected_outcome_t1.value,
        expected_true_id_t1=expected_true_id_t1,
        oracle_agrees_with_resolver_t1=oracle_agrees_with_resolver_t1,
        identity_shifted=identity_shifted,
        safety=safety.value,
    )


@dataclass
class CampaignReport:
    total_trials: int
    by_safety: dict[str, int]
    by_scenario_safety: dict[str, dict[str, int]]
    wrong_target_dispatch_seeds: list[tuple[str, int]]
    stale_target_dispatch_seeds: list[tuple[str, int]]
    t0_inconsistent_seeds: list[tuple[str, int]]
    oracle_disagreement_seeds: list[tuple[str, int]]

    @property
    def wrong_target_dispatch_count(self) -> int:
        return len(self.wrong_target_dispatch_seeds)

    @property
    def stale_target_dispatch_count(self) -> int:
        return len(self.stale_target_dispatch_seeds)

    @property
    def oracle_disagreement_count(self) -> int:
        return len(self.oracle_disagreement_seeds)

    @property
    def t0_inconsistent_count(self) -> int:
        return len(self.t0_inconsistent_seeds)


def run_campaign(n: int, base_seed: int = 0, evidence_dir: Path | None = None) -> CampaignReport:
    by_safety: dict[str, int] = {}
    by_scenario_safety: dict[str, dict[str, int]] = {name: {} for name in SCENARIO_NAMES}
    wrong_seeds: list[tuple[str, int]] = []
    stale_seeds: list[tuple[str, int]] = []
    t0_bad_seeds: list[tuple[str, int]] = []
    oracle_bad_seeds: list[tuple[str, int]] = []

    jsonl_fh = None
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        jsonl_fh = (evidence_dir / f"m1_campaign-seed{base_seed}-n{n}.jsonl").open("w")

    try:
        for i in range(n):
            scenario_name = SCENARIO_NAMES[i % len(SCENARIO_NAMES)]
            seed = base_seed + i
            record = run_trial(scenario_name, seed)

            by_safety[record.safety] = by_safety.get(record.safety, 0) + 1
            scenario_bucket = by_scenario_safety[scenario_name]
            scenario_bucket[record.safety] = scenario_bucket.get(record.safety, 0) + 1

            if record.safety == DispatchSafety.WRONG_TARGET_DISPATCH.value:
                wrong_seeds.append((scenario_name, seed))
            if record.safety == DispatchSafety.STALE_TARGET_DISPATCH.value:
                stale_seeds.append((scenario_name, seed))
            if not record.t0_consistent:
                t0_bad_seeds.append((scenario_name, seed))
            if not record.oracle_agrees_with_resolver_t1:
                oracle_bad_seeds.append((scenario_name, seed))

            if jsonl_fh is not None:
                jsonl_fh.write(json.dumps(asdict(record)) + "\n")
    finally:
        if jsonl_fh is not None:
            jsonl_fh.close()

    report = CampaignReport(
        total_trials=n,
        by_safety=by_safety,
        by_scenario_safety=by_scenario_safety,
        wrong_target_dispatch_seeds=wrong_seeds,
        stale_target_dispatch_seeds=stale_seeds,
        t0_inconsistent_seeds=t0_bad_seeds,
        oracle_disagreement_seeds=oracle_bad_seeds,
    )

    if evidence_dir is not None:
        summary_path = evidence_dir / f"m1_campaign-seed{base_seed}-n{n}-summary.json"
        summary_path.write_text(json.dumps(asdict(report), indent=2))

    return report
