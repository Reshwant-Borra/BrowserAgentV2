"""Recovery decision table + real-process crash tests (M3).

The subprocess tests SIGKILL an actual controller process at each durable
boundary -- not a cooperative exception -- and restart a new process that
knows only the SQLite journal and the external world file.
"""

from __future__ import annotations

import pytest

from computer_agent.recovery import MAX_DISPATCHES, Next, after_verification, on_restart
from computer_agent.state import ActionState, Phase
from computer_agent.types import EffectClass
from computer_agent.verification import VerificationOutcome as V

from . import m3_campaign
from .fixtures.fixture_c import CRASH_BOUNDARIES

A, B, C, D = EffectClass


def _action(cls, phase):
    return ActionState("s1.a1", "s1", "k", {}, cls, {}, phase=phase)


@pytest.mark.parametrize("cls", list(EffectClass))
def test_restart_table(cls):
    assert on_restart(_action(cls, Phase.INTENT_PERSISTED)) == Next.RESUME_DISPATCH  # provably not dispatched
    assert on_restart(_action(cls, Phase.RETRY_PENDING)) == Next.RESUME_DISPATCH
    for phase in (Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED):
        assert on_restart(_action(cls, phase)) == (Next.OUTCOME_UNKNOWN if cls == D else Next.RECONCILE)
    assert on_restart(_action(cls, Phase.OBSERVED_AFTER)) == Next.JUDGE_PERSISTED
    assert on_restart(_action(cls, Phase.VERIFIED)) == Next.SETTLE_PERSISTED
    assert on_restart(_action(cls, Phase.COMMITTED)) == Next.COMPLETE_STEP


def test_after_verification_table():
    for cls in EffectClass:
        assert after_verification(cls, V.VERIFIED_SUCCESS, 1) == Next.COMMIT
        for bad in (V.PARTIAL_SUCCESS, V.UNEXPECTED_SIDE_EFFECT):
            assert after_verification(cls, bad, 1) == Next.NEEDS_REVIEW
        assert after_verification(cls, V.VERIFIED_FAILURE, MAX_DISPATCHES) == Next.NEEDS_REVIEW
    assert after_verification(D, V.VERIFIED_FAILURE, 1) == Next.NEEDS_REVIEW  # never auto-retried
    assert after_verification(D, V.INCONCLUSIVE, 1) == Next.OUTCOME_UNKNOWN
    assert after_verification(B, V.INCONCLUSIVE, 1) == Next.OUTCOME_UNKNOWN
    assert after_verification(A, V.INCONCLUSIVE, 1) == Next.RETRY  # same idempotency key
    assert after_verification(C, V.INCONCLUSIVE, 1) == Next.RETRY  # idempotent state-set
    for cls in (A, B, C):
        assert after_verification(cls, V.VERIFIED_FAILURE, 1) == Next.RETRY


@pytest.mark.parametrize("cls", list(EffectClass))
@pytest.mark.parametrize("boundary", CRASH_BOUNDARIES)
def test_sigkill_at_every_boundary(tmp_path, cls, boundary):
    seed = 7000 + CRASH_BOUNDARIES.index(boundary)
    t = m3_campaign.run_trial_subprocess(cls, boundary, seed, tmp_path)
    assert t.safety_failures == 0, t.notes
    assert t.final in ("COMPLETED", "NEEDS_REVIEW", "BLOCKED")
    # same seed in-process reaches the same authoritative outcome (crash mechanism does not matter)
    inproc = m3_campaign.run_trial(cls, boundary, seed)
    assert (inproc.final, inproc.step_status, len(inproc.crashes)) == (t.final, t.step_status, len(t.crashes))
    if t.crashes and cls == D and boundary in ("after_dispatch_started", "during_dispatch_before_effect",
                                                "after_effect_before_return", "after_dispatch_returned",
                                                "after_observation_before_persist"):
        assert t.step_status["s1"] == "NEEDS_REVIEW" and t.outcome_unknown >= 1
