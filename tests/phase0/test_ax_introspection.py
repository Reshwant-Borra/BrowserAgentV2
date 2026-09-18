"""Unit tests for phase0/experiments/mac_app_capabilities/ax_introspection.py.

Exercises `walk_tree`/`find_descendant`/`find_by_role*` against a fake,
in-memory AX-like tree - never a real `ApplicationServices` call. This
mirrors tests/phase0/conftest.py's `FakeObserver` approach: replace the
module's low-level attribute/action accessors with fakes, and drive the
same tree-walking logic the real probe uses against real applications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from phase0.experiments.mac_app_capabilities import ax_introspection as axi


@dataclass
class FakeNode:
    role: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    identifier: Optional[str] = None
    value: Optional[str] = None
    actions: Optional[List[str]] = None
    children: List["FakeNode"] = field(default_factory=list)


def _fake_copy_attr(node: FakeNode, attribute: str):
    if node is None:
        return None, -1
    mapping: Dict[str, object] = {
        "AXRole": node.role,
        "AXTitle": node.title,
        "AXDescription": node.description,
        "AXIdentifier": node.identifier,
        "AXValue": node.value,
        "AXChildren": node.children or None,
    }
    value = mapping.get(attribute)
    return (value, 0) if value is not None else (None, -25212)


def _fake_action_names(node: FakeNode):
    if node is None:
        return None
    return list(node.actions) if node.actions else None


@pytest.fixture(autouse=True)
def _patch_ax_layer(monkeypatch):
    monkeypatch.setattr(axi, "_AX_AVAILABLE", True)
    monkeypatch.setattr(axi, "copy_attr", _fake_copy_attr)
    monkeypatch.setattr(axi, "action_names", _fake_action_names)


def _tree() -> FakeNode:
    # window
    #   button (actionable, titled, identifier)
    #   textfield (actionable, no title, identifier)
    #   staticText (labeled via description only)
    #   webarea
    #     nested button (depth 2)
    return FakeNode(
        role="AXWindow",
        title="Test Window",
        children=[
            FakeNode(role="AXButton", title="Press Me", identifier="btn1", actions=["AXPress"]),
            FakeNode(role="AXTextField", identifier="field1", actions=["AXConfirm"], value="hello"),
            FakeNode(role="AXStaticText", description="a label"),
            FakeNode(
                role="AXWebArea",
                children=[FakeNode(role="AXButton", title="Nested", actions=["AXPress"])],
            ),
        ],
    )


def test_walk_tree_counts_nodes_actions_identifiers_and_labels():
    stats = axi.walk_tree(_tree(), max_depth=6, max_nodes=100)
    # window + 4 children + 1 nested = 6 nodes
    assert stats.node_count == 6
    assert stats.actionable_count == 3  # button, textfield, nested button
    assert stats.identifier_count == 2  # button, textfield
    assert stats.labeled_count == 4  # window (title), button (title), staticText (description), nested button (title)
    assert stats.web_area_present is True
    assert "AXWindow" in stats.roles_seen
    assert stats.truncated is False


def test_walk_tree_respects_max_depth():
    stats = axi.walk_tree(_tree(), max_depth=0, max_nodes=100)
    assert stats.node_count == 1  # only the root is visited
    assert stats.web_area_present is False


def test_walk_tree_marks_truncated_when_node_cap_is_hit():
    stats = axi.walk_tree(_tree(), max_depth=6, max_nodes=2)
    assert stats.node_count == 2
    assert stats.truncated is True


def test_walk_tree_on_none_root_returns_empty_stats_without_raising():
    stats = axi.walk_tree(None)
    assert stats.node_count == 0
    assert stats.truncated is False


def test_find_by_role_locates_nested_element():
    found = axi.find_by_role(_tree(), "AXWebArea")
    assert found is not None
    assert found.role == "AXWebArea"


def test_find_by_role_and_title_distinguishes_same_role_different_title():
    found = axi.find_by_role_and_title(_tree(), "AXButton", "Nested")
    assert found is not None
    assert found.title == "Nested"

    missing = axi.find_by_role_and_title(_tree(), "AXButton", "Does Not Exist")
    assert missing is None


def test_find_descendant_returns_none_when_nothing_matches():
    found = axi.find_descendant(_tree(), lambda e: e.role == "AXSlider")
    assert found is None


def test_ax_unavailable_short_circuits_walk_tree(monkeypatch):
    monkeypatch.setattr(axi, "_AX_AVAILABLE", False)
    stats = axi.walk_tree(_tree())
    assert stats.node_count == 0
