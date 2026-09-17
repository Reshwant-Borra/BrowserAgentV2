"""Sanity checks that the real macOS observers return plausible values (or
an explicit unavailable reason) without moving anything. Read-only."""

from __future__ import annotations

import pytest

from phase0.harness.observers_macos import MacObserver, accessibility_trusted, is_macos, pyobjc_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_macos(), reason="macOS-only observers"),
    pytest.mark.skipif(not pyobjc_available(), reason="pyobjc not importable"),
]


def test_cursor_position_is_available_and_numeric():
    observer = MacObserver()
    m = observer.get_cursor_position()
    assert m.available is True
    assert isinstance(m.value["x"], float)
    assert isinstance(m.value["y"], float)


def test_foreground_application_is_available():
    observer = MacObserver()
    app_m, pid_m = observer.get_foreground_application()
    assert app_m.available is True
    assert pid_m.available is True
    assert isinstance(pid_m.value, int)


def test_focused_window_reports_permission_state_explicitly():
    observer = MacObserver()
    window_m, element_m = observer.get_focused_window_and_element()
    if not accessibility_trusted():
        assert window_m.available is False
        assert window_m.reason == "accessibility_permission_not_granted"
        assert element_m.available is False
    else:
        # Either a real value, or an explicit AX-error reason - never a
        # fabricated value.
        assert window_m.available in (True, False)
        if not window_m.available:
            assert window_m.reason
