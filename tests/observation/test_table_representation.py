"""Table / group representation quality.

AD-M22's root cause: an actionable control inside a table row carried no row
context, so three identical `button 'Open'` entries were indistinguishable and
the observation could not express "the Open button in B. Lindqvist's row".

These tests ask a question about the *observation*, not about a model: given
only the observation, can deterministic code establish which row a target
belongs to? No Qwen is involved anywhere here.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PORT_BASE = 9111


def _row_of(obs, target: str) -> dict:
    """Resolve a target to its row's cells using only the observation."""
    g = obs.group_of(target)
    return dict(g.cells) if g else {}


def _targets_named(obs, name: str, section: str | None = None):
    return [e for e in obs.elements
            if e.name.strip() == name
            and (section is None or (e.section or "").strip() == section)]


# ------------------------------------------------------------------ basics


def test_every_row_control_resolves_to_its_own_row(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    reviews = _targets_named(obs, "Review", "Standard table with headers")
    assert len(reviews) == 3

    rows = [_row_of(obs, e.target) for e in reviews]
    assert [r.get("Name") for r in rows] == ["Alice", "Bob", "Carol"]
    assert [r.get("Status") for r in rows] == ["Pending", "Complete", "Pending"]
    # each row is distinct, which is the whole point
    assert len({json.dumps(r, sort_keys=True) for r in rows}) == 3


def test_the_ad_m22_question_is_answerable(kit):
    """'Which target is the Review button in Alice/Pending's row?'"""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    reviews = _targets_named(obs, "Review", "Standard table with headers")

    matching = [
        e for e in reviews
        if _row_of(obs, e.target).get("Name") == "Alice"
        and _row_of(obs, e.target).get("Status") == "Pending"
    ]
    assert len(matching) == 1, "row association is ambiguous"

    kernel.click(matching[0].target)
    obs2 = kernel.observe()
    assert any("picked Alice" in b.text for b in obs2.text_blocks)


def test_identical_rows_in_a_second_table_do_not_collide(kit):
    """Alice/Pending appears in two tables; the groups must stay distinct."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    t1 = _targets_named(obs, "Review", "Standard table with headers")
    t2 = _targets_named(obs, "Review", "Second table, same action label, same statuses")
    assert t1 and t2

    alice1 = [e for e in t1 if _row_of(obs, e.target).get("Name") == "Alice"]
    alice2 = [e for e in t2 if _row_of(obs, e.target).get("Name") == "Alice"]
    assert len(alice1) == 1 and len(alice2) == 1
    assert alice1[0].group_id != alice2[0].group_id, "rows from two tables merged"
    assert alice1[0].target != alice2[0].target

    kernel.click(alice2[0].target)
    obs2 = kernel.observe()
    assert any("picked T2-Alice" in b.text for b in obs2.text_blocks), (
        "clicked the wrong table's Alice"
    )


def test_headerless_table_uses_positional_cell_keys(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    opens = _targets_named(obs, "Open", "No headers, missing optional cell")
    assert len(opens) == 2
    rows = [_row_of(obs, e.target) for e in opens]
    assert rows[0].get("1") == "Erin"
    assert rows[1].get("1") == "Frank"
    assert rows[1].get("2") == "Archived"


def test_missing_optional_cell_does_not_shift_the_others(kit):
    """Erin's status cell is empty; her name must not slide into that slot."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    erin = [e for e in _targets_named(obs, "Open", "No headers, missing optional cell")
            if _row_of(obs, e.target).get("1") == "Erin"]
    assert len(erin) == 1
    assert _row_of(obs, erin[0].target).get("2") in (None, "")


def test_links_in_cells_are_grouped(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    details = _targets_named(obs, "Details", "Links inside cells")
    assert len(details) == 2
    owners = [_row_of(obs, e.target).get("Owner") for e in details]
    assert owners == ["Grace", "Heidi"]


def test_aria_grid_is_grouped(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    applies = _targets_named(obs, "Apply", "ARIA grid")
    assert len(applies) == 2
    rows = [_row_of(obs, e.target) for e in applies]
    assert [r.get("Item") for r in rows] == ["Widget", "Gadget"]
    assert [r.get("Qty") for r in rows] == ["3", "7"]


def test_list_items_are_grouped(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    reminds = _targets_named(obs, "Remind", "List items")
    assert len(reminds) == 2
    groups = [obs.group_of(e.target) for e in reminds]
    assert all(g is not None and g.kind == "listitem" for g in groups)
    assert "Ivan" in groups[0].label and "Judy" in groups[1].label


def test_controls_outside_any_group_have_no_group(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    reorder = next(e for e in obs.elements if e.name == "Reorder standard rows")
    assert reorder.group_id == ""
    assert obs.group_of(reorder.target) is None


def test_action_cell_is_not_echoed_into_the_row_label(kit):
    """The row's own controls are already listed as elements."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    e = _targets_named(obs, "Review", "Standard table with headers")[0]
    label = obs.group_of(e.target).label
    assert "Review" not in label, f"row label echoed its own control: {label!r}"


# --------------------------------------------------------------- dynamics


def test_reorder_keeps_each_control_with_its_own_row(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    kernel.click(next(e for e in obs.elements if e.name == "Reorder standard rows").target)
    time.sleep(0.2)
    obs2 = kernel.observe()
    reviews = _targets_named(obs2, "Review", "Standard table with headers")
    order = [_row_of(obs2, e.target).get("Name") for e in reviews]
    assert order == ["Carol", "Alice", "Bob"], order

    carol = [e for e in reviews if _row_of(obs2, e.target).get("Name") == "Carol"]
    kernel.click(carol[0].target)
    obs3 = kernel.observe()
    assert any("picked Carol" in b.text for b in obs3.text_blocks)


def test_row_replacement_keeps_associations_correct(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    kernel.click(next(e for e in obs.elements if e.name == "Replace standard rows").target)
    time.sleep(0.3)
    obs2 = kernel.observe()
    reviews = _targets_named(obs2, "Review", "Standard table with headers")
    assert [_row_of(obs2, e.target).get("Name") for e in reviews] == [
        "Carol", "Bob", "Alice"
    ]

    bob = [e for e in reviews if _row_of(obs2, e.target).get("Name") == "Bob"]
    kernel.click(bob[0].target)
    obs3 = kernel.observe()
    assert any("picked Bob" in b.text for b in obs3.text_blocks)


def test_value_swap_is_reflected_in_the_row(kit):
    """If the page moves a value between rows, the observation follows."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/tables_adversarial"))
    obs = kernel.observe()
    kernel.click(next(e for e in obs.elements if e.name == "Swap Alice/Bob names").target)
    time.sleep(0.2)
    obs2 = kernel.observe()
    reviews = _targets_named(obs2, "Review", "Standard table with headers")
    names = [_row_of(obs2, e.target).get("Name") for e in reviews]
    assert names[:2] == ["Bob", "Alice"], names


def test_stress_row_association(kit):
    """Every row control on the page, repeatedly, across dynamic churn."""
    kernel, cluster = kit
    checked = 0
    for cycle in range(10):
        kernel.navigate(cluster.url("/p/tables_adversarial"))
        obs = kernel.observe()
        if cycle % 3 == 1:
            kernel.click(next(e for e in obs.elements
                              if e.name == "Reorder standard rows").target)
            time.sleep(0.15)
            obs = kernel.observe()
        elif cycle % 3 == 2:
            kernel.click(next(e for e in obs.elements
                              if e.name == "Replace standard rows").target)
            time.sleep(0.25)
            obs = kernel.observe()

        grouped = [e for e in obs.elements if e.group_id]
        assert len(grouped) >= 11, f"expected >=11 grouped controls, got {len(grouped)}"
        for e in grouped:
            cells = _row_of(obs, e.target)
            assert cells, f"{e.target} ({e.name}) has a group with no cells"
            # the row must carry at least one value that is not the control name
            assert any(v and v != e.name for v in cells.values()), cells
            checked += 1
    print(f"\nrow associations checked={checked}")
    assert checked >= 100
