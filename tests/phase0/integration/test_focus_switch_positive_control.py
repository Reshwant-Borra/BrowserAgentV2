"""Real-machine positive control for focus-interference detection.

This exists solely to prove the hardened measurement harness actually
detects a genuine focus change between two elements that a bare
(role, title) comparison cannot tell apart - the exact false-negative
`observers_macos._element_identity_changed` was hardened against (see
phase0/README.md). It mirrors `phase0/harness/control.py`'s cursor
positive control: not part of the AX non-interference experiment, only
meaningful with real Accessibility permission, and skipped otherwise.

The fixture app (phase0/fixtures/mac_ax_fixture_app.py) exposes two
AXTextFields with identical role, no AXTitle, differing only in screen
position. Focus is moved between them via the public AXFocused
attribute (a semantic AX action, not synthetic input), while the
original foreground application stays frontmost throughout, so this
isolates the *element* identity signal from window/foreground signals.
"""

from __future__ import annotations

import time

import pytest

from phase0.experiments.macos_ax import ax_elements
from phase0.experiments.macos_ax.fixture_process import FixtureLaunchError, launch_fixture
from phase0.harness.observers_macos import MacObserver, accessibility_trusted, is_macos, pyobjc_available
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, InterferenceClassification, Measurement

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_macos(), reason="AX fixture only implemented for macOS"),
    pytest.mark.skipif(not pyobjc_available(), reason="pyobjc not importable"),
]


def _get_fixture_window_with_retry(pid: int, timeout: float = 2.0, interval: float = 0.05):
    """`get_fixture_window` immediately after `launch_fixture()` returns
    can transiently see no AXWindows yet: the fixture's own readiness
    signal fires once its window exists in-process, but this process's
    AX query of another process's window can lag briefly behind that,
    especially under system load (observed when run after other
    integration tests). Poll instead of failing on the first miss - no
    blind sleep, matching `_reactivate_and_wait` below."""
    deadline = time.monotonic() + timeout
    last_exc: Exception = ax_elements.ElementNotFoundError(f"pid {pid} never exposed AXWindows")
    while time.monotonic() < deadline:
        try:
            return ax_elements.get_fixture_window(pid)
        except ax_elements.ElementNotFoundError as exc:
            last_exc = exc
            time.sleep(interval)
    raise last_exc


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


def test_focus_switch_between_untitled_fields_is_detected_as_focus_interference():
    if not accessibility_trusted():
        pytest.skip("Accessibility permission not granted; this positive control needs a real focus change to measure")

    observer = MacObserver()
    _, holder_pid_measurement = observer.get_foreground_application()
    holder_pid = int(holder_pid_measurement.value) if holder_pid_measurement.available else None

    try:
        fixture = launch_fixture()
    except FixtureLaunchError as exc:
        pytest.skip(f"could not launch AX fixture app: {exc}")

    try:
        if holder_pid is not None:
            _reactivate_and_wait(holder_pid)

        window = _get_fixture_window_with_retry(fixture.pid)
        fields = ax_elements.get_text_fields(window)
        assert len(fields) == 2, "fixture must expose two AXTextFields for this positive control"

        # Confirm the exact false-negative shape this hardens against:
        # both fields report the same role and no title, before relying
        # on any other signal to tell them apart.
        for field in fields:
            assert ax_elements._copy_attr(field, "AXRole") == "AXTextField"
            assert ax_elements._copy_attr(field, "AXTitle") is None

        field_a, field_b = fields[0], fields[1]

        def execute():
            err = ax_elements.set_focused(field_b)
            if err != 0:
                raise RuntimeError(f"AXUIElementSetAttributeValue(AXFocused) failed: err={err}")
            return err

        def verify(_result):
            focused = ax_elements._copy_attr(_ax_app_element(fixture.pid), "AXFocusedUIElement")
            is_field_b = focused == field_b
            return is_field_b, Measurement.of({"focus_moved_to_field_b": bool(is_field_b)})

        spec = ActionSpec(
            action_type="ax_focus_switch_positive_control",
            action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
            expected_postcondition="AX focus moves from field_a to field_b (identical role, no titles)",
            execute=execute,
            verify=verify,
            target_application=Measurement.of("phase0_ax_fixture"),
            target_process=Measurement.of(fixture.pid),
            target_window=Measurement.unavailable("positive control: window title not tracked"),
            focus_pid=fixture.pid,
        )

        runner = ExperimentRunner(experiment_id="focus_switch_positive_control", run_id="it-focus", observer=observer)
        observation = runner.run_trial("focus-switch-0000", spec)

        assert observation.postcondition_success is True, (
            f"AX focus did not actually move to field_b: {observation.observed_postcondition.to_dict()}"
        )
        assert observation.cursor_moved is False
        assert observation.foreground_changed is False
        assert observation.focus_changed is True
        assert observation.classification == InterferenceClassification.FOCUS_INTERFERENCE
    finally:
        fixture.terminate()


def _ax_app_element(pid: int):
    import ApplicationServices as AS

    return AS.AXUIElementCreateApplication(pid)
