"""The M3 hard gate (docs/BUILD_SPEC.md "Gate M3"): >= 1,000 randomized
crash-injection trials per effect class (A-D), zero duplicate effects,
zero blind class-D retries, zero incorrect VERIFIED_SUCCESS, zero
unverified step advancement, deterministic journal reconstruction.

Also proves the gate can fail: a naive "reconcile then retry on failure"
policy for class D must be caught as duplicate/unsafe retry by the same oracle.
"""

from __future__ import annotations

import pytest

from computer_agent import recovery
from computer_agent.recovery import Next
from computer_agent.state import Phase
from computer_agent.types import EffectClass

from . import m3_campaign
from .fixtures.fixture_c import CRASH_BOUNDARIES

PER_CLASS = 1044  # 12 crash boundaries x 87 seeds, per class

# Every seed that ever violated an M3 safety property is pinned here permanently.
REGRESSION_SEEDS: tuple[tuple[str, str, int], ...] = ()

SAFETY = ("duplicate_effects", "lost_effects", "incorrect_verified_success", "unsafe_retries",
          "unresolved_auto_advanced", "dispatch_without_durable_start", "stale_or_wrong_target_dispatches",
          "reconstruction_failures", "action_id_instability")


def test_m3_gate():
    r = m3_campaign.run_campaign(PER_CLASS, base_seed=0)
    assert all(n >= 1000 for n in r.by_class.values()) and len(r.by_class) == 4
    for metric in SAFETY:
        assert r.totals[metric] == 0, (metric, r.failing[:5])
    assert not r.failing
    assert r.crash_fired >= 0.97 * r.total_trials  # unfired = run halted (review) before that boundary
    assert r.second_crash_fired > 500
    # the recovery paths are genuinely exercised, not vacuously safe
    assert r.totals["reconciled"] > 500
    assert r.totals["outcome_unknown"] > 300
    assert r.totals["safe_key_retries"] > 0 and r.totals["idempotent_reapplies"] > 0
    assert all(set(v) <= {"COMPLETED", "NEEDS_REVIEW", "BLOCKED"} for v in r.by_final.values())


@pytest.mark.parametrize("cls,boundary,seed", REGRESSION_SEEDS)
def test_regression_seed(cls, boundary, seed):
    assert m3_campaign.run_trial(EffectClass(cls), boundary, seed).safety_failures == 0


def test_oracle_detects_blind_class_d_retry(monkeypatch):
    real_restart, real_after = recovery.on_restart, recovery.after_verification

    def naive_restart(a):
        if a.phase in (Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED):
            return Next.RECONCILE  # "just check and retry" for every class, D included
        return real_restart(a)

    def naive_after(cls, outcome, dispatches):
        nxt = real_after(cls, outcome, dispatches)
        return Next.RETRY if nxt in (Next.NEEDS_REVIEW, Next.OUTCOME_UNKNOWN) and dispatches < 2 else nxt

    monkeypatch.setattr(recovery, "on_restart", naive_restart)
    monkeypatch.setattr(recovery, "after_verification", naive_after)
    bad = [m3_campaign.run_trial(EffectClass.NON_IDEMPOTENT_UNQUERYABLE, b, s)
           for s, b in enumerate(CRASH_BOUNDARIES * 3)]
    assert sum(t.duplicate_effects + t.unsafe_retries for t in bad) > 0
