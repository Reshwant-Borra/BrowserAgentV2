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
import time
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


def warm_up_ax_focus_tree(pid: int, timeout: float = 2.0, poll_interval: float = 0.2) -> bool:
    """Triggers a target process's on-demand accessibility tree via the
    standard public AT-detection mechanism, then immediately tears the
    trigger back down.

    Some applications - most notably Chromium-based browsers (Google
    Chrome, and by extension any Electron app), and generally anything
    that lazily builds its accessibility tree - do not populate
    AXFocusedUIElement (AX error -25212 / kAXErrorNoValue) until the OS
    signals that a real assistive-technology client is attached. A
    single AXUIElementCopyAttributeValue read from a foreign process
    does not trigger that signal; registering an AXObserver notification
    does (this is the same public mechanism VoiceOver and other real ATs
    use - see `phase0/CAMPAIGN_REPORT.md`'s focus-observation addendum
    for the diagnostic evidence this was derived from).

    This function only creates/removes an AXObserver notification
    registration - it never moves the physical cursor, changes the
    frontmost application, or injects synthetic input, and it works
    against a fully backgrounded target. Its one disclosed side effect:
    once triggered, the target's accessibility mode typically stays
    enabled for the remainder of that process's lifetime (Chromium
    documents a small, persistent CPU overhead from this - not a
    functional behavior change).

    Returns True once AXFocusedUIElement becomes readable (a non-error
    read, whether or not it currently has a focused element), False if
    that does not happen within `timeout` seconds. Never raises for an
    ordinary AX failure - a warm-up that doesn't help is a normal,
    reportable outcome, not an error.
    """
    if not _PYOBJC_AVAILABLE or not accessibility_trusted():
        return False
    try:
        import objc

        ax_app = AS.AXUIElementCreateApplication(pid)

        err0, elem0 = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", None)
        if err0 == 0:
            return True  # already warm; nothing to do

        @objc.callbackFor(AS.AXObserverCreate)
        def _on_notification(observer, element, notification, refcon):  # pragma: no cover
            # Never expected to fire synchronously within this function's
            # short-lived run loop pump; the registration side effect
            # (not the callback) is what wakes the target up.
            pass

        create_err, observer = AS.AXObserverCreate(pid, _on_notification, None)
        if create_err != 0 or observer is None:
            return False

        reg_err = AS.AXObserverAddNotification(observer, ax_app, "AXFocusedUIElementChanged", None)
        if reg_err != 0:
            return False

        run_loop = None
        source = None
        try:
            import Quartz

            source = AS.AXObserverGetRunLoopSource(observer)
            run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(run_loop, source, Quartz.kCFRunLoopDefaultMode)

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, poll_interval, False)
                err, elem = AS.AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", None)
                if err == 0:
                    return True
            return False
        finally:
            AS.AXObserverRemoveNotification(observer, ax_app, "AXFocusedUIElementChanged")
            if run_loop is not None and source is not None:
                Quartz.CFRunLoopRemoveSource(run_loop, source, Quartz.kCFRunLoopDefaultMode)
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


def _decode_ax_point(ax_value) -> Optional[dict]:
    """Decodes an AXValueRef of type CGPoint (e.g. AXPosition). Returns
    None if the attribute was absent or could not be decoded - never a
    fabricated coordinate."""
    if ax_value is None or not _PYOBJC_AVAILABLE:
        return None
    try:
        ok, point = AS.AXValueGetValue(ax_value, AS.kAXValueCGPointType, None)
    except Exception:
        return None
    if not ok or point is None:
        return None
    try:
        return {"x": round(float(point.x), 1), "y": round(float(point.y), 1)}
    except (AttributeError, TypeError, ValueError):
        return None


def _decode_ax_size(ax_value) -> Optional[dict]:
    """Decodes an AXValueRef of type CGSize (e.g. AXSize). Returns None if
    the attribute was absent or could not be decoded."""
    if ax_value is None or not _PYOBJC_AVAILABLE:
        return None
    try:
        ok, size = AS.AXValueGetValue(ax_value, AS.kAXValueCGSizeType, None)
    except Exception:
        return None
    if not ok or size is None:
        return None
    try:
        return {"width": round(float(size.width), 1), "height": round(float(size.height), 1)}
    except (AttributeError, TypeError, ValueError):
        return None


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

        def _attr(attribute: str):
            a_err, a_val = AS.AXUIElementCopyAttributeValue(elem, attribute, None)
            return a_val if a_err == 0 else None

        def _str_attr(attribute: str) -> Optional[str]:
            val = _attr(attribute)
            return str(val) if val is not None else None

        value = _attr("AXValue")
        value_str = str(value) if value is not None else None

        return Measurement.of(
            {
                "role": _str_attr("AXRole"),
                # Identity signals beyond (role, title): a fixed pair of
                # role+title is not unique (e.g. two untitled
                # AXTextFields), so additional stable, public AX metadata
                # is captured to disambiguate distinct elements that would
                # otherwise look identical. See
                # `_element_identity_changed` for how these combine into
                # a conservative same/different/unknown verdict.
                "subrole": _str_attr("AXSubrole"),
                "identifier": _str_attr("AXIdentifier"),
                "title": _str_attr("AXTitle"),
                "description": _str_attr("AXDescription"),
                "help": _str_attr("AXHelp"),
                "position": _decode_ax_point(_attr("AXPosition")),
                "size": _decode_ax_size(_attr("AXSize")),
                # AXValue can be unboundedly large (e.g. a terminal's
                # entire scrollback) and may contain sensitive content
                # from an unrelated application. Cap what we persist to
                # evidence files; identity/interference decisions below
                # never depend on this field.
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


_GEOMETRY_TOLERANCE_PX = 1.0

# Fields compared as exact string identity when both sides expose them.
# AXIdentifier is the closest thing macOS AX has to a stable per-instance
# id; title/description/help are semantic labels, not content. AXValue is
# deliberately excluded (see `_element_identity_changed`).
_IDENTITY_LABEL_FIELDS: Tuple[str, ...] = ("identifier", "title", "description", "help")


def _geometry_distance(a: Optional[dict], b: Optional[dict], keys: Tuple[str, str]) -> Optional[float]:
    if not a or not b:
        return None
    try:
        d0 = float(a[keys[0]]) - float(b[keys[0]])
        d1 = float(a[keys[1]]) - float(b[keys[1]])
    except (KeyError, TypeError, ValueError):
        return None
    return (d0 * d0 + d1 * d1) ** 0.5


def _geometry_matches(position_before, position_after, size_before, size_after) -> Optional[bool]:
    """True if position+size are both available and within tolerance on
    both sides, False if both available and clearly apart, None if not
    comparable (e.g. one side never exposed geometry)."""
    pos_dist = _geometry_distance(position_before, position_after, ("x", "y"))
    size_dist = _geometry_distance(size_before, size_after, ("width", "height"))
    if pos_dist is None or size_dist is None:
        return None
    return pos_dist <= _GEOMETRY_TOLERANCE_PX and size_dist <= _GEOMETRY_TOLERANCE_PX


def _element_identity_changed(before: Measurement, after: Measurement) -> Optional[bool]:
    """Conservative same-element check for a focused UI element, using
    (role, subrole, AXIdentifier, title, description, help, geometry) -
    never AXValue.

    A bare (role, title) match is not unique: two distinct, untitled
    AXTextFields compare equal on that pair alone, which previously
    produced a false-negative (missed) FOCUS_INTERFERENCE. This adds
    further public, non-content AX signals so such elements can be told
    apart, while still refusing to call two elements "the same" on role
    alone.

    Returns:
      True  - a stable identity signal (role, subrole, identifier,
              title, description, help, or geometry) explicitly
              mismatches: these are different elements.
      False - role matches *and* at least one other identity signal
              (identifier/title/description/help match, or geometry is
              within tolerance) corroborates sameness.
      None  - available signals do not clear the bar for either verdict
              (e.g. only role is comparable, or an element became
              unavailable). Callers must treat this as unknown, never as
              evidence of BACKGROUND_SAFE.
    """
    if not before.available or not after.available:
        return None

    b = before.value or {}
    a = after.value or {}

    role_before, role_after = b.get("role"), a.get("role")
    if role_before is not None and role_after is not None and role_before != role_after:
        return True

    subrole_before, subrole_after = b.get("subrole"), a.get("subrole")
    if subrole_before is not None and subrole_after is not None and subrole_before != subrole_after:
        return True

    corroborations = 0
    for field_name in _IDENTITY_LABEL_FIELDS:
        v_before, v_after = b.get(field_name), a.get(field_name)
        if v_before is None or v_after is None:
            continue  # not comparable on this field; no signal either way
        if v_before != v_after:
            return True
        corroborations += 1

    geometry_match = _geometry_matches(b.get("position"), a.get("position"), b.get("size"), a.get("size"))
    if geometry_match is False:
        return True
    if geometry_match is True:
        corroborations += 1

    if role_before is None or role_after is None:
        # We don't even know both sides are the same kind of control;
        # nothing gathered above can safely corroborate sameness.
        return None

    if corroborations >= 1:
        return False

    return None


def focus_changed(
    window_before: Measurement,
    window_after: Measurement,
    element_before: Measurement,
    element_after: Measurement,
) -> Optional[bool]:
    """Three-valued combination of the window and element identity
    signals. A definite interference (True) from either signal always
    wins; otherwise, if either signal is unknown (None), the result is
    unknown - never silently treated as "no interference". Only when
    both signals are affirmatively False (measured and matching) is the
    result False.
    """
    window_diff = _values_differ(window_before, window_after)
    element_diff = _element_identity_changed(element_before, element_after)

    if window_diff is True or element_diff is True:
        return True
    if window_diff is None or element_diff is None:
        return None
    return False
