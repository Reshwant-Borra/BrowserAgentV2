"""Launches/tears down the occlusion overlay fixture
(phase0/fixtures/overlay_window_app.py) as a child process.

Shared by the browser and macOS AX campaigns' "occluded target" condition.
Mirrors phase0/experiments/macos_ax/fixture_process.py's readiness
protocol (a single `{"ready": true, "pid": ...}` JSON line on stdout).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

OVERLAY_SCRIPT = Path(__file__).resolve().parents[1] / "fixtures" / "overlay_window_app.py"


class OverlayLaunchError(RuntimeError):
    pass


@dataclass
class OverlayHandle:
    process: subprocess.Popen
    pid: int

    def terminate(self, timeout: float = 3.0) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)


def launch_overlay(ready_timeout: float = 10.0) -> OverlayHandle:
    if not OVERLAY_SCRIPT.exists():
        raise OverlayLaunchError(f"overlay script not found: {OVERLAY_SCRIPT}")

    process = subprocess.Popen(
        [sys.executable, str(OVERLAY_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise OverlayLaunchError(f"overlay process exited early (code {process.returncode}): {stderr}")
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            time.sleep(0.05)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("ready"):
            pid: Optional[int] = payload.get("pid")
            if pid is None:
                raise OverlayLaunchError("overlay reported ready without a pid")
            return OverlayHandle(process=process, pid=int(pid))

    process.kill()
    raise OverlayLaunchError(f"overlay did not report readiness within {ready_timeout}s")
