"""Cheap, platform-portable environment/hardware metadata for evidence
records. Deliberately minimal: Phase 0's full HardwareProfiler (GPU,
VRAM, thermal, etc.) is a separate workstream (see docs/BUILD_SPEC.md
section 1) and is not built here. This module only captures what's
cheap to obtain and useful for interpreting non-interference results.
"""

from __future__ import annotations

import os
import platform as _platform
from datetime import datetime, timezone

from phase0.schemas.evidence import Measurement, Platform


def current_platform() -> Platform:
    system = _platform.system()
    if system == "Darwin":
        return Platform.MACOS
    if system == "Windows":
        return Platform.WINDOWS
    if system == "Linux":
        return Platform.LINUX
    return Platform.UNKNOWN


def get_os_version_measurement() -> Measurement:
    try:
        system = _platform.system()
        if system == "Darwin":
            release, _, _ = _platform.mac_ver()
            if not release:
                return Measurement.unavailable("platform.mac_ver() returned empty release")
            return Measurement.of(release)
        version = _platform.version()
        if not version:
            return Measurement.unavailable(f"platform.version() returned empty string on {system}")
        return Measurement.of(version)
    except Exception as exc:
        return Measurement.unavailable(f"platform version lookup failed: {exc}")


def get_cheap_hardware_metadata() -> dict:
    """Best-effort, cheap-to-obtain metadata. Any field that cannot be
    determined is simply omitted (never fabricated)."""
    metadata: dict = {
        "machine": _platform.machine(),
        "processor": _platform.processor() or None,
        "python_version": _platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    return {k: v for k, v in metadata.items() if v is not None}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
