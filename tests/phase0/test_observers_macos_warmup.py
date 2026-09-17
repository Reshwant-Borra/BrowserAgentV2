"""Unit tests for `observers_macos.warm_up_ax_focus_tree`'s guard
clauses only - no real desktop control, no Quartz/AppKit/
ApplicationServices calls. The real-machine behavior (does it actually
make Chrome's AXFocusedUIElement resolve) is covered by the integration
positive control in
tests/phase0/integration/test_focus_warmup_positive_control.py, which
this file deliberately does not duplicate.
"""

from __future__ import annotations

from phase0.harness import observers_macos


def test_warm_up_returns_false_when_pyobjc_unavailable(monkeypatch):
    monkeypatch.setattr(observers_macos, "_PYOBJC_AVAILABLE", False)
    assert observers_macos.warm_up_ax_focus_tree(pid=1) is False


def test_warm_up_returns_false_when_accessibility_not_trusted(monkeypatch):
    monkeypatch.setattr(observers_macos, "_PYOBJC_AVAILABLE", True)
    monkeypatch.setattr(observers_macos, "accessibility_trusted", lambda: False)
    assert observers_macos.warm_up_ax_focus_tree(pid=1) is False


def test_warm_up_never_raises_on_unexpected_error(monkeypatch):
    """Any failure inside the AXObserver dance is a normal, reportable
    'did not warm up' outcome (False), never an exception - a target
    that can't be warmed up is not a harness bug."""
    monkeypatch.setattr(observers_macos, "_PYOBJC_AVAILABLE", True)
    monkeypatch.setattr(observers_macos, "accessibility_trusted", lambda: True)

    class _ExplodingAS:
        @staticmethod
        def AXUIElementCreateApplication(pid):
            raise RuntimeError("boom")

    monkeypatch.setattr(observers_macos, "AS", _ExplodingAS)
    assert observers_macos.warm_up_ax_focus_tree(pid=1) is False
