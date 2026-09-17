"""Real-machine integration tests for the Playwright browser experiment.

These launch a real (headed) Chromium instance and read real cursor/
foreground-application state. Run explicitly with:

    pytest -m integration tests/phase0/integration/test_browser_experiment_live.py

Not part of the default unit suite (see pyproject.toml addopts).
"""

from __future__ import annotations

import pytest

from phase0.harness.observers_macos import is_macos, pyobjc_available
from phase0.harness.persistence import read_results

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_macos(), reason="observers currently only implemented for macOS"),
    pytest.mark.skipif(not pyobjc_available(), reason="pyobjc not importable"),
]


def test_browser_experiment_runs_and_produces_verified_trials(tmp_path):
    from phase0.experiments.browser_background.experiment import ExperimentBlocked, run_experiment

    try:
        results_path, summary = run_experiment(trial_count=5, output_dir=tmp_path, run_id="it-browser")
    except ExperimentBlocked as exc:
        pytest.skip(f"BLOCKED: {exc}")

    assert summary["trials"] == 5
    observations = list(read_results(results_path))
    assert len(observations) == 5

    # Every trial's postcondition must be independently verified, one
    # way or another (never silently skipped).
    assert all(obs.postcondition_success is not None for obs in observations)
    assert summary["verified_postconditions"] >= 1
