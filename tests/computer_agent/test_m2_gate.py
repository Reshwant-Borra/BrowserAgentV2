"""The M2 hard gate (docs/BUILD_SPEC.md "Gate M2"): >= 1,000 injected
deterministic Fixture B trials, ZERO verifier false successes.

Also proves the gate can fail: deliberately sabotaged verification (specs
stripped of invariants; a "verifier" that trusts the executor's claim)
must be caught by the same oracle. A gate that cannot fail proves nothing.
"""

from __future__ import annotations

import pytest

from computer_agent.verification import VerificationOutcome as O, VerificationResult, VerificationSpec

from . import m2_campaign
from .fixtures import fixture_b
from .fixtures.fixture_b import CASE_NAMES

GATE_TRIALS = 2200  # 44 behavior x action-kind classes x 50 seeds

# Every seed that ever produced a false success is pinned here permanently.
REGRESSION_SEEDS: tuple[tuple[str, int], ...] = ()

# Deterministic behaviors whose designed verdict does not depend on the seed.
DESIGNED = {
    "correct": O.VERIFIED_SUCCESS,
    "noop_claims_success": O.VERIFIED_FAILURE,
    "wrong_object": O.UNEXPECTED_SIDE_EFFECT,
    "collateral": O.UNEXPECTED_SIDE_EFFECT,
    "claims_failure_but_applied": O.VERIFIED_SUCCESS,
    "ambiguous_result": O.INCONCLUSIVE,
    "precondition_satisfied": O.VERIFIED_SUCCESS,
}


def test_m2_gate_zero_false_success():
    report = m2_campaign.run_campaign(GATE_TRIALS, base_seed=0)
    assert report.total_trials >= 1000
    assert report.false_success_count == 0, f"false-success seeds: {report.false_success_seeds}"
    assert set(report.by_case_verdict) == set(CASE_NAMES)
    assert all(sum(v.values()) == GATE_TRIALS // len(CASE_NAMES) for v in report.by_case_verdict.values())
    # every outcome in the vocabulary is actually exercised
    assert set(report.by_verdict) == {o.value for o in O}
    assert report.executor_lies > 0 and report.executor_lies == report.executor_lies_caught


@pytest.mark.parametrize("case", CASE_NAMES)
def test_designed_verdicts(case):
    behavior = case.split(":")[0]
    for seed in range(5):
        t = m2_campaign.run_trial(case, seed)
        assert not t.false_success
        if behavior in DESIGNED:
            assert t.verdict == DESIGNED[behavior].value, (case, seed, t.reason)


def test_partial_and_duplicate_classification():
    assert m2_campaign.run_trial("partial:update_fields", 1).verdict == O.PARTIAL_SUCCESS.value
    assert m2_campaign.run_trial("duplicate:update_fields", 1).verdict == O.VERIFIED_SUCCESS.value  # idempotent
    for kind in ("increment", "create_record", "send_message"):
        assert m2_campaign.run_trial(f"duplicate:{kind}", 1).verdict == O.UNEXPECTED_SIDE_EFFECT.value


@pytest.mark.parametrize("case,seed", REGRESSION_SEEDS)
def test_regression_seed(case, seed):
    assert not m2_campaign.run_trial(case, seed).false_success


def test_oracle_detects_invariant_free_specs(monkeypatch):
    real = fixture_b.spec_for
    monkeypatch.setattr(m2_campaign, "spec_for", lambda i: VerificationSpec(success=real(i).success))
    assert m2_campaign.run_campaign(440).false_success_count > 0


def test_oracle_detects_claim_trusting_verifier(monkeypatch):
    def trusting_verify(spec, before, observe, max_observations):
        return VerificationResult(O.VERIFIED_SUCCESS, "executor said ok"), []

    monkeypatch.setattr(m2_campaign, "verify", trusting_verify)
    assert m2_campaign.run_campaign(440).false_success_count > 0
