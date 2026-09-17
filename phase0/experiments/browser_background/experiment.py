"""Playwright browser non-interference experiment.

Question (see docs/BUILD_SPEC.md section 2): can Playwright-driven
browser actions perform useful work without moving the user's physical
cursor, stealing foreground application focus, or interfering with
unrelated user activity?

Protocol per run (mirrors the macOS AX experiment for consistency):
1. Record whichever application is currently frontmost ("foreground
   holder").
2. Launch a headed Chromium instance and load the local fixture page
   (setup - not measured; a freshly opened browser window may or may
   not grab OS focus, and that is a separate, already-known effect from
   window creation, not from the semantic actions under test).
3. Re-activate the foreground holder so the browser is a background
   window, and wait (polling, not a blind sleep) until that is
   observably true.
4. Run measured trials, cycling a fixed unit of semantic actions -
   click, fill, select, navigate forward, navigate back - each
   independently verified against page content and classified for
   interference.
5. Close the browser.

Only Playwright's semantic APIs are used (`click`, `fill`,
`select_option`, page navigation). No physical mouse/keyboard
automation is used to perform the actions under test.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from phase0.harness.observers_macos import MacObserver, is_macos, pyobjc_available
from phase0.harness.persistence import ResultWriter, read_results, summarize, write_summary
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.evidence import ActionMechanism, Measurement

try:
    import AppKit

    _APPKIT_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    _APPKIT_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright

    _PLAYWRIGHT_AVAILABLE = True
    _PLAYWRIGHT_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - missing dependency
    sync_playwright = None  # type: ignore[assignment]
    _PLAYWRIGHT_AVAILABLE = False
    _PLAYWRIGHT_IMPORT_ERROR = str(exc)

EXPERIMENT_ID = "browser_non_interference"

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
PAGE1_PATH = FIXTURES_DIR / "browser_page1.html"
PAGE2_PATH = FIXTURES_DIR / "browser_page2.html"
PAGE1_URL = PAGE1_PATH.resolve().as_uri()
PAGE1_TITLE = "Phase0 Fixture Page 1"
PAGE2_TITLE = "Phase0 Fixture Page 2"

SELECT_OPTIONS = ["alpha", "bravo", "charlie"]


class ExperimentBlocked(RuntimeError):
    """Raised when the experiment cannot run at all (missing platform
    capability/permission/dependency). Callers must report this as
    BLOCKED, never manufacture a result."""


def _require_prerequisites() -> None:
    if not PAGE1_PATH.exists() or not PAGE2_PATH.exists():
        raise ExperimentBlocked(f"fixture pages missing under {FIXTURES_DIR}")
    if not _PLAYWRIGHT_AVAILABLE:
        raise ExperimentBlocked(f"playwright is not importable: {_PLAYWRIGHT_IMPORT_ERROR}")
    if not is_macos():
        raise ExperimentBlocked("this runner's OS observers currently only support macOS")
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


def _build_trials(page, trial_count: int) -> List[Tuple[str, ActionSpec]]:
    target_process = Measurement.unavailable(
        "Playwright's Python sync API does not expose the underlying browser process pid"
    )
    target_application = Measurement.of("chromium (playwright-managed)")

    unit_names = ["click", "fill", "select", "navigate_forward", "navigate_back"]
    trials: List[Tuple[str, ActionSpec]] = []

    expected_count = 0
    select_index = 0

    i = 0
    while len(trials) < trial_count:
        op = unit_names[i % len(unit_names)]
        trial_id = f"trial-{len(trials):04d}-{op}"

        if op == "click":
            expected_count += 1

            def execute():
                page.click("#increment-btn")

            def verify(_result, _expected=expected_count):
                observed = page.inner_text("#counter")
                success = observed == str(_expected)
                return success, Measurement.of({"expected": str(_expected), "observed": observed})

            spec = ActionSpec(
                action_type="click_button",
                action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
                expected_postcondition=f"#counter text becomes '{expected_count}'",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=Measurement.of(PAGE1_TITLE),
            )

        elif op == "fill":
            value = f"phase0-{len(trials)}"

            def execute(_value=value):
                page.fill("#text-input", _value)

            def verify(_result, _expected=value):
                observed = page.inner_text("#text-mirror")
                success = observed == _expected
                return success, Measurement.of({"expected": _expected, "observed": observed})

            spec = ActionSpec(
                action_type="fill_input",
                action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
                expected_postcondition=f"#text-mirror text becomes '{value}'",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=Measurement.of(PAGE1_TITLE),
            )

        elif op == "select":
            value = SELECT_OPTIONS[select_index % len(SELECT_OPTIONS)]
            select_index += 1

            def execute(_value=value):
                page.select_option("#select-input", _value)

            def verify(_result, _expected=value):
                observed = page.inner_text("#select-mirror")
                success = observed == _expected
                return success, Measurement.of({"expected": _expected, "observed": observed})

            spec = ActionSpec(
                action_type="select_option",
                action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
                expected_postcondition=f"#select-mirror text becomes '{value}'",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=Measurement.of(PAGE1_TITLE),
            )

        elif op == "navigate_forward":

            def execute():
                page.click("#nav-link")

            def verify(_result):
                observed = page.title()
                success = observed == PAGE2_TITLE
                return success, Measurement.of({"expected": PAGE2_TITLE, "observed": observed})

            spec = ActionSpec(
                action_type="navigate_forward",
                action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
                expected_postcondition=f"page title becomes '{PAGE2_TITLE}'",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=Measurement.of(PAGE1_TITLE),
            )

        else:  # navigate_back
            expected_count = 0
            select_index = 0

            def execute():
                page.click("#back-link")

            def verify(_result):
                observed = page.title()
                success = observed == PAGE1_TITLE
                return success, Measurement.of({"expected": PAGE1_TITLE, "observed": observed})

            spec = ActionSpec(
                action_type="navigate_back",
                action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
                expected_postcondition=f"page title becomes '{PAGE1_TITLE}'",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=Measurement.of(PAGE2_TITLE),
            )

        trials.append((trial_id, spec))
        i += 1

    return trials


def run_experiment(
    trial_count: int,
    output_dir: Path,
    run_id: str,
    headless: bool = False,
) -> Tuple[Path, dict]:
    """Runs the Playwright browser non-interference experiment.

    `headless=False` (the default) is deliberate: a headless browser has
    no OS-level window to steal focus from anything, which would make
    the experiment trivially pass without measuring anything real. The
    question this experiment answers only has evidentiary value against
    a real, visible browser window.

    Raises `ExperimentBlocked` if prerequisites are not met.
    """
    _require_prerequisites()

    observer = MacObserver()
    holder_pid = _get_frontmost_pid(observer)

    output_dir = Path(output_dir)
    results_path = output_dir / f"{EXPERIMENT_ID}-{run_id}.jsonl"
    writer = ResultWriter(results_path)
    runner = ExperimentRunner(experiment_id=EXPERIMENT_ID, run_id=run_id, observer=observer)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(PAGE1_URL)

            if holder_pid is not None:
                _reactivate_and_wait(holder_pid)

            trials = _build_trials(page, trial_count)
            for trial_id, spec in trials:
                observation = runner.run_trial(trial_id, spec)
                writer.write(observation)
        finally:
            browser.close()

    summary = summarize(read_results(results_path))
    write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")
    return results_path, summary
