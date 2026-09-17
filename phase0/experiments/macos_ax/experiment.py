"""macOS Accessibility (AX) non-interference spike.

Scope (see docs/BUILD_SPEC.md section 3 and the milestone instructions):
this measures whether AXUIElement read/mutate/invoke operations against
a *background* application move the physical cursor or steal
foreground/focus, using a small deterministic fixture app
(phase0/fixtures/mac_ax_fixture_app.py). It is a narrow spike, not the
future AccessibilityKernel/MacAccessibilityAdapter.

Protocol per run:
1. Record whichever application is currently frontmost ("foreground
   holder").
2. Launch the fixture app (its window briefly may or may not grab
   focus - this setup step is NOT measured).
3. Re-activate the foreground holder so the fixture is now a background
   application, and wait (polling, not a blind sleep) until that is
   observably true.
4. Run measured trials: READ (AXValue), SET VALUE (AXValue, mutating),
   and INVOKE ACTION (AXPress, mutating) against the backgrounded
   fixture, each independently verified and classified.
5. Terminate the fixture process.

If the Accessibility permission is not granted, every trial is recorded
as UNSUPPORTED rather than skipped or faked.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from phase0.experiments.macos_ax import ax_elements
from phase0.experiments.macos_ax.fixture_process import FixtureHandle, FixtureLaunchError, launch_fixture
from phase0.fixtures.mac_ax_fixture_app import COUNTER_LABEL_PREFIX, TEXT_FIELD_INITIAL_VALUE, WINDOW_TITLE
from phase0.harness.observers_macos import MacObserver, accessibility_trusted, is_macos, pyobjc_available
from phase0.harness.persistence import ResultWriter, summarize, write_summary
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, ExperimentObservation, Measurement

try:
    import AppKit

    _APPKIT_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    _APPKIT_AVAILABLE = False

EXPERIMENT_ID = "macos_ax_non_interference"


class ExperimentBlocked(RuntimeError):
    """Raised when the experiment cannot run at all (missing platform
    capability/permission/dependency). Callers must report this as
    BLOCKED, never manufacture a result."""


def _require_macos() -> None:
    if not is_macos():
        raise ExperimentBlocked("this experiment only runs on macOS")
    if not pyobjc_available():
        raise ExperimentBlocked("pyobjc is not importable in this environment")


def _get_frontmost_pid(observer: MacObserver) -> Optional[int]:
    _, pid_measurement = observer.get_foreground_application()
    return int(pid_measurement.value) if pid_measurement.available else None


def _reactivate_and_wait(holder_pid: int, timeout: float = 3.0, interval: float = 0.05) -> bool:
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


def _build_trials(
    runner_target_process: Measurement,
    fixture_pid: int,
    trial_count: int,
) -> List[Tuple[str, ActionSpec]]:
    """Builds a deterministic, repeatable sequence of trials cycling
    through read / set-value / invoke-action against the fixture."""

    trials: List[Tuple[str, ActionSpec]] = []
    expected_text = TEXT_FIELD_INITIAL_VALUE
    expected_press_count = 0

    operations = ["read", "set_value", "invoke_action"]

    for i in range(trial_count):
        op = operations[i % len(operations)]
        trial_id = f"trial-{i:04d}-{op}"

        if op == "read":

            def execute():
                window = ax_elements.get_fixture_window(fixture_pid)
                text_field = ax_elements.get_text_field(window)
                return ax_elements.read_value(text_field)

            def verify(_result, _expected=expected_text):
                window = ax_elements.get_fixture_window(fixture_pid)
                text_field = ax_elements.get_text_field(window)
                observed = ax_elements.read_value(text_field)
                success = observed == _expected
                return success, Measurement.of({"expected": _expected, "observed": observed})

            spec = ActionSpec(
                action_type="ax_read_text_value",
                action_mechanism=ActionMechanism.MACOS_AX_READ,
                expected_postcondition=f"AXValue of fixture text field equals {expected_text!r}",
                execute=execute,
                verify=verify,
                target_application=Measurement.of("phase0_ax_fixture"),
                target_process=runner_target_process,
                target_window=Measurement.of(WINDOW_TITLE),
            )

        elif op == "set_value":
            new_value = f"phase0-mutated-{i}"

            def execute(_new_value=new_value):
                window = ax_elements.get_fixture_window(fixture_pid)
                text_field = ax_elements.get_text_field(window)
                err = ax_elements.set_value(text_field, _new_value)
                return err

            def verify(_result, _expected=new_value):
                window = ax_elements.get_fixture_window(fixture_pid)
                text_field = ax_elements.get_text_field(window)
                observed = ax_elements.read_value(text_field)
                success = observed == _expected
                return success, Measurement.of({"expected": _expected, "observed": observed})

            spec = ActionSpec(
                action_type="ax_set_text_value",
                action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                expected_postcondition=f"AXValue of fixture text field becomes {new_value!r}",
                execute=execute,
                verify=verify,
                target_application=Measurement.of("phase0_ax_fixture"),
                target_process=runner_target_process,
                target_window=Measurement.of(WINDOW_TITLE),
            )
            expected_text = new_value

        else:  # invoke_action
            expected_press_count += 1
            expected_label = f"{COUNTER_LABEL_PREFIX}{expected_press_count}"

            def execute():
                window = ax_elements.get_fixture_window(fixture_pid)
                button = ax_elements.get_press_button(window)
                err = ax_elements.perform_action(button, "AXPress")
                return err

            def verify(_result, _expected=expected_label):
                window = ax_elements.get_fixture_window(fixture_pid)
                counter = ax_elements.get_counter_label(window)
                observed = ax_elements.read_value(counter)
                success = observed == _expected
                return success, Measurement.of({"expected": _expected, "observed": observed})

            spec = ActionSpec(
                action_type="ax_invoke_press_action",
                action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                expected_postcondition=f"fixture counter label becomes {expected_label!r}",
                execute=execute,
                verify=verify,
                target_application=Measurement.of("phase0_ax_fixture"),
                target_process=runner_target_process,
                target_window=Measurement.of(WINDOW_TITLE),
            )

        trials.append((trial_id, spec))

    return trials


def run_experiment(
    trial_count: int,
    output_dir: Path,
    run_id: str,
) -> Tuple[Path, dict]:
    """Runs the macOS AX non-interference spike.

    Raises `ExperimentBlocked` if the platform/permission prerequisites
    are not met - callers must surface this as BLOCKED, not a result.
    """
    _require_macos()

    observer = MacObserver()

    permission_ok = accessibility_trusted()

    output_dir = Path(output_dir)
    results_path = output_dir / f"{EXPERIMENT_ID}-{run_id}.jsonl"
    writer = ResultWriter(results_path)
    runner = ExperimentRunner(experiment_id=EXPERIMENT_ID, run_id=run_id, observer=observer)

    if not permission_ok:
        # Do not attempt any AX call; do not launch the fixture. Record
        # every planned trial as UNSUPPORTED so the evidence trail is
        # explicit about *why* no measurement happened.
        target_process = Measurement.unavailable("fixture not launched: accessibility permission not granted")
        for trial_id, spec in _build_trials(target_process, fixture_pid=-1, trial_count=trial_count):
            spec.supported = False
            spec.unsupported_reason = "accessibility_permission_not_granted"
            spec.execute = lambda: None
            observation = runner.run_trial(trial_id, spec)
            writer.write(observation)

        summary = summarize(_read_back(results_path))
        write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")
        return results_path, summary

    holder_pid = _get_frontmost_pid(observer)

    try:
        fixture: FixtureHandle = launch_fixture()
    except FixtureLaunchError as exc:
        raise ExperimentBlocked(f"could not launch AX fixture app: {exc}") from exc

    try:
        if holder_pid is not None:
            _reactivate_and_wait(holder_pid)

        target_process = Measurement.of(fixture.pid)
        trials = _build_trials(target_process, fixture.pid, trial_count)
        for trial_id, spec in trials:
            observation: ExperimentObservation = runner.run_trial(trial_id, spec)
            writer.write(observation)
    finally:
        fixture.terminate()

    summary = summarize(_read_back(results_path))
    write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")
    return results_path, summary


def _read_back(results_path: Path):
    from phase0.harness.persistence import read_results

    return list(read_results(results_path))
