from __future__ import annotations

from pathlib import Path

import pytest

from phase0.harness.persistence import ResultWriter, read_results, summarize
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, InterferenceClassification, Measurement, SchemaValidationError
from tests.phase0.conftest import make_snapshot


def _make_trial(observer, outcome_success: bool):
    runner = ExperimentRunner(experiment_id="persist-test", run_id="run-1", observer=observer)
    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        expected_postcondition="n/a",
        execute=lambda: "ok",
        verify=lambda result: (outcome_success, Measurement.of("done")),
    )
    return runner.run_trial(f"t-{outcome_success}", spec)


def test_write_then_read_round_trip(tmp_path: Path, fake_observer_factory):
    observer = fake_observer_factory(make_snapshot(), make_snapshot(), make_snapshot(), make_snapshot())
    obs1 = _make_trial(observer, True)
    obs2 = _make_trial(observer, False)

    path = tmp_path / "results.jsonl"
    writer = ResultWriter(path)
    writer.write(obs1)
    writer.write(obs2)

    restored = list(read_results(path))
    assert len(restored) == 2
    assert restored[0].to_dict() == obs1.to_dict()
    assert restored[1].to_dict() == obs2.to_dict()


def test_read_results_rejects_malformed_json_line(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not valid json\n")
    with pytest.raises(SchemaValidationError):
        list(read_results(path))


def test_read_results_rejects_malformed_record(tmp_path: Path):
    path = tmp_path / "bad_record.jsonl"
    path.write_text('{"schema_version": "1.0.0"}\n')
    with pytest.raises(SchemaValidationError):
        list(read_results(path))


def test_summarize_counts_all_trials_including_failures(fake_observer_factory):
    observer = fake_observer_factory(
        make_snapshot(), make_snapshot(),  # trial 1: success
        make_snapshot(), make_snapshot(),  # trial 2: failure
    )
    obs_success = _make_trial(observer, True)
    obs_failure = _make_trial(observer, False)

    summary = summarize([obs_success, obs_failure])
    assert summary["trials"] == 2
    assert summary["verified_postconditions"] == 1
    assert summary["background_safe_count"] == 2  # interference-clean regardless of postcondition
    assert summary["error_count"] == 0


def test_summarize_tracks_interference_rates(fake_observer_factory):
    clean_before = make_snapshot(cursor=(0.0, 0.0))
    clean_after = make_snapshot(cursor=(0.0, 0.0))
    moved_before = make_snapshot(cursor=(0.0, 0.0))
    moved_after = make_snapshot(cursor=(999.0, 999.0))

    observer = fake_observer_factory(clean_before, clean_after, moved_before, moved_after)
    obs_clean = _make_trial(observer, True)
    obs_moved = _make_trial(observer, True)

    summary = summarize([obs_clean, obs_moved])
    assert summary["trials"] == 2
    assert summary["cursor_interference_count"] == 1
    assert summary["cursor_interference_rate"] == pytest.approx(0.5)
    assert summary["background_safe_count"] == 1


def test_summarize_empty_list_does_not_crash():
    summary = summarize([])
    assert summary["trials"] == 0
    assert summary["latency_ms"]["median"] is None
