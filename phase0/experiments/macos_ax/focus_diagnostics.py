"""Diagnostic matrix for the macOS focus-observation gap documented in
`phase0/CAMPAIGN_REPORT.md` section F: `AXUIElementCopyAttributeValue(ax_app,
"AXFocusedUIElement", ...)` returning AX error -25212 for the real
foreground holder (Google Chrome), which left the focus safety signal
`INCONCLUSIVE` for 93% of that campaign's trials.

This is deliberately NOT a repeat of the 500+/510+ trial campaign
(`phase0/experiments/*/campaign.py`). It is a small, targeted probe
across a handful of representative applications and focus states,
built to answer three questions with evidence rather than assumption:

1. What does AX error -25212 actually mean here?
2. Is it Chrome-specific, or a general public-API/PyObjC/observer-timing
   limitation?
3. Can it be resolved with a public, non-invasive mechanism (no
   foregrounding, no synthetic input, no fabricated identity)?

Run directly: `python3 -m phase0.experiments.macos_ax.focus_diagnostics`
(writes a JSON record per target/state to stdout and, if `--out` is
given, to a file under `phase0/results/`).

Every probe here is read-only or observer-registration-only against a
disposable target the probe itself launches and tears down (the AX
fixture app, a throwaway Chrome profile, a throwaway Safari window) -
never the operator's real browsing session, never synthetic mouse/
keyboard input, never a foregrounding call.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional

from phase0.experiments.macos_ax.fixture_process import FixtureLaunchError, launch_fixture
from phase0.harness.observers_macos import (
    MacObserver,
    accessibility_trusted,
    is_macos,
    pyobjc_available,
    warm_up_ax_focus_tree,
)

try:
    import AppKit
    import ApplicationServices as AS

    _AX_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    AS = None  # type: ignore[assignment]
    _AX_AVAILABLE = False

FIXTURE_PAGE = (Path(__file__).resolve().parents[2] / "fixtures" / "browser_page1.html").resolve()


@dataclass
class FocusStateProbe:
    """One (target, moment) measurement. `error` fields are the raw AX
    error integer (0 == success); `None` means the read was never
    attempted (e.g. warm-up not needed)."""

    target: str
    pid: Optional[int]
    frontmost_pid: Optional[int]
    ax_trusted: bool
    supported_attributes: Optional[List[str]]
    ax_focused_window_error: Optional[int]
    ax_focused_window_available: Optional[bool]
    ax_focused_element_error_before: Optional[int]
    ax_focused_element_available_before: Optional[bool]
    content_subtree_present_before: Optional[bool]
    warm_up_attempted: bool
    warm_up_succeeded: Optional[bool]
    ax_focused_element_error_after: Optional[int]
    ax_focused_element_available_after: Optional[bool]
    focused_element_role: Optional[str]
    cursor_moved: Optional[bool]
    foreground_changed: Optional[bool]
    notes: str = ""


def _copy_attr(element, attribute: str):
    err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    return (err, value)


def _attribute_names(element) -> Optional[List[str]]:
    err, names = AS.AXUIElementCopyAttributeNames(element, None)
    return sorted(names) if err == 0 and names else None


def _find_role(element, target_role: str, max_depth: int = 8, max_children: int = 8) -> Optional[bool]:
    """Bounded search for `target_role` in the AX subtree under
    `element`. Used only to distinguish "the content subtree doesn't
    exist yet" from "it exists but nothing is focused" for browser
    targets - never used for interference/identity decisions."""

    def walk(e, depth: int) -> bool:
        err, role = _copy_attr(e, "AXRole")
        if err == 0 and role == target_role:
            return True
        if depth >= max_depth:
            return False
        err, children = _copy_attr(e, "AXChildren")
        if err != 0 or not children:
            return False
        return any(walk(c, depth + 1) for c in list(children)[:max_children])

    try:
        return walk(element, 0)
    except Exception:
        return None


def _wait_for_ax_bootstrap(ax_app, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """Freshly-launched GUI processes can take a variable, non-zero
    amount of time to register with the WindowServer/AX subsystem at
    all - a basic AXRole read on the top-level application element can
    transiently fail with kAXErrorCannotComplete (-25204) for reasons
    entirely unrelated to the Chrome AXFocusedUIElement gap this module
    investigates (observed directly while building this diagnostic: a
    single unretried read shortly after launch is flaky in exactly this
    way for otherwise-healthy targets). Poll instead of reading once, to
    avoid misattributing ordinary launch-timing noise to the -25212
    finding."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        err, _role = _copy_attr(ax_app, "AXRole")
        if err == 0:
            return True
        time.sleep(interval)
    return False


def _probe_pid(target: str, pid: int, notes: str = "") -> FocusStateProbe:
    observer = MacObserver()
    cursor_before = observer.get_cursor_position()
    _, fg_pid_before = observer.get_foreground_application()

    ax_app = AS.AXUIElementCreateApplication(pid)
    bootstrap_ok = _wait_for_ax_bootstrap(ax_app)
    if not bootstrap_ok:
        notes = (notes + " " if notes else "") + (
            "AX bootstrap: AXRole never succeeded within 5s (WindowServer/AX "
            "connection for this process never came up in this run) - "
            "distinct from the -25212 focus-tree finding."
        )
    supported = _attribute_names(ax_app)

    win_err, win = _copy_attr(ax_app, "AXFocusedWindow")
    elem_err_before, elem_before = _copy_attr(ax_app, "AXFocusedUIElement")

    content_present_before: Optional[bool] = None
    probe_root = win if win_err == 0 and win is not None else ax_app
    content_present_before = _find_role(probe_root, "AXWebArea")

    warm_up_attempted = False
    warm_up_ok: Optional[bool] = None
    elem_err_after: Optional[int] = None
    elem_after = None

    if elem_err_before != 0:
        warm_up_attempted = True
        warm_up_ok = warm_up_ax_focus_tree(pid)
        elem_err_after, elem_after = _copy_attr(ax_app, "AXFocusedUIElement")

    final_err = elem_err_after if warm_up_attempted else elem_err_before
    final_elem = elem_after if warm_up_attempted else elem_before
    role = None
    if final_err == 0 and final_elem is not None:
        r_err, r_val = _copy_attr(final_elem, "AXRole")
        role = r_val if r_err == 0 else None

    cursor_after = observer.get_cursor_position()
    _, fg_pid_after = observer.get_foreground_application()

    from phase0.harness.observers_macos import cursor_moved as _cursor_moved
    from phase0.harness.observers_macos import foreground_changed as _fg_changed

    return FocusStateProbe(
        target=target,
        pid=pid,
        frontmost_pid=int(fg_pid_before.value) if fg_pid_before.available else None,
        ax_trusted=accessibility_trusted(),
        supported_attributes=supported,
        ax_focused_window_error=win_err,
        ax_focused_window_available=(win_err == 0),
        ax_focused_element_error_before=elem_err_before,
        ax_focused_element_available_before=(elem_err_before == 0),
        content_subtree_present_before=content_present_before,
        warm_up_attempted=warm_up_attempted,
        warm_up_succeeded=warm_up_ok,
        ax_focused_element_error_after=elem_err_after,
        ax_focused_element_available_after=(elem_err_after == 0) if elem_err_after is not None else None,
        focused_element_role=role,
        cursor_moved=_cursor_moved(cursor_before, cursor_after),
        foreground_changed=_fg_changed(fg_pid_before, fg_pid_after),
        notes=notes,
    )


class TargetUnavailable(RuntimeError):
    pass


@contextmanager
def _ax_fixture_target() -> Iterator[int]:
    try:
        fixture = launch_fixture()
    except FixtureLaunchError as exc:
        raise TargetUnavailable(str(exc)) from exc
    try:
        yield fixture.pid
    finally:
        fixture.terminate()


@contextmanager
def _disposable_chrome_target() -> Iterator[int]:
    """A throwaway Google Chrome instance with its own temporary
    profile, launched via `open` (proper Launch Services bootstrap - a
    direct subprocess.Popen fork of the Chromium binary was found NOT to
    register with the WindowServer/AX subsystem at all in some sandboxed
    automation contexts; see the diagnostic addendum). Never the
    operator's real Chrome profile/session."""
    chrome_app = Path("/Applications/Google Chrome.app")
    if not chrome_app.exists():
        raise TargetUnavailable("Google Chrome.app not installed")

    profile_dir = tempfile.mkdtemp(prefix="phase0-focus-diag-chrome-")
    proc = subprocess.Popen(
        [
            "open",
            "-na",
            "Google Chrome",
            "--args",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            FIXTURE_PAGE.as_uri(),
        ]
    )
    proc.wait(timeout=10)

    pid = None
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and pid is None:
        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="]).decode()
        for line in out.splitlines():
            line = line.strip()
            if profile_dir in line and "Contents/MacOS/Google Chrome" in line:
                pid = int(line.split(None, 1)[0])
                break
        if pid is None:
            time.sleep(0.2)
    if pid is None:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise TargetUnavailable("disposable Chrome process did not appear within 10s")

    try:
        yield pid
    finally:
        subprocess.run(["kill", str(pid)], check=False)
        time.sleep(0.3)
        shutil.rmtree(profile_dir, ignore_errors=True)


@contextmanager
def _safari_target() -> Iterator[int]:
    safari_app = Path("/Applications/Safari.app")
    if not safari_app.exists():
        raise TargetUnavailable("Safari.app not installed")

    was_running = bool(AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.apple.Safari"))
    subprocess.run(["open", "-a", "Safari", FIXTURE_PAGE.as_uri()], check=True)

    pid = None
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and pid is None:
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.apple.Safari")
        if apps:
            pid = apps[0].processIdentifier()
        else:
            time.sleep(0.2)
    if pid is None:
        raise TargetUnavailable("Safari did not appear within 10s")

    try:
        yield pid
    finally:
        if not was_running:
            subprocess.run(["osascript", "-e", 'tell application "Safari" to quit'], check=False)


@contextmanager
def _playwright_chromium_target() -> Iterator[int]:
    """Chromium launched via Playwright's own `.launch(headless=False)`.
    Included because BUILD_SPEC/README name this as the actual campaign
    target - but see the diagnostic addendum: in some sandboxed
    automation contexts this process never registers a WindowServer-
    visible window at all (every AX attribute, including AXRole, returns
    kAXErrorCannotComplete), which is a distinct failure mode from the
    Chrome -25212 gap this module otherwise investigates. Reported
    honestly as TargetUnavailable in that case, never conflated with the
    -25212 finding."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise TargetUnavailable(f"playwright not importable: {exc}") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            page.goto(FIXTURE_PAGE.as_uri())
            time.sleep(0.5)

            out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="]).decode()
            pid = None
            for line in out.splitlines():
                if "Contents/MacOS/Google Chrome for Testing" in line and "--type=" not in line:
                    pid = int(line.strip().split(None, 1)[0])
                    break
            if pid is None:
                raise TargetUnavailable("could not identify playwright chromium's main process pid")

            # Confirm it is actually AX-reachable at all before handing
            # it to the shared probe; if not, surface that distinctly.
            ax_app = AS.AXUIElementCreateApplication(pid)
            err, _role = _copy_attr(ax_app, "AXRole")
            if err != 0:
                raise TargetUnavailable(
                    f"playwright chromium (pid {pid}) is not AX-reachable in this environment: "
                    f"AXRole read failed with AX error {err} (likely no WindowServer session for this process)"
                )
            yield pid
        finally:
            browser.close()


def run_diagnostics() -> List[FocusStateProbe]:
    if not is_macos() or not pyobjc_available():
        raise TargetUnavailable("focus diagnostics require macOS with pyobjc available")
    if not accessibility_trusted():
        raise TargetUnavailable("Accessibility permission not granted")

    results: List[FocusStateProbe] = []

    for label, builder in [
        ("cocoa_ax_fixture", _ax_fixture_target),
        ("playwright_chromium", _playwright_chromium_target),
        ("disposable_chrome", _disposable_chrome_target),
        ("safari", _safari_target),
    ]:
        try:
            with builder() as pid:
                results.append(_probe_pid(label, pid))
        except TargetUnavailable as exc:
            results.append(
                FocusStateProbe(
                    target=label,
                    pid=None,
                    frontmost_pid=None,
                    ax_trusted=accessibility_trusted(),
                    supported_attributes=None,
                    ax_focused_window_error=None,
                    ax_focused_window_available=None,
                    ax_focused_element_error_before=None,
                    ax_focused_element_available_before=None,
                    content_subtree_present_before=None,
                    warm_up_attempted=False,
                    warm_up_succeeded=None,
                    ax_focused_element_error_after=None,
                    ax_focused_element_available_after=None,
                    focused_element_role=None,
                    cursor_moved=None,
                    foreground_changed=None,
                    notes=f"TARGET_UNAVAILABLE: {exc}",
                )
            )

    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=None, help="write JSON results to this path")
    args = parser.parse_args(argv)

    results = run_diagnostics()
    payload = [asdict(r) for r in results]
    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
