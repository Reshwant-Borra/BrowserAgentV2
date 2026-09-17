"""Unit tests for ExperimentRunner. All observers are faked; nothing here
touches the real desktop, cursor, or foreground application."""

from __future__ import annotations

import pytest

from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, ActionOutcome, InterferenceClassification, Measurement
from tests.phase0.conftest import make_snapshot


def _runner(observer) -> ExperimentRunner:
    return ExperimentRunner(experiment_id="unit-test", run_id="run-1", observer=observer)


def test_background_safe_trial(fake_observer_factory):
    before = make_snapshot()
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="noop",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        expected_postcondition="counter becomes 1",
        execute=lambda: "ok",
        verify=lambda result: (True, Measurement.of({"observed": result})),
    )

    obs = _runner(observer).run_trial("t1", spec)

    assert obs.action_outcome == ActionOutcome.SUCCESS
    assert obs.postcondition_success is True
    assert obs.cursor_moved is False
    assert obs.foreground_changed is False
    assert obs.focus_changed is False
    assert obs.classification == InterferenceClassification.BACKGROUND_SAFE


def test_cursor_interference_detected(fake_observer_factory):
    before = make_snapshot(cursor=(100.0, 100.0))
    after = make_snapshot(cursor=(400.0, 100.0))
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="warp",
        action_mechanism=ActionMechanism.PHYSICAL_INPUT_INJECTION,
        expected_postcondition="cursor moves",
        execute=lambda: None,
        verify=lambda result: (True, Measurement.of("moved")),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.cursor_moved is True
    assert obs.classification == InterferenceClassification.CURSOR_INTERFERENCE


def test_foreground_interference_detected(fake_observer_factory):
    before = make_snapshot(app="Terminal")
    after = make_snapshot(app="Safari")
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="steal_focus",
        action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
        expected_postcondition="n/a",
        execute=lambda: None,
        verify=lambda result: (True, Measurement.of("done")),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.foreground_changed is True
    assert obs.classification == InterferenceClassification.FOREGROUND_INTERFERENCE


def test_focus_interference_detected(fake_observer_factory):
    before = make_snapshot(window="Window A")
    after = make_snapshot(window="Window B")
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="change_focus",
        action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
        expected_postcondition="n/a",
        execute=lambda: None,
        verify=lambda result: (True, Measurement.of("done")),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.focus_changed is True
    assert obs.classification == InterferenceClassification.FOCUS_INTERFERENCE


def test_multiple_interference_detected(fake_observer_factory):
    before = make_snapshot(cursor=(0.0, 0.0), app="Terminal")
    after = make_snapshot(cursor=(500.0, 500.0), app="Safari")
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="chaos",
        action_mechanism=ActionMechanism.PHYSICAL_INPUT_INJECTION,
        expected_postcondition="n/a",
        execute=lambda: None,
        verify=lambda result: (True, Measurement.of("done")),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.classification == InterferenceClassification.MULTIPLE_INTERFERENCE


def test_unavailable_cursor_observation_is_inconclusive(fake_observer_factory):
    before = make_snapshot(cursor_available=False)
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.MACOS_AX_READ,
        expected_postcondition="n/a",
        execute=lambda: None,
        verify=lambda result: (True, Measurement.of("done")),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.cursor_moved is None
    assert obs.classification == InterferenceClassification.INCONCLUSIVE


def test_verifier_failure_marks_action_failure_but_not_error(fake_observer_factory):
    before = make_snapshot()
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        expected_postcondition="counter becomes 1",
        execute=lambda: "ok",
        verify=lambda result: (False, Measurement.of({"expected": "1", "observed": "0"})),
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.postcondition_success is False
    assert obs.action_outcome == ActionOutcome.FAILURE
    # Interference is orthogonal to postcondition success.
    assert obs.classification == InterferenceClassification.BACKGROUND_SAFE


def test_action_exception_is_error_and_never_calls_verify(fake_observer_factory):
    before = make_snapshot()
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    verify_called = []

    def execute():
        raise RuntimeError("boom")

    def verify(result):
        verify_called.append(result)
        return True, Measurement.of("should not run")

    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        expected_postcondition="n/a",
        execute=execute,
        verify=verify,
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.action_outcome == ActionOutcome.ERROR
    assert obs.error is not None
    assert obs.error["type"] == "RuntimeError"
    assert obs.postcondition_success is None
    assert not verify_called
    assert obs.classification == InterferenceClassification.ERROR


def test_verifier_exception_is_error(fake_observer_factory):
    before = make_snapshot()
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    def verify(result):
        raise ValueError("verifier exploded")

    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        expected_postcondition="n/a",
        execute=lambda: "ok",
        verify=verify,
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert obs.action_outcome == ActionOutcome.ERROR
    assert obs.error["type"] == "ValueError"
    assert obs.classification == InterferenceClassification.ERROR


def test_unsupported_spec_skips_execution(fake_observer_factory):
    before = make_snapshot()
    after = make_snapshot()
    observer = fake_observer_factory(before, after)

    executed = []

    spec = ActionSpec(
        action_type="op",
        action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
        expected_postcondition="n/a",
        execute=lambda: executed.append(True),
        verify=lambda result: (True, Measurement.of("done")),
        supported=False,
        unsupported_reason="accessibility_permission_not_granted",
    )

    obs = _runner(observer).run_trial("t1", spec)
    assert not executed
    assert obs.classification == InterferenceClassification.UNSUPPORTED
    assert obs.observed_postcondition.available is False
    assert obs.observed_postcondition.reason == "accessibility_permission_not_granted"
