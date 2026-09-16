"""Final adversarial pass: the combinations, not the individual cases.

Frame identity and row grouping are each tested in isolation elsewhere. This is
the cross-product, which is where a representation usually breaks: two frames
with identical `src` and `name`, each hosting a byte-identical table, so that
frame url, frame name, frame index, row content and control label all collide
at once. Six "Open" buttons, nothing distinguishable except minted identity.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browser_agent_v2.verification import (
    ElementPresence,
    Reason,
    VerificationRequest,
    VerificationStatus,
)

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


def _side_of(kernel, frame_id):
    frame = kernel._frames.get(frame_id)
    try:
        return frame.evaluate("() => (document.getElementById('who')||{}).textContent || ''")
    except Exception:
        return "<gone>"


def _load(kernel, cluster):
    kernel.navigate(cluster.url("/p/frames_tables"))
    time.sleep(1.0)
    obs = kernel.observe()
    sides = {}
    for f in obs.frames:
        if f.is_main:
            continue
        sides[_side_of(kernel, f.frame_id).strip()] = f.frame_id
    return obs, sides


def test_six_identical_buttons_are_all_distinguishable(kit):
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    assert set(sides) == {"table left", "table right"}, sides

    opens = [e for e in obs.elements if e.name.strip() == "Open"]
    assert len(opens) == 6, f"expected 6 Open buttons, got {len(opens)}"

    # Each is identified by (frame, row) and every combination is unique.
    keys = set()
    for e in opens:
        g = obs.group_of(e.target)
        assert g is not None, f"{e.target} has no row"
        keys.add((e.frame_id, g.cells.get("Ref")))
    assert len(keys) == 6, f"identities collapsed: {sorted(keys)}"


def test_group_ids_do_not_collide_across_identical_frames(kit):
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    left, right = sides["table left"], sides["table right"]
    left_groups = {g.group_id for g in obs.groups if g.frame_id == left}
    right_groups = {g.group_id for g in obs.groups if g.frame_id == right}
    assert left_groups and right_groups
    assert not (left_groups & right_groups), "row ids collided across frames"


def test_clicking_a_row_in_one_frame_does_not_hit_its_twin(kit):
    """The end-to-end check: the right button in the right frame."""
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    right = sides["table right"]

    target = next(
        e for e in obs.elements
        if e.name.strip() == "Open"
        and e.frame_id == right
        and (obs.group_of(e.target).cells.get("Ref") == "REF-1002")
    )
    kernel.click(target.target)
    time.sleep(0.2)
    after = kernel.observe()
    picked = [b.text for b in after.text_blocks if b.text.startswith("picked")]
    assert picked == ["picked right:REF-1002"], picked


def test_verifier_can_scope_to_a_row_inside_a_specific_frame(kit, harness):
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    left, right = sides["table left"], sides["table right"]

    step = harness.act(obs, lambda: None)
    ok = harness.verify(
        step,
        ElementPresence(page_id=obs.page_id, role="button", name="Open",
                        frame_id=right, group_cells={"Owner": "B. Lindqvist"}),
    )
    assert ok.status is SAT
    assert ok.evidence["matched_frames"] == [right]
    assert len(ok.evidence["matches"]) == 1, "row scoping matched more than one control"

    # A row value that exists in neither frame must not match.
    missing = harness.verify(
        step,
        ElementPresence(page_id=obs.page_id, role="button", name="Open",
                        frame_id=right, group_cells={"Owner": "Nobody At All"}),
    )
    assert missing.status is NOT
    assert missing.reason is Reason.ELEMENT_MISSING


def test_dropping_one_frame_leaves_the_twin_untouched(kit, harness):
    """The transfer scenario, with tables attached."""
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    left, right = sides["table left"], sides["table right"]

    drop = next(e for e in obs.elements if e.name == "Drop left frame")
    step = harness.act(obs, lambda: kernel.click(drop.target))
    time.sleep(0.5)

    after = kernel.observe()
    live = {f.frame_id for f in after.frames if not f.is_main}
    assert left not in live, "the dropped frame is still present"
    assert right in live, "the surviving frame lost its identity"
    assert _side_of(kernel, right).strip() == "table right", (
        "the surviving frame's identity moved"
    )

    # The dropped frame's scope now finds nothing; the twin does not answer.
    gone = harness.verify(
        step,
        ElementPresence(page_id=obs.page_id, role="button", name="Open",
                        frame_id=left, group_cells={"Owner": "B. Lindqvist"}),
    )
    assert gone.status is NOT, "the twin frame answered for the dropped one"

    still_there = harness.verify(
        step,
        ElementPresence(page_id=obs.page_id, role="button", name="Open",
                        frame_id=right, group_cells={"Owner": "B. Lindqvist"}),
    )
    assert still_there.status is SAT


def test_stale_target_from_a_dropped_frame_fails_closed(kit):
    kernel, cluster = kit
    obs, sides = _load(kernel, cluster)
    left = sides["table left"]
    victim = next(e for e in obs.elements
                  if e.name.strip() == "Open" and e.frame_id == left)

    drop = next(e for e in obs.elements if e.name == "Drop left frame")
    kernel.click(drop.target)
    time.sleep(0.5)

    from experiments.common.contracts import KernelError

    with pytest.raises(KernelError) as exc:
        kernel.click(victim.target)
    assert exc.value.code.value in (
        "FRAME_DETACHED", "TARGET_STALE", "OBSERVATION_SUPERSEDED", "DOCUMENT_CHANGED"
    ), exc.value.code

    # and nothing in the surviving frame was activated
    after = kernel.observe()
    picked = [b.text for b in after.text_blocks if b.text.startswith("picked")]
    assert picked == [] or all("none" in p for p in picked), picked
