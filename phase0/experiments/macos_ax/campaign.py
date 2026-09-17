"""macOS Accessibility background-safety evidence campaign
(docs/BUILD_SPEC.md §3).

The preliminary `experiment.py` run (30 trials, read/set-value/invoke
cycling over one field) was not enough evidence. This module runs a
larger, multi-condition campaign over the same measurement pipeline
(`ExperimentRunner`/`ActionSpec`/`MacObserver`/`ax_elements`) - it does
not change how interference is measured, only what is exercised and how
results are labeled (`action_type` prefixed `"<condition>__"`, matching
the browser campaign's convention; no schema changes).

Conditions:

- `baseline` - the existing read / set-value / invoke-action cycle
  (`experiment._build_trials`) against the backgrounded fixture.
- `focus_switch` - repeatedly moves AX focus between the fixture's two
  identical-role/untitled AXTextFields (`AXFocused`), verified by
  reading back which field's value is now focused. Distinct from
  `baseline`: this is the "focus-related operations" / "multiple
  controls" class, and the exact shape the focus-identity hardening
  targets.
- `occluded` - the baseline read/set/invoke mix with
  `overlay_window_app.py` visually covering the whole screen.
- `stale_element` - captures a reference to the fixture's second text
  field, triggers its "Rebuild Field 2" button (which destroys and
  replaces that field), then repeatedly reads the OLD, now-invalidated
  reference. The correct, measured behavior is a non-zero AX error every
  time - never a silently-succeeding stale read.

Distinguishes READ (`ax_read_text_value`, `stale_element__*`) from
MUTATING (`ax_set_text_value`, `ax_invoke_press_action`,
`focus_switch__*`) operations via `action_mechanism`
(`MACOS_AX_READ` vs `MACOS_AX_MUTATE`), already set correctly by the
reused trial builders.

"Multiple target windows" is NOT covered: the fixture app is
single-window and adding a second window was judged not practical
within this campaign's scope - documented as a limitation in the
campaign report, not silently skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from phase0.experiments.macos_ax import ax_elements
from phase0.experiments.macos_ax.experiment import (
    _build_trials,
    _get_frontmost_pid,
    _reactivate_and_wait,
)
from phase0.experiments.macos_ax.fixture_process import FixtureLaunchError, launch_fixture
from phase0.experiments.overlay_process import OverlayLaunchError, launch_overlay
from phase0.fixtures.mac_ax_fixture_app import WINDOW_TITLE
from phase0.harness.observers_macos import MacObserver, accessibility_trusted, is_macos, pyobjc_available
from phase0.harness.persistence import ResultWriter, read_results, summarize, write_summary
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, ExperimentObservation, Measurement

try:
    import ApplicationServices as AS

    _AX_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AS = None  # type: ignore[assignment]
    _AX_AVAILABLE = False

EXPERIMENT_ID = "ax_campaign"

DEFAULT_COUNTS = {
    "baseline": 400,
    "focus_switch": 60,
    "occluded": 40,
    "stale_element": 10,
}


class CampaignBlocked(RuntimeError):
    pass


def _tag(condition: str, trials: List[Tuple[str, ActionSpec]]) -> List[Tuple[str, ActionSpec]]:
    tagged = []
    for trial_id, spec in trials:
        spec.action_type = f"{condition}__{spec.action_type}"
        tagged.append((f"{condition}-{trial_id}", spec))
    return tagged


def _read_focused_value(fixture_pid: int):
    ax_app = AS.AXUIElementCreateApplication(fixture_pid)
    focused = ax_elements._copy_attr(ax_app, "AXFocusedUIElement")
    if focused is None:
        return None
    return ax_elements.read_value(focused)


def _focus_switch_trials(fixture_pid: int, count: int) -> List[Tuple[str, ActionSpec]]:
    # Read each field's *current* value rather than assuming the fixture's
    # initial constants: if `focus_switch` runs after `baseline` on the
    # same live fixture, `baseline`'s set-value trials have already
    # mutated field 0's content. Focus identity is verified by content
    # here (simplest independent signal for "which field is focused"),
    # so it must reflect whatever the fields actually hold right now, not
    # a stale assumption about a fresh fixture.
    window = ax_elements.get_fixture_window(fixture_pid)
    current_fields = ax_elements.get_text_fields(window)
    expected_values = [ax_elements.read_value(f) for f in current_fields]
    trials: List[Tuple[str, ActionSpec]] = []

    for i in range(count):
        idx = i % 2
        expected = expected_values[idx]

        def execute(_idx=idx):
            window = ax_elements.get_fixture_window(fixture_pid)
            fields = ax_elements.get_text_fields(window)
            return ax_elements.set_focused(fields[_idx])

        def verify(_result, _expected=expected):
            observed = _read_focused_value(fixture_pid)
            return observed == _expected, Measurement.of({"expected": _expected, "observed": observed})

        spec = ActionSpec(
            action_type="ax_set_focused",
            action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
            expected_postcondition=f"AXFocusedUIElement value becomes {expected!r}",
            execute=execute,
            verify=verify,
            target_application=Measurement.of("phase0_ax_fixture"),
            target_process=Measurement.of(fixture_pid),
            target_window=Measurement.of(WINDOW_TITLE),
            focus_pid=fixture_pid,
        )
        trials.append((f"trial-{i:04d}-focus_switch", spec))
    return trials


def _stale_element_trials(fixture_pid: int, count: int) -> List[Tuple[str, ActionSpec]]:
    window = ax_elements.get_fixture_window(fixture_pid)
    fields = ax_elements.get_text_fields(window)
    stale_ref = fields[1]

    rebuild_button = ax_elements.get_rebuild_button(window)
    rebuild_err = ax_elements.perform_action(rebuild_button, "AXPress")
    if rebuild_err != 0:
        raise RuntimeError(f"fixture rebuild action failed: AX error {rebuild_err}")

    trials: List[Tuple[str, ActionSpec]] = []
    for i in range(count):

        def execute():
            return AS.AXUIElementCopyAttributeValue(stale_ref, "AXValue", None)

        def verify(result):
            err, val = result
            # Correct behavior: the AX layer reports the now-destroyed
            # element as invalid (non-zero error, no value) every time -
            # never a stale, silently-successful read.
            success = err != 0 and val is None
            return success, Measurement.of({"ax_error": err, "value": val})

        spec = ActionSpec(
            action_type="read_invalidated_reference",
            action_mechanism=ActionMechanism.MACOS_AX_READ,
            expected_postcondition="reading an invalidated AXUIElement reference returns a non-zero AX error",
            execute=execute,
            verify=verify,
            target_application=Measurement.of("phase0_ax_fixture"),
            target_process=Measurement.of(fixture_pid),
            target_window=Measurement.of(WINDOW_TITLE),
            focus_pid=fixture_pid,
        )
        trials.append((f"trial-{i:04d}-stale", spec))
    return trials


def run_campaign(
    output_dir: Path,
    run_id: str,
    counts: dict = None,
) -> Tuple[Path, dict]:
    if not is_macos() or not pyobjc_available():
        raise CampaignBlocked("AX campaign requires macOS with pyobjc available")
    if not accessibility_trusted():
        raise CampaignBlocked("Accessibility permission not granted; cannot run a meaningful AX campaign")

    counts = {**DEFAULT_COUNTS, **(counts or {})}

    observer = MacObserver()
    holder_pid = _get_frontmost_pid(observer)

    output_dir = Path(output_dir)
    results_path = output_dir / f"{EXPERIMENT_ID}-{run_id}.jsonl"
    writer = ResultWriter(results_path)
    runner = ExperimentRunner(experiment_id=EXPERIMENT_ID, run_id=run_id, observer=observer)

    try:
        fixture = launch_fixture()
    except FixtureLaunchError as exc:
        raise CampaignBlocked(f"could not launch AX fixture app: {exc}") from exc

    condition_counts: dict = {}

    try:
        if holder_pid is not None:
            _reactivate_and_wait(holder_pid)

        target_process = Measurement.of(fixture.pid)

        def run_batch(condition: str, trials: List[Tuple[str, ActionSpec]]) -> None:
            n = 0
            for trial_id, spec in _tag(condition, trials):
                observation: ExperimentObservation = runner.run_trial(trial_id, spec)
                writer.write(observation)
                n += 1
            condition_counts[condition] = n

        # --- baseline: read / set-value / invoke-action ------------------
        run_batch("baseline", _build_trials(target_process, fixture.pid, counts["baseline"]))

        # --- focus_switch --------------------------------------------------
        run_batch("focus_switch", _focus_switch_trials(fixture.pid, counts["focus_switch"]))

        # --- stale_element (still against fixture 1: needs a reference
        # that pre-dates the fixture's own rebuild) -----------------------
        run_batch("stale_element", _stale_element_trials(fixture.pid, counts["stale_element"]))
    finally:
        fixture.terminate()

    # --- occluded: baseline mix on a FRESH fixture process --------------
    # `_build_trials` assumes a pristine fixture (text field at its
    # initial value, press counter at 0). Reusing fixture 1 here would
    # carry over baseline's mutations (a stale-postcondition bug found
    # while validating this campaign, not an interference-measurement
    # defect) and produce misleading `postcondition_success=False`
    # results for a reason unrelated to interference.
    try:
        occluded_fixture = launch_fixture()
    except FixtureLaunchError as exc:
        raise CampaignBlocked(f"could not launch AX fixture app for occluded condition: {exc}") from exc

    try:
        if holder_pid is not None:
            _reactivate_and_wait(holder_pid)
        try:
            overlay = launch_overlay()
        except OverlayLaunchError as exc:
            raise CampaignBlocked(f"could not launch occlusion overlay: {exc}") from exc
        try:
            run_batch(
                "occluded",
                _build_trials(Measurement.of(occluded_fixture.pid), occluded_fixture.pid, counts["occluded"]),
            )
        finally:
            overlay.terminate()
    finally:
        occluded_fixture.terminate()

    summary = summarize(read_results(results_path))
    summary["condition_counts"] = condition_counts
    write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")
    return results_path, summary
