"""Shared fixtures/helpers for Phase 0 harness unit tests.

None of these tests control the real desktop: all observers are faked.
Real-machine experiments live under tests/phase0/integration/ and are
marked `integration`.
"""

from __future__ import annotations

import itertools
from typing import Iterable

import pytest

from phase0.harness.observers_macos import SystemSnapshot
from phase0.schemas.evidence import Measurement


class FakeObserver:
    """Replays a fixed sequence of `SystemSnapshot`s, one per call to
    `snapshot()`. Never touches the real desktop."""

    def __init__(self, snapshots: Iterable[SystemSnapshot]):
        self._snapshots = iter(snapshots)

    def snapshot(self, pid=None) -> SystemSnapshot:
        try:
            return next(self._snapshots)
        except StopIteration as exc:
            raise AssertionError("FakeObserver.snapshot() called more times than snapshots provided") from exc


def make_snapshot(
    *,
    cursor=(100.0, 200.0),
    cursor_available=True,
    app="TestApp",
    app_available=True,
    window="Test Window",
    window_available=True,
    element_role="AXTextField",
    element_subrole=None,
    element_identifier=None,
    # Non-None by default so two default snapshots corroborate as the
    # *same* element (role alone is deliberately not enough - see
    # `observers_macos._element_identity_changed`). Tests that need to
    # exercise ambiguous/indistinguishable elements pass None explicitly.
    element_title="Test Field",
    element_description=None,
    element_help=None,
    element_position=(50.0, 50.0),
    element_size=(200.0, 24.0),
    element_value=None,
    element_available=True,
) -> SystemSnapshot:
    cursor_m = (
        Measurement.of({"x": cursor[0], "y": cursor[1]}) if cursor_available else Measurement.unavailable("test: cursor unavailable")
    )
    app_m = (
        Measurement.of({"name": app, "bundle_id": f"com.test.{app}"})
        if app_available
        else Measurement.unavailable("test: app unavailable")
    )
    pid_m = Measurement.of(1234) if app_available else Measurement.unavailable("test: pid unavailable")
    window_m = (
        Measurement.of({"title": window}) if window_available else Measurement.unavailable("test: window unavailable")
    )
    position = {"x": element_position[0], "y": element_position[1]} if element_position is not None else None
    size = {"width": element_size[0], "height": element_size[1]} if element_size is not None else None
    element_m = (
        Measurement.of(
            {
                "role": element_role,
                "subrole": element_subrole,
                "identifier": element_identifier,
                "title": element_title,
                "description": element_description,
                "help": element_help,
                "position": position,
                "size": size,
                "value": element_value,
                "value_length": len(element_value) if element_value is not None else None,
                "value_truncated": False,
            }
        )
        if element_available
        else Measurement.unavailable("test: element unavailable")
    )
    return SystemSnapshot(
        cursor=cursor_m,
        foreground_app=app_m,
        foreground_pid=pid_m,
        focused_window=window_m,
        focused_element=element_m,
    )


@pytest.fixture
def fake_observer_factory():
    def _factory(*snapshots: SystemSnapshot) -> FakeObserver:
        return FakeObserver(snapshots)

    return _factory
