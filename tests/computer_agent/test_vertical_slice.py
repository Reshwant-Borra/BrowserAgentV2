"""Combined M1 -> M2 -> M3 vertical-slice scenarios through the real
controller: TargetSpec -> resolve -> (UI mutates) -> freshness -> intent
journal -> dispatch -> (deceptive executor) -> independent verification ->
(crash) -> restart -> reconcile -> final authoritative state."""

from __future__ import annotations

import pytest

from . import m3_campaign
from .fixtures.fixture_c import COMBINED_SCENARIOS

# scenario -> (final task state, step-1 status, step-1 dispatch calls, extra journal events required)
EXPECT = {
    "stale_target_before_dispatch": ("BLOCKED", "BLOCKED", 0, {"FRESHNESS_FAILED", "ACTION_ABANDONED"}),
    "target_replaced_same_semantics": ("COMPLETED", "COMPLETED", 1, {"FRESHNESS_PASSED"}),
    "duplicate_target_after_reobservation": ("BLOCKED", "BLOCKED", 0, {"FRESHNESS_FAILED"}),
    "target_removed_before_dispatch": ("BLOCKED", "BLOCKED", 0, {"FRESHNESS_FAILED"}),
    "executor_lies_noop_class_a": ("COMPLETED", "COMPLETED", 2, {"ACTION_FAILED"}),
    "executor_lies_noop_class_d": ("NEEDS_REVIEW", "NEEDS_REVIEW", 1, {"NEEDS_REVIEW"}),
    "executor_reports_failure_but_applied": ("COMPLETED", "COMPLETED", 1, set()),
    "collateral_side_effect": ("NEEDS_REVIEW", "NEEDS_REVIEW", 1, {"NEEDS_REVIEW"}),
    "evidence_unavailable_class_a_key_retry": ("COMPLETED", "COMPLETED", 2, {"ACTION_FAILED"}),
    "evidence_unavailable_class_b": ("NEEDS_REVIEW", "NEEDS_REVIEW", 1, {"OUTCOME_UNKNOWN"}),
    "effect_then_crash_before_persist_class_b": ("COMPLETED", "COMPLETED", 1, {"OUTCOME_RECONCILED"}),
    "effect_then_crash_before_persist_class_a": ("COMPLETED", "COMPLETED", 1, {"OUTCOME_RECONCILED"}),
    "class_d_ambiguous_crash": ("NEEDS_REVIEW", "NEEDS_REVIEW", 1, {"OUTCOME_UNKNOWN", "RECOVERY_STARTED"}),
    "class_d_crash_after_observation_persisted": ("COMPLETED", "COMPLETED", 1, {"OUTCOME_RECONCILED"}),
    "verified_success_then_restart": ("COMPLETED", "COMPLETED", 1, {"STATE_RECONSTRUCTED"}),
    "lie_then_crash_mid_retry": ("COMPLETED", "COMPLETED", 2, {"ACTION_FAILED", "RECOVERY_STARTED"}),
    "stale_target_then_crash_after_intent": ("COMPLETED", "COMPLETED", 1, {"RECOVERY_STARTED"}),
    "policy_blocked_kind": ("BLOCKED", "BLOCKED", 0, {"POLICY_BLOCKED"}),
    "happy_path_no_crash": ("COMPLETED", "COMPLETED", 1, {"TASK_COMPLETED"}),
}


def test_every_combined_scenario_has_an_expectation():
    assert set(EXPECT) == set(COMBINED_SCENARIOS)


@pytest.mark.parametrize("name", COMBINED_SCENARIOS)
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_combined_scenario(name, seed):
    cap: dict = {}
    t = m3_campaign.run_combined(name, seed, capture=cap)
    final, s1, calls, required = EXPECT[name]
    types = {e.type.value for e in cap["events"]}
    assert t.safety_failures == 0, t.notes
    assert (t.final, t.step_status["s1"]) == (final, s1)
    assert cap["world"]["_truth"]["dispatch_calls"].get("s1.a1", 0) == calls
    assert required <= types, required - types
    # grounding: nothing ever dispatched at a stale or wrong target
    assert cap["world"]["_truth"]["stale_dispatches"] == cap["world"]["_truth"]["wrong_target_dispatches"] == 0
    # a step is COMPLETED only with an independently verified success on the journal
    for step_id, status in t.step_status.items():
        if status == "COMPLETED":
            assert cap["state"].actions[f"{step_id}.a1"].outcome == "VERIFIED_SUCCESS"
