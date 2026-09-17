"""Positive control: an action KNOWN to move the physical cursor.

This exists solely to prove the measurement harness can actually detect
interference (see the Phase 0 milestone instructions, section 5). It is
not part of the browser or AX experiments and must never run as part of
an ordinary test/experiment sweep - only via explicit invocation
(`python -m phase0 control`).

It warps the physical cursor a short, visible distance and back. It is
reversible and non-destructive, but it IS visibly disruptive while it
runs (the cursor will jump), which is the entire point: it is the
control condition proving CURSOR_INTERFERENCE gets detected when
interference actually occurs.
"""

from __future__ import annotations

from phase0.harness.observers_macos import MacObserver
from phase0.harness.runner import ActionSpec
from phase0.schemas.evidence import ActionMechanism, Measurement

try:
    import Quartz

    _QUARTZ_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    Quartz = None  # type: ignore[assignment]
    _QUARTZ_AVAILABLE = False


def _warp_cursor_by(dx: float, dy: float, observer: MacObserver) -> dict:
    if not _QUARTZ_AVAILABLE:
        raise RuntimeError("Quartz is unavailable; cannot run the positive control on this platform")
    before = observer.get_cursor_position()
    if not before.available:
        raise RuntimeError(f"cannot read current cursor position: {before.reason}")
    x, y = before.value["x"], before.value["y"]
    target = Quartz.CGPoint(x + dx, y + dy)
    Quartz.CGWarpMouseCursorPosition(target)
    return {"from": {"x": x, "y": y}, "to": {"x": target.x, "y": target.y}}


def build_positive_control_spec(observer: MacObserver, dx: float = 80.0, dy: float = 0.0) -> ActionSpec:
    """An `ActionSpec` that deliberately warps the physical cursor by
    (dx, dy) pixels, to validate that the harness detects
    CURSOR_INTERFERENCE when interference actually occurs."""

    def execute():
        return _warp_cursor_by(dx, dy, observer)

    def verify(result):
        after = observer.get_cursor_position()
        if not after.available:
            return None, Measurement.unavailable(f"could not read cursor after warp: {after.reason}")
        expected = result["to"]
        actual = after.value
        close = abs(expected["x"] - actual["x"]) < 1.0 and abs(expected["y"] - actual["y"]) < 1.0
        return close, Measurement.of({"expected": expected, "actual": actual})

    return ActionSpec(
        action_type="positive_control_cursor_warp",
        action_mechanism=ActionMechanism.PHYSICAL_INPUT_INJECTION,
        expected_postcondition=f"cursor moves by ({dx}, {dy}) pixels",
        execute=execute,
        verify=verify,
        target_application=Measurement.of("harness_self_test"),
    )
