"""The M1 hard gate (docs/BUILD_SPEC.md "Gate M1"): >= 1,000 deterministic
seeded trials, zero wrong-target dispatch, zero stale-target dispatch.

Runs on every test invocation (no I/O, pure in-memory, sub-second) so any
future change to computer_agent/grounding.py is re-validated against the
full adversarial distribution automatically -- this is the "run the
campaign again after any correctness fix" requirement, permanently wired
into CI rather than a one-off manual step.
"""

from __future__ import annotations

from .campaign import run_campaign


def test_m1_gate_zero_wrong_or_stale_dispatch_across_1500_trials():
    report = run_campaign(n=1500, base_seed=0)

    assert report.total_trials >= 1000

    assert report.wrong_target_dispatch_count == 0, (
        f"wrong-target dispatch seeds: {report.wrong_target_dispatch_seeds}"
    )
    assert report.stale_target_dispatch_count == 0, (
        f"stale-target dispatch seeds: {report.stale_target_dispatch_seeds}"
    )
    assert report.t0_inconsistent_count == 0, (
        f"scenario construction produced an unexpected T0 outcome: {report.t0_inconsistent_seeds}"
    )
    assert report.oracle_disagreement_count == 0, (
        f"resolver disagreed with the independent ground-truth oracle: {report.oracle_disagreement_seeds}"
    )
