"""Generic, bounded AX introspection helpers for arbitrary real macOS
applications - not tied to the Cocoa fixture app the way
phase0/experiments/macos_ax/ax_elements.py is.

These are read-only except where a function name says `set`/`perform`.
They never fabricate a value: on failure they return `None`/empty and
let the caller (phase0/experiments/mac_app_capabilities/matrix.py)
decide how to classify that as a `CapabilityState`, the same discipline
phase0/harness/observers_macos.py applies via `Measurement`.

`walk_tree` deliberately never persists AXValue/text content - only
counts (docs/BUILD_SPEC.md section 5: "Do not collect huge full-tree
dumps from private user applications. Store bounded structural
summaries instead.").
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

try:
    import AppKit
    import ApplicationServices as AS

    _AX_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    AS = None  # type: ignore[assignment]
    _AX_AVAILABLE = False


def ax_available() -> bool:
    return _AX_AVAILABLE


def copy_attr(element, attribute: str):
    """Returns `(value_or_None, ax_error_int)`. Never raises for an
    ordinary AX failure."""
    if element is None or not _AX_AVAILABLE:
        return None, -1
    try:
        err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None, -1
    return (value if err == 0 else None), err


def set_attr(element, attribute: str, value) -> int:
    if element is None or not _AX_AVAILABLE:
        return -1
    try:
        return AS.AXUIElementSetAttributeValue(element, attribute, value)
    except Exception:
        return -1


def perform_action(element, action: str) -> int:
    if element is None or not _AX_AVAILABLE:
        return -1
    try:
        return AS.AXUIElementPerformAction(element, action)
    except Exception:
        return -1


def action_names(element) -> Optional[List[str]]:
    if element is None or not _AX_AVAILABLE:
        return None
    try:
        err, names = AS.AXUIElementCopyActionNames(element, None)
    except Exception:
        return None
    return list(names) if err == 0 and names else None


def attribute_names(element) -> Optional[List[str]]:
    if element is None or not _AX_AVAILABLE:
        return None
    try:
        err, names = AS.AXUIElementCopyAttributeNames(element, None)
    except Exception:
        return None
    return sorted(names) if err == 0 and names else None


def create_application_element(pid: int):
    if not _AX_AVAILABLE:
        return None
    return AS.AXUIElementCreateApplication(pid)


def list_windows(ax_app) -> List:
    windows, _err = copy_attr(ax_app, "AXWindows")
    return list(windows) if windows else []


def wait_for_ax_bootstrap(ax_app, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """A freshly launched process's AX/WindowServer connection can take a
    moment to come up at all; this is ordinary launch-timing noise, a
    distinct thing from the Chromium on-demand-content-tree gap
    `observers_macos.warm_up_ax_focus_tree` addresses (see
    phase0/experiments/macos_ax/focus_diagnostics.py's
    `_wait_for_ax_bootstrap`, whose behavior this mirrors for arbitrary
    targets)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _value, err = copy_attr(ax_app, "AXRole")
        if err == 0:
            return True
        time.sleep(interval)
    return False


@dataclass
class TreeWalkStats:
    node_count: int = 0
    max_depth: int = 0
    actionable_count: int = 0
    identifier_count: int = 0
    labeled_count: int = 0
    roles_seen: Set[str] = field(default_factory=set)
    web_area_present: bool = False
    truncated: bool = False


def walk_tree(
    root,
    max_depth: int = 6,
    max_nodes: int = 300,
    max_children_per_node: int = 30,
) -> TreeWalkStats:
    """Bounded iterative traversal collecting structural counts only."""
    stats = TreeWalkStats()
    if root is None or not _AX_AVAILABLE:
        return stats

    stack = [(root, 0)]
    while stack:
        if stats.node_count >= max_nodes:
            stats.truncated = True
            break
        element, depth = stack.pop()
        stats.node_count += 1
        stats.max_depth = max(stats.max_depth, depth)

        role, _ = copy_attr(element, "AXRole")
        if role:
            stats.roles_seen.add(str(role))
            if role == "AXWebArea":
                stats.web_area_present = True

        if action_names(element):
            stats.actionable_count += 1

        identifier, _ = copy_attr(element, "AXIdentifier")
        if identifier:
            stats.identifier_count += 1

        title, _ = copy_attr(element, "AXTitle")
        description, _ = copy_attr(element, "AXDescription")
        if title or description:
            stats.labeled_count += 1

        if depth >= max_depth:
            continue
        children, _ = copy_attr(element, "AXChildren")
        if not children:
            continue
        for child in list(children)[:max_children_per_node]:
            stack.append((child, depth + 1))

    return stats


def find_descendant(
    root,
    predicate: Callable[[object], bool],
    max_depth: int = 8,
    max_children: int = 30,
) -> Optional[object]:
    """Bounded depth-first search for the first descendant matching
    `predicate` (evaluated on `root` itself too)."""
    if root is None or not _AX_AVAILABLE:
        return None

    def _walk(element, depth):
        try:
            if predicate(element):
                return element
        except Exception:
            return None
        if depth >= max_depth:
            return None
        children, _ = copy_attr(element, "AXChildren")
        if not children:
            return None
        for child in list(children)[:max_children]:
            found = _walk(child, depth + 1)
            if found is not None:
                return found
        return None

    return _walk(root, 0)


def find_by_role(root, role: str, **kwargs) -> Optional[object]:
    return find_descendant(root, lambda e: copy_attr(e, "AXRole")[0] == role, **kwargs)


def find_by_role_and_title(root, role: str, title: str, **kwargs) -> Optional[object]:
    def _pred(e):
        r, _ = copy_attr(e, "AXRole")
        t, _ = copy_attr(e, "AXTitle")
        return r == role and t == title

    return find_descendant(root, _pred, **kwargs)
