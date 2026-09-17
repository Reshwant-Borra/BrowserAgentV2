"""Real-machine positive control for `observers_macos.warm_up_ax_focus_tree`.

Reproduces, in a minimal and repeatable form, the macOS focus-
observation gap documented in `phase0/CAMPAIGN_REPORT.md` (AX error
-25212 / kAXErrorNoValue on Chrome's AXFocusedUIElement) and proves the
fix: on a disposable, throwaway Chrome instance (never the operator's
real profile/session) with a freshly-loaded page and no focused
control, AXFocusedUIElement is unavailable before warm-up and becomes
readable after it - without moving the cursor, changing the frontmost
application, or requiring the target to be foregrounded.

Launching the disposable Chrome window is, like the AX fixture's own
launch elsewhere in this suite, an unmeasured setup step: creating a
new window can legitimately grab OS foreground focus on its own (a
known, separate effect of window *creation*), so this control
re-activates whatever was frontmost beforehand and waits for that to be
observably true again before it starts measuring - what's actually
under test is interference from `warm_up_ax_focus_tree` itself against
an already-backgrounded target, not from opening the window.

See phase0/experiments/macos_ax/focus_diagnostics.py for the broader,
multi-target diagnostic matrix this was derived from.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from phase0.experiments.macos_ax.focus_diagnostics import (
    TargetUnavailable,
    _disposable_chrome_target,
    _wait_for_ax_bootstrap,
)
from phase0.harness.observers_macos import (
    MacObserver,
    accessibility_trusted,
    cursor_moved,
    foreground_changed,
    is_macos,
    pyobjc_available,
    warm_up_ax_focus_tree,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_macos(), reason="AX focus warm-up only implemented for macOS"),
    pytest.mark.skipif(not pyobjc_available(), reason="pyobjc not importable"),
    pytest.mark.skipif(
        not Path("/Applications/Google Chrome.app").exists(), reason="Google Chrome.app not installed"
    ),
]


def _reactivate_and_wait(holder_pid: int, timeout: float = 3.0, interval: float = 0.05) -> bool:
    import AppKit

    holder = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(holder_pid)
    if holder is None:
        return False
    holder.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)

    ws = AppKit.NSWorkspace.sharedWorkspace()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        front = ws.frontmostApplication()
        if front is not None and front.processIdentifier() == holder_pid:
            return True
        time.sleep(interval)
    return False


def test_warm_up_resolves_focused_ui_element_on_backgrounded_chrome():
    if not accessibility_trusted():
        pytest.skip("Accessibility permission not granted; this positive control needs a real AX read to measure")

    import ApplicationServices as AS

    observer = MacObserver()
    _, holder_pid_measurement = observer.get_foreground_application()
    holder_pid = int(holder_pid_measurement.value) if holder_pid_measurement.available else None

    try:
        with _disposable_chrome_target() as pid:
            ax_app = AS.AXUIElementCreateApplication(pid)
            assert _wait_for_ax_bootstrap(ax_app), "disposable Chrome never became AX-reachable at all"

            if holder_pid is not None:
                _reactivate_and_wait(holder_pid)

            cursor_before = observer.get_cursor_position()
            _, fg_before = observer.get_foreground_application()

            err_before, _elem_before = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", None)
            if err_before == 0:
                # Whether a fresh Chrome process already has its web-
                # content accessibility tree active before any warm-up
                # is itself observed to be non-deterministic (see the
                # diagnostic matrix's repeated-run notes in
                # phase0/CAMPAIGN_REPORT.md) - most runs reproduce the
                # -25212 gap, but not reliably every run. That is not
                # this control's target: skip rather than fail when the
                # precondition for reproducing the bug didn't occur this
                # time, instead of asserting a stricter guarantee than
                # Chrome's own behavior actually provides.
                pytest.skip(
                    "AXFocusedUIElement was already resolvable before warm-up this run "
                    "(Chrome's on-demand AX activation is non-deterministic) - nothing to warm up"
                )

            warmed = warm_up_ax_focus_tree(pid)
            assert warmed is True, "warm_up_ax_focus_tree did not resolve AXFocusedUIElement within its timeout"

            err_after, elem_after = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", None)
            assert err_after == 0
            assert elem_after is not None

            cursor_after = observer.get_cursor_position()
            _, fg_after = observer.get_foreground_application()

            assert cursor_moved(cursor_before, cursor_after) is not True
            assert foreground_changed(fg_before, fg_after) is not True
    except TargetUnavailable as exc:
        pytest.skip(f"disposable Chrome target unavailable in this environment: {exc}")
