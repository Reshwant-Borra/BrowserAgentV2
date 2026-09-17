"""Launches and tears down the deterministic AX fixture app
(phase0/fixtures/mac_ax_fixture_app.py) as a child process."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

FIXTURE_SCRIPT = Path(__file__).resolve().parents[2] / "fixtures" / "mac_ax_fixture_app.py"


class FixtureLaunchError(RuntimeError):
    pass


@dataclass
class FixtureHandle:
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


def launch_fixture(ready_timeout: float = 10.0) -> FixtureHandle:
    """Starts the fixture app and blocks until it reports readiness."""
    if not FIXTURE_SCRIPT.exists():
        raise FixtureLaunchError(f"fixture script not found: {FIXTURE_SCRIPT}")

    process = subprocess.Popen(
        [sys.executable, str(FIXTURE_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise FixtureLaunchError(f"fixture process exited early (code {process.returncode}): {stderr}")
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
                raise FixtureLaunchError("fixture reported ready without a pid")
            return FixtureHandle(process=process, pid=int(pid))

    process.kill()
    raise FixtureLaunchError(f"fixture did not report readiness within {ready_timeout}s")
