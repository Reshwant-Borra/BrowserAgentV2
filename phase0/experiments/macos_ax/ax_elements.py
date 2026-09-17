"""Locates elements inside the AX fixture app's window.

Kept separate from the experiment/trial definitions so element lookup
failures are easy to distinguish from interference-measurement logic.
"""

from __future__ import annotations

from typing import Optional

from phase0.fixtures.mac_ax_fixture_app import BUTTON_TITLE

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
    children = _copy_attr(window, "AXChildren") or []
    for child in children:
        if _copy_attr(child, "AXRole") == "AXTextField":
            return child
    raise ElementNotFoundError("no AXTextField found in fixture window")


def get_press_button(window) -> "object":
    children = _copy_attr(window, "AXChildren") or []
    for child in children:
        if _copy_attr(child, "AXRole") == "AXButton" and _copy_attr(child, "AXTitle") == BUTTON_TITLE:
            return child
    raise ElementNotFoundError(f"no AXButton titled {BUTTON_TITLE!r} found in fixture window")


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
