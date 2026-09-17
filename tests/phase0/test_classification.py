import pytest

from phase0.harness.classification import classify_interference
from phase0.schemas.evidence import ActionOutcome, InterferenceClassification


def test_no_interference_is_background_safe():
    result = classify_interference(
        cursor_moved=False, foreground_changed=False, focus_changed=False, action_outcome=ActionOutcome.SUCCESS
    )
    assert result == InterferenceClassification.BACKGROUND_SAFE


def test_cursor_only_is_cursor_interference():
    result = classify_interference(
        cursor_moved=True, foreground_changed=False, focus_changed=False, action_outcome=ActionOutcome.SUCCESS
    )
    assert result == InterferenceClassification.CURSOR_INTERFERENCE


def test_foreground_only_is_foreground_interference():
    result = classify_interference(
        cursor_moved=False, foreground_changed=True, focus_changed=False, action_outcome=ActionOutcome.SUCCESS
    )
    assert result == InterferenceClassification.FOREGROUND_INTERFERENCE


def test_focus_only_is_focus_interference():
    result = classify_interference(
        cursor_moved=False, foreground_changed=False, focus_changed=True, action_outcome=ActionOutcome.SUCCESS
    )
    assert result == InterferenceClassification.FOCUS_INTERFERENCE


@pytest.mark.parametrize(
    "cursor_moved,foreground_changed,focus_changed",
    [
        (True, True, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
def test_two_or_more_signals_is_multiple_interference(cursor_moved, foreground_changed, focus_changed):
    result = classify_interference(
        cursor_moved=cursor_moved,
        foreground_changed=foreground_changed,
        focus_changed=focus_changed,
        action_outcome=ActionOutcome.SUCCESS,
    )
    assert result == InterferenceClassification.MULTIPLE_INTERFERENCE


@pytest.mark.parametrize(
    "cursor_moved,foreground_changed,focus_changed",
    [
        (None, False, False),
        (False, None, False),
        (False, False, None),
        (None, None, None),
    ],
)
def test_any_unmeasurable_signal_is_inconclusive(cursor_moved, foreground_changed, focus_changed):
    result = classify_interference(
        cursor_moved=cursor_moved,
        foreground_changed=foreground_changed,
        focus_changed=focus_changed,
        action_outcome=ActionOutcome.SUCCESS,
    )
    assert result == InterferenceClassification.INCONCLUSIVE


def test_action_error_is_error_regardless_of_signals():
    result = classify_interference(
        cursor_moved=True, foreground_changed=True, focus_changed=True, action_outcome=ActionOutcome.ERROR
    )
    assert result == InterferenceClassification.ERROR


def test_unsupported_overrides_clean_signals():
    result = classify_interference(
        cursor_moved=False,
        foreground_changed=False,
        focus_changed=False,
        action_outcome=ActionOutcome.SUCCESS,
        supported=False,
    )
    assert result == InterferenceClassification.UNSUPPORTED


def test_error_takes_precedence_over_unsupported():
    result = classify_interference(
        cursor_moved=None,
        foreground_changed=None,
        focus_changed=None,
        action_outcome=ActionOutcome.ERROR,
        supported=False,
    )
    assert result == InterferenceClassification.ERROR


def test_action_failure_does_not_force_error_classification():
    # A failed postcondition (ActionOutcome.FAILURE) with clean
    # interference signals is still BACKGROUND_SAFE: interference and
    # task success are orthogonal measurements.
    result = classify_interference(
        cursor_moved=False, foreground_changed=False, focus_changed=False, action_outcome=ActionOutcome.FAILURE
    )
    assert result == InterferenceClassification.BACKGROUND_SAFE
