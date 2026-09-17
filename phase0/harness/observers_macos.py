"""macOS system-state observers used to measure interference.

These observers use only public, non-invasive APIs:

- `Quartz.CGEventGetLocation` for the physical cursor position (reads the
  current event location; does not synthesize input).
- `AppKit.NSWorkspace` for the frontmost application (no special
  permission required).
- `ApplicationServices` AXUIElement calls for the focused window/element
  of a given application (requires the macOS Accessibility permission).

This module never requests or attempts to bypass a permission. When a
capability is unavailable it returns `Measurement.unavailable(reason)`
rather than raising or fabricating a value.
"""

from __future__ import annotations

import platform as _platform
from dataclasses import dataclass
from typing import List, Optional, Tuple

from phase0.schemas.evidence import Measurement

try:
    import AppKit
    import ApplicationServices as AS
    import Quartz

    _PYOBJC_AVAILABLE = True
    _PYOBJC_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - exercised on non-macOS/no pyobjc
    Quartz = None  # type: ignore[assignment]
    AppKit = None  # type: ignore[assignment]
    AS = None  # type: ignore[assignment]
    _PYOBJC_AVAILABLE = False
    _PYOBJC_IMPORT_ERROR = str(exc)


def is_macos() -> bool:
    return _platform.system() == "Darwin"


def pyobjc_available() -> bool:
    return _PYOBJC_AVAILABLE


def pyobjc_import_error() -> Optional[str]:
    return _PYOBJC_IMPORT_ERROR


def accessibility_trusted() -> bool:
    """Whether this process currently holds the Accessibility permission.

    Never prompts the user and never attempts to bypass the OS
    permission system.
    """
    if not _PYOBJC_AVAILABLE:
        return False
    try:
        return bool(AS.AXIsProcessTrusted())
    except Exception:
        return False


_MAX_CAPTURED_VALUE_CHARS = 200


def _bounded_value_fields(value_str: Optional[str]) -> dict:
    """Bounds a captured AXValue string for safe persistence: full
    arbitrary application content (e.g. a terminal's scrollback, a
    document's text) must never be written verbatim into an evidence
    file. Returns dict with `value` (possibly truncated), `value_length`,
    and `value_truncated`."""
    if value_str is None:
        return {"value": None, "value_length": None, "value_truncated": False}
    truncated = len(value_str) > _MAX_CAPTURED_VALUE_CHARS
    return {
        "value": value_str[:_MAX_CAPTURED_VALUE_CHARS],
        "value_length": len(value_str),
        "value_truncated": truncated,
    }


@dataclass(frozen=True)
class SystemSnapshot:
    """A point-in-time bundle of everything the runner needs to compare
    before/after state for interference detection."""

    cursor: Measurement
    foreground_app: Measurement
    foreground_pid: Measurement
    focused_window: Measurement
    focused_element: Measurement


class MacObserver:
    """Read-only observer of macOS system state. Makes no state-changing
    calls of its own."""

    def get_cursor_position(self) -> Measurement:
        if not _PYOBJC_AVAILABLE:
            return Measurement.unavailable(f"pyobjc unavailable: {_PYOBJC_IMPORT_ERROR}")
        try:
            event = Quartz.CGEventCreate(None)
            loc = Quartz.CGEventGetLocation(event)
            return Measurement.of({"x": float(loc.x), "y": float(loc.y)})
        except Exception as exc:
            return Measurement.unavailable(f"CGEventGetLocation failed: {exc}")

    def get_foreground_application(self) -> Tuple[Measurement, Measurement]:
        """Returns (app_measurement, pid_measurement)."""
        if not _PYOBJC_AVAILABLE:
            reason = f"pyobjc unavailable: {_PYOBJC_IMPORT_ERROR}"
            return Measurement.unavailable(reason), Measurement.unavailable(reason)
        try:
            ws = AppKit.NSWorkspace.sharedWorkspace()
            app = ws.frontmostApplication()
            if app is None:
                reason = "NSWorkspace reported no frontmost application"
                return Measurement.unavailable(reason), Measurement.unavailable(reason)
            name = app.localizedName()
            bundle_id = app.bundleIdentifier()
            pid = app.processIdentifier()
            return (
                Measurement.of(
                    {
                        "name": str(name) if name else None,
                        "bundle_id": str(bundle_id) if bundle_id else None,
                    }
                ),
                Measurement.of(int(pid)),
            )
        except Exception as exc:
            reason = f"NSWorkspace query failed: {exc}"
            return Measurement.unavailable(reason), Measurement.unavailable(reason)

    def get_focused_window_and_element(
        self, pid: Optional[int] = None
    ) -> Tuple[Measurement, Measurement]:
        """Returns (focused_window_measurement, focused_element_measurement)
        for `pid`'s application (defaults to the current frontmost
        application). Requires the Accessibility permission.
        """
        if not _PYOBJC_AVAILABLE:
            reason = f"pyobjc unavailable: {_PYOBJC_IMPORT_ERROR}"
            return Measurement.unavailable(reason), Measurement.unavailable(reason)
        if not accessibility_trusted():
            reason = "accessibility_permission_not_granted"
            return Measurement.unavailable(reason), Measurement.unavailable(reason)

        try:
            resolved_pid = pid
            if resolved_pid is None:
                ws = AppKit.NSWorkspace.sharedWorkspace()
                app = ws.frontmostApplication()
                if app is None:
                    reason = "NSWorkspace reported no frontmost application"
                    return Measurement.unavailable(reason), Measurement.unavailable(reason)
                resolved_pid = int(app.processIdentifier())

            ax_app = AS.AXUIElementCreateApplication(resolved_pid)
            window_measurement = self._read_window(ax_app)
            element_measurement = self._read_focused_element(ax_app)
            return window_measurement, element_measurement
        except Exception as exc:
            reason = f"AX query failed: {exc}"
            return Measurement.unavailable(reason), Measurement.unavailable(reason)

    def _read_window(self, ax_app) -> Measurement:
        err, window = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedWindow", None)
        if err != 0 or window is None:
            return Measurement.unavailable(f"AX error {err} reading AXFocusedWindow")
        title_err, title = AS.AXUIElementCopyAttributeValue(window, "AXTitle", None)
        return Measurement.of({"title": str(title) if title_err == 0 and title is not None else None})

    def _read_focused_element(self, ax_app) -> Measurement:
        err, elem = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", None)
        if err != 0 or elem is None:
            return Measurement.unavailable(f"AX error {err} reading AXFocusedUIElement")
        role_err, role = AS.AXUIElementCopyAttributeValue(elem, "AXRole", None)
        value_err, value = AS.AXUIElementCopyAttributeValue(elem, "AXValue", None)
        title_err, title = AS.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
        value_str = str(value) if value_err == 0 and value is not None else None
        return Measurement.of(
            {
                "role": str(role) if role_err == 0 and role is not None else None,
                "title": str(title) if title_err == 0 and title is not None else None,
                # AXValue can be unboundedly large (e.g. a terminal's
                # entire scrollback) and may contain sensitive content
                # from an unrelated application. Cap what we persist to
                # evidence files; identity/interference decisions below
                # never depend on this field, only on role+title.
                **_bounded_value_fields(value_str),
            }
        )

    def snapshot(self, pid: Optional[int] = None) -> SystemSnapshot:
        """Capture full system state. If `pid` is given, focused
        window/element are read for that process; otherwise for whichever
        application is currently frontmost."""
        cursor = self.get_cursor_position()
        foreground_app, foreground_pid = self.get_foreground_application()
        target_pid = pid if pid is not None else (foreground_pid.value if foreground_pid.available else None)
        focused_window, focused_element = self.get_focused_window_and_element(target_pid)
        return SystemSnapshot(
            cursor=cursor,
            foreground_app=foreground_app,
            foreground_pid=foreground_pid,
            focused_window=focused_window,
            focused_element=focused_element,
        )


def _values_differ(before: Measurement, after: Measurement) -> Optional[bool]:
    if not before.available or not after.available:
        return None
    return before.value != after.value


def cursor_moved(before: Measurement, after: Measurement, tolerance_px: float = 0.5) -> Optional[bool]:
    if not before.available or not after.available:
        return None
    try:
        dx = float(before.value["x"]) - float(after.value["x"])
        dy = float(before.value["y"]) - float(after.value["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (dx * dx + dy * dy) ** 0.5 > tolerance_px


def foreground_changed(before: Measurement, after: Measurement) -> Optional[bool]:
    return _values_differ(before, after)


def _element_identity(element: Measurement) -> Optional[tuple]:
    """Identity of a focused element for change detection: (role, title)
    only. Deliberately excludes AXValue - an element's *content* (e.g. a
    terminal's scrollback, a growing log) can legitimately change without
    focus moving anywhere, and treating content drift as a focus change
    would produce false-positive FOCUS_INTERFERENCE classifications."""
    if not element.available:
        return None
    value = element.value or {}
    return (value.get("role"), value.get("title"))


def focus_changed(
    window_before: Measurement,
    window_after: Measurement,
    element_before: Measurement,
    element_after: Measurement,
) -> Optional[bool]:
    window_diff = _values_differ(window_before, window_after)

    identity_before = _element_identity(element_before)
    identity_after = _element_identity(element_after)
    element_diff = None if identity_before is None or identity_after is None else identity_before != identity_after

    if window_diff is None and element_diff is None:
        return None
    return bool(window_diff) or bool(element_diff)
