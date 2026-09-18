"""Representative real-application targets for the Mac Application
Capability Matrix, and how to safely attach to (or launch a disposable
instance of) each one.

Safety posture per docs/BUILD_SPEC.md section 3 / this milestone's
instructions:
- Never installs a third-party application.
- Never logs into a service, opens real user documents/notes/events, or
  navigates System Settings into a specific pane.
- Real-app scratch interaction (Safari/Chrome/Electron) always targets a
  disposable/local resource (the existing `phase0/fixtures` HTML pages,
  or a brand-new empty window), never the user's real profile content.
- Finder is pointed at this repository's own directory (already fully
  readable by the harness) rather than a personal folder.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from phase0.schemas.app_capability import AppArchitecture

try:
    import AppKit

    _APPKIT_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    _APPKIT_AVAILABLE = False

FIXTURE_PAGE = (Path(__file__).resolve().parents[2] / "fixtures" / "browser_page1.html").resolve()
REPO_ROOT = Path(__file__).resolve().parents[3]


class TargetUnavailable(RuntimeError):
    """Raised when a target cannot be attached to/launched at all -
    callers must record this as NOT_INSTALLED/BLOCKED, never fabricate a
    pid."""


def app_installed(bundle_id: str) -> bool:
    if not _APPKIT_AVAILABLE:
        return False
    url = AppKit.NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)
    return url is not None


def running_pid_for_bundle_id(bundle_id: str) -> Optional[int]:
    if not _APPKIT_AVAILABLE:
        return None
    apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    if not apps:
        return None
    return int(apps[0].processIdentifier())


def _wait_for_pid(bundle_id: str, timeout: float = 12.0, interval: float = 0.2) -> Optional[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = running_pid_for_bundle_id(bundle_id)
        if pid is not None:
            return pid
        time.sleep(interval)
    return None


@dataclass
class ResolvedTarget:
    """What a target resolver hands back: a live pid plus whether this
    probe run launched it (so teardown only ever closes what it opened,
    never an application the user already had running)."""

    pid: int
    launched_by_probe: bool
    launched_scratch_window: bool = False


@contextmanager
def _attach_or_launch(bundle_id: str, open_args: Optional[list] = None) -> Iterator[ResolvedTarget]:
    """Attaches to an already-running app, or launches it via `open` if
    not running. Never terminates an app the probe did not itself start
    (per-app resolvers below own any scratch-window-specific teardown;
    this only decides process-level launch bookkeeping)."""
    if not app_installed(bundle_id):
        raise TargetUnavailable(f"{bundle_id} is not installed")

    existing_pid = running_pid_for_bundle_id(bundle_id)
    if existing_pid is not None:
        yield ResolvedTarget(pid=existing_pid, launched_by_probe=False)
        return

    cmd = ["open", "-b", bundle_id]
    if open_args:
        cmd += ["--args", *open_args]
    subprocess.run(cmd, check=False)
    pid = _wait_for_pid(bundle_id)
    if pid is None:
        raise TargetUnavailable(f"{bundle_id} did not appear within timeout after launch")
    yield ResolvedTarget(pid=pid, launched_by_probe=True)
    # Deliberately does not terminate: these are real user applications
    # (Finder/Notes/Calendar/System Settings) that must not be quit out
    # from under the user just because the probe started them.


@contextmanager
def finder_target() -> Iterator[ResolvedTarget]:
    """Finder is always running and cannot meaningfully be "launched" -
    this only ensures a window is open, pointed at this repository's own
    directory (not a personal folder) so tree traversal has something to
    inspect."""
    if not app_installed("com.apple.finder"):
        raise TargetUnavailable("com.apple.finder not installed")
    pid = running_pid_for_bundle_id("com.apple.finder")
    if pid is None:
        raise TargetUnavailable("Finder is not running (unexpected on macOS)")
    subprocess.run(["open", "-a", "Finder", str(REPO_ROOT)], check=False)
    time.sleep(0.5)
    yield ResolvedTarget(pid=pid, launched_by_probe=False, launched_scratch_window=True)


@contextmanager
def notes_target() -> Iterator[ResolvedTarget]:
    with _attach_or_launch("com.apple.Notes") as resolved:
        yield resolved


@contextmanager
def calendar_target() -> Iterator[ResolvedTarget]:
    with _attach_or_launch("com.apple.iCal") as resolved:
        yield resolved


@contextmanager
def system_settings_target() -> Iterator[ResolvedTarget]:
    with _attach_or_launch("com.apple.systempreferences") as resolved:
        yield resolved


@contextmanager
def safari_target() -> Iterator[ResolvedTarget]:
    """Opens the local, network-free fixture page in a *new* Safari
    window rather than touching any existing user window/tab."""
    if not app_installed("com.apple.Safari"):
        raise TargetUnavailable("com.apple.Safari not installed")
    was_running = running_pid_for_bundle_id("com.apple.Safari") is not None
    subprocess.run(["open", "-a", "Safari", FIXTURE_PAGE.as_uri()], check=True)
    pid = _wait_for_pid("com.apple.Safari")
    if pid is None:
        raise TargetUnavailable("Safari did not appear within timeout")
    time.sleep(0.5)
    yield ResolvedTarget(pid=pid, launched_by_probe=not was_running, launched_scratch_window=True)


@contextmanager
def disposable_chrome_target() -> Iterator[ResolvedTarget]:
    """A throwaway Google Chrome instance with its own temporary
    profile - never the operator's real Chrome profile/session. Mirrors
    phase0/experiments/macos_ax/focus_diagnostics.py's
    `_disposable_chrome_target`."""
    chrome_app = Path("/Applications/Google Chrome.app")
    if not chrome_app.exists():
        raise TargetUnavailable("Google Chrome.app not installed")

    profile_dir = tempfile.mkdtemp(prefix="phase0-mac-app-caps-chrome-")
    subprocess.Popen(
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
    ).wait(timeout=10)

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
        yield ResolvedTarget(pid=pid, launched_by_probe=True, launched_scratch_window=True)
    finally:
        subprocess.run(["kill", str(pid)], check=False)
        time.sleep(0.3)
        shutil.rmtree(profile_dir, ignore_errors=True)


@contextmanager
def vscode_target() -> Iterator[ResolvedTarget]:
    """A brand-new, folder-less VS Code window (no project/files opened)
    - an Electron representative with no real user documents touched."""
    app_path = Path("/Applications/Visual Studio Code.app")
    if not app_path.exists():
        raise TargetUnavailable("Visual Studio Code.app not installed")
    was_running = running_pid_for_bundle_id("com.microsoft.VSCode") is not None
    subprocess.run(["open", "-na", "Visual Studio Code", "--args", "--new-window"], check=False)
    pid = _wait_for_pid("com.microsoft.VSCode")
    if pid is None:
        raise TargetUnavailable("Visual Studio Code did not appear within timeout")
    time.sleep(1.0)
    yield ResolvedTarget(pid=pid, launched_by_probe=not was_running, launched_scratch_window=True)


TARGET_SPECS = [
    ("finder", "Finder", "com.apple.finder", AppArchitecture.COCOA, finder_target),
    ("notes", "Notes", "com.apple.Notes", AppArchitecture.SWIFTUI, notes_target),
    ("calendar", "Calendar", "com.apple.iCal", AppArchitecture.COCOA, calendar_target),
    (
        "system_settings",
        "System Settings",
        "com.apple.systempreferences",
        AppArchitecture.SWIFTUI,
        system_settings_target,
    ),
    ("safari", "Safari", "com.apple.Safari", AppArchitecture.WEBKIT, safari_target),
    ("chrome", "Google Chrome", "com.google.Chrome", AppArchitecture.CHROMIUM, disposable_chrome_target),
    ("vscode", "Visual Studio Code", "com.microsoft.VSCode", AppArchitecture.ELECTRON, vscode_target),
]
