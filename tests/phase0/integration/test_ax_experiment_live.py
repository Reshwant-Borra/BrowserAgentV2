"""Real-machine integration tests for the macOS AX experiment.

Launches the real AX fixture app and makes real AXUIElement calls. Run
explicitly with:

    pytest -m integration tests/phase0/integration/test_ax_experiment_live.py

Not part of the default unit suite (see pyproject.toml addopts). If the
Accessibility permission is not granted to the interpreter running
pytest, the experiment itself reports every trial UNSUPPORTED (it does
not skip silently) - this test accepts either outcome and checks the
harness behaved correctly either way.
"""

from __future__ import annotations

import pytest

from phase0.harness.observers_macos import is_macos, pyobjc_available
from phase0.harness.persistence import read_results
from phase0.schemas.evidence import InterferenceClassification

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_macos(), reason="AX experiment only implemented for macOS"),
    pytest.mark.skipif(not pyobjc_available(), reason="pyobjc not importable"),
]


def test_ax_experiment_runs_and_produces_results(tmp_path):
    from phase0.experiments.macos_ax.experiment import ExperimentBlocked, run_experiment

    try:
        results_path, summary = run_experiment(trial_count=6, output_dir=tmp_path, run_id="it-ax")
    except ExperimentBlocked as exc:
        pytest.skip(f"BLOCKED: {exc}")

    assert summary["trials"] == 6
    observations = list(read_results(results_path))
    assert len(observations) == 6

    classifications = {obs.classification for obs in observations}
    # Either every trial was UNSUPPORTED (no Accessibility permission),
    # or every trial got a real classification - never a silent skip.
    if InterferenceClassification.UNSUPPORTED in classifications:
        assert classifications == {InterferenceClassification.UNSUPPORTED}
    else:
        assert all(obs.postcondition_success is not None for obs in observations)
