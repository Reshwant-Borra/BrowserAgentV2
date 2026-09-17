"""Browser background-safety evidence campaign (docs/BUILD_SPEC.md §2).

The preliminary `experiment.py` run (60 trials, one condition) was not
enough evidence for a BACKGROUND_PROVEN claim. This module runs a larger,
multi-condition campaign over the same measurement pipeline
(`ExperimentRunner`/`ActionSpec`/`MacObserver`) - it does not change how
interference is measured, only what is exercised and how results are
labeled for per-condition/per-class reporting.

Conditions (each its own batch of trials, `action_type` prefixed
`"<condition>__"` so results can be grouped without touching the frozen
`ExperimentObservation` schema):

- `baseline_backgrounded` - the existing click/fill/select/navigate mix
  (`experiment._build_trials`), browser window backgrounded throughout.
- `occluded` - same mix, with `phase0/fixtures/overlay_window_app.py`
  covering the whole screen (see that module for why it doesn't itself
  steal frontmost/focus).
- `multi_tab` - a second Playwright page (tab) is open in the same
  browser context throughout, mix runs against the first tab.
- `multi_window` - a second BrowserContext (a second top-level Chromium
  window) is open throughout, mix runs against the first window.
- `popup` - repeatedly opens/verifies/closes a `window.open()` popup
  (`page.expect_popup()`), the one non-`_build_trials` action class.

All conditions run with the real foreground holder application
reactivated once, up front (per `experiment._reactivate_and_wait`), and
never explicitly touched again - exactly the "user keeps using another
app in the foreground" condition from BUILD_SPEC's non-interference
stress requirement. No synthetic user input is injected during
measurement to avoid confounding the signal being measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from phase0.experiments.browser_background.experiment import (
    PAGE1_URL,
    PAGE2_TITLE,
    _build_trials,
    _get_frontmost_pid,
    _reactivate_and_wait,
)
from phase0.experiments.overlay_process import OverlayLaunchError, launch_overlay
from phase0.harness.observers_macos import MacObserver, is_macos, pyobjc_available
from phase0.harness.persistence import ResultWriter, read_results, summarize, write_summary
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, ExperimentObservation, Measurement

try:
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - missing dependency
    sync_playwright = None  # type: ignore[assignment]
    _PLAYWRIGHT_AVAILABLE = False

EXPERIMENT_ID = "browser_campaign"

DEFAULT_COUNTS = {
    "baseline_backgrounded": 400,
    "occluded": 40,
    "multi_tab": 30,
    "multi_window": 20,
    "popup": 10,
}


class CampaignBlocked(RuntimeError):
    pass


def _require_prerequisites() -> None:
    if not is_macos() or not pyobjc_available():
        raise CampaignBlocked("browser campaign requires macOS with pyobjc available")
    if not _PLAYWRIGHT_AVAILABLE:
        raise CampaignBlocked("playwright is not importable")


def _tag(condition: str, trials: List[Tuple[str, ActionSpec]]) -> List[Tuple[str, ActionSpec]]:
    tagged = []
    for trial_id, spec in trials:
        spec.action_type = f"{condition}__{spec.action_type}"
        tagged.append((f"{condition}-{trial_id}", spec))
    return tagged


def _popup_trials(page, count: int) -> List[Tuple[str, ActionSpec]]:
    trials: List[Tuple[str, ActionSpec]] = []
    target_application = Measurement.of("chromium (playwright-managed)")
    target_process = Measurement.unavailable(
        "Playwright's Python sync API does not expose the underlying browser process pid"
    )

    for i in range(count):
        trial_id = f"popup-{i:04d}"

        def execute():
            with page.expect_popup() as popup_info:
                page.click("#popup-btn")
            popup = popup_info.value
            popup.wait_for_load_state()
            return popup

        def verify(popup):
            try:
                observed = popup.title()
                success = observed == PAGE2_TITLE
                return success, Measurement.of({"expected": PAGE2_TITLE, "observed": observed})
            finally:
                popup.close()

        spec = ActionSpec(
            action_type="popup__open_and_verify_popup",
            action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
            expected_postcondition=f"popup page title equals '{PAGE2_TITLE}'",
            execute=execute,
            verify=verify,
            target_application=target_application,
            target_process=target_process,
            target_window=Measurement.of("popup (window.open target=_blank)"),
        )
        trials.append((trial_id, spec))
    return trials


def run_campaign(
    output_dir: Path,
    run_id: str,
    counts: dict = None,
) -> Tuple[Path, dict]:
    """Runs the full multi-condition browser campaign. Raises
    `CampaignBlocked` if prerequisites are missing."""
    _require_prerequisites()
    counts = {**DEFAULT_COUNTS, **(counts or {})}

    observer = MacObserver()
    holder_pid = _get_frontmost_pid(observer)

    output_dir = Path(output_dir)
    results_path = output_dir / f"{EXPERIMENT_ID}-{run_id}.jsonl"
    writer = ResultWriter(results_path)
    runner = ExperimentRunner(experiment_id=EXPERIMENT_ID, run_id=run_id, observer=observer)

    condition_counts: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(PAGE1_URL)

            if holder_pid is not None:
                _reactivate_and_wait(holder_pid)

            def run_batch(condition: str, trials: List[Tuple[str, ActionSpec]]) -> None:
                n = 0
                for trial_id, spec in _tag(condition, trials):
                    observation: ExperimentObservation = runner.run_trial(trial_id, spec)
                    writer.write(observation)
                    n += 1
                condition_counts[condition] = n

            # --- baseline_backgrounded ---------------------------------
            run_batch("baseline_backgrounded", _build_trials(page, counts["baseline_backgrounded"]))

            # --- occluded ------------------------------------------------
            try:
                overlay = launch_overlay()
            except OverlayLaunchError as exc:
                raise CampaignBlocked(f"could not launch occlusion overlay: {exc}") from exc
            try:
                run_batch("occluded", _build_trials(page, counts["occluded"]))
            finally:
                overlay.terminate()

            # --- multi_tab: a second tab stays open throughout -----------
            second_tab = browser.new_page()
            try:
                second_tab.goto(PAGE1_URL)
                run_batch("multi_tab", _build_trials(page, counts["multi_tab"]))
            finally:
                second_tab.close()

            # --- multi_window: a second top-level window stays open ------
            second_context = browser.new_context()
            try:
                second_window_page = second_context.new_page()
                second_window_page.goto(PAGE1_URL)
                run_batch("multi_window", _build_trials(page, counts["multi_window"]))
            finally:
                second_context.close()

            # --- popup / new-page ------------------------------------------
            run_batch("popup", _popup_trials(page, counts["popup"]))
        finally:
            browser.close()

    summary = summarize(read_results(results_path))
    summary["condition_counts"] = condition_counts
    write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")
    return results_path, summary
