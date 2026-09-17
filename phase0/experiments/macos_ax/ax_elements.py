"""Locates elements inside the AX fixture app's window.

Kept separate from the experiment/trial definitions so element lookup
failures are easy to distinguish from interference-measurement logic.
"""

from __future__ import annotations

from typing import List, Optional

from phase0.fixtures.mac_ax_fixture_app import BUTTON_TITLE, REBUILD_BUTTON_TITLE

try:
    import ApplicationServices as AS

    _AX_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AS = None  # type: ignore[assignment]
    _AX_AVAILABLE = False


class ElementNotFoundError(RuntimeError):
    pass


def _copy_attr(element, attribute: str):
    err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    if err != 0:
        return None
    return value


def get_fixture_window(pid: int):
    if not _AX_AVAILABLE:
        raise RuntimeError("ApplicationServices unavailable on this platform")
    ax_app = AS.AXUIElementCreateApplication(pid)
    windows = _copy_attr(ax_app, "AXWindows")
    if not windows:
        raise ElementNotFoundError(f"pid {pid} has no AXWindows")
    return windows[0]


def get_text_field(window) -> "object":
    """Returns the first AXTextField in the window (deterministic: the
    fixture always adds `text_field` before `second_text_field`)."""
    fields = get_text_fields(window)
    if not fields:
        raise ElementNotFoundError("no AXTextField found in fixture window")
    return fields[0]


def get_text_fields(window) -> List["object"]:
    """Returns every AXTextField in the fixture window, in AXChildren
    order. The fixture app deliberately gives both fields the same role
    and no AXTitle, so this is used by the focus-switch positive control
    (tests/phase0/integration/test_focus_switch_positive_control.py) to
    move AX focus between two elements a bare (role, title) comparison
    cannot tell apart."""
    children = _copy_attr(window, "AXChildren") or []
    return [child for child in children if _copy_attr(child, "AXRole") == "AXTextField"]


def get_press_button(window) -> "object":
    return _get_button_titled(window, BUTTON_TITLE)


def get_rebuild_button(window) -> "object":
    return _get_button_titled(window, REBUILD_BUTTON_TITLE)


def _get_button_titled(window, title: str) -> "object":
    children = _copy_attr(window, "AXChildren") or []
    for child in children:
        if _copy_attr(child, "AXRole") == "AXButton" and _copy_attr(child, "AXTitle") == title:
            return child
    raise ElementNotFoundError(f"no AXButton titled {title!r} found in fixture window")


def get_counter_label(window) -> "object":
    children = _copy_attr(window, "AXChildren") or []
    for child in children:
        if _copy_attr(child, "AXRole") == "AXStaticText":
            value = _copy_attr(child, "AXValue")
            if isinstance(value, str) and value.startswith("pressed:"):
                return child
    raise ElementNotFoundError("no counter AXStaticText found in fixture window")


def read_value(element) -> Optional[str]:
    return _copy_attr(element, "AXValue")


def set_value(element, value: str) -> int:
    return AS.AXUIElementSetAttributeValue(element, "AXValue", value)


def perform_action(element, action: str) -> int:
    return AS.AXUIElementPerformAction(element, action)


def set_focused(element) -> int:
    """Moves AX keyboard focus to `element` via the public AXFocused
    attribute - a semantic accessibility action, not synthetic
    mouse/keyboard input, and does not touch the physical cursor."""
    return AS.AXUIElementSetAttributeValue(element, "AXFocused", True)
