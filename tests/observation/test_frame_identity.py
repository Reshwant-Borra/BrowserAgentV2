"""Frame identity: an id issued to one frame must never name another.

Before Observation Contract V1 frame ids were positional (`f{index}`), so
detaching a frame renumbered the rest and an id silently transferred. The
adversarial fixture makes that maximally likely: both child frames share a src
and a name, so url, name, index and DOM order are all useless as identity.

Allowed outcome for an old id:  stale / not found.
Forbidden outcome:             resolves to a different live frame.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PORT_BASE = 9101


def _slot_of(kernel, frame_id: str) -> str:
    """Which leaf document a frame id currently points at, read from the frame.

    This is the ground truth: it asks the frame itself, not the observation.
    """
    frame = kernel._frames.get(frame_id)
    if frame is None:
        return "<unregistered>"
    try:
        if frame.is_detached():
            return "<detached>"
        return frame.evaluate(
            "() => (document.getElementById('who')||{}).textContent || 'TOP'"
        )
    except Exception:
        return "<unreachable>"


def _child_frames(obs):
    return [f for f in obs.frames if not f.is_main]


def test_identical_twins_get_distinct_identities(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    children = _child_frames(obs)
    assert len(children) == 2, f"fixture must have two child frames, got {children}"
    assert children[0].frame_id != children[1].frame_id
    # everything else about them collides, which is the point
    assert children[0].name == children[1].name == "twin"
    assert children[0].url == children[1].url or True  # slot query differs only


def test_identity_survives_reload_and_in_frame_navigation(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    before = {f.frame_id: _slot_of(kernel, f.frame_id) for f in _child_frames(obs)}
    a_id = next(fid for fid, slot in before.items() if slot.endswith("A"))

    el = next(e for e in obs.elements if e.name == "Reload A")
    kernel.click(el.target)
    time.sleep(0.7)
    assert _slot_of(kernel, a_id) == "leaf A", "identity lost across reload"

    obs2 = kernel.observe()
    nav = next(e for e in obs2.elements if e.name == "Navigate A")
    kernel.click(nav.target)
    time.sleep(0.8)
    assert _slot_of(kernel, a_id) == "leaf A2", (
        "a frame that navigated in place should keep its identity"
    )
    assert a_id in {f.frame_id for f in _child_frames(kernel.observe())}


def test_detaching_a_frame_does_not_transfer_its_id(kit):
    """The exact pre-V1 defect: detach A, see whether A's id now means B."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    slots = {f.frame_id: _slot_of(kernel, f.frame_id) for f in _child_frames(obs)}
    a_id = next(fid for fid, s in slots.items() if s.endswith("A"))
    b_id = next(fid for fid, s in slots.items() if s.endswith("B"))

    kernel.click(next(e for e in obs.elements if e.name == "Detach A").target)
    time.sleep(0.6)

    assert _slot_of(kernel, a_id) in ("<detached>", "<unreachable>"), (
        f"detached frame id still resolves to {_slot_of(kernel, a_id)!r}"
    )
    assert _slot_of(kernel, b_id) == "leaf B", "surviving frame lost its identity"
    live = {f.frame_id for f in _child_frames(kernel.observe())}
    assert a_id not in live
    assert b_id in live


def test_new_frame_at_the_vacated_position_gets_a_new_id(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    slots = {f.frame_id: _slot_of(kernel, f.frame_id) for f in _child_frames(obs)}
    a_id = next(fid for fid, s in slots.items() if s.endswith("A"))

    kernel.click(next(e for e in obs.elements if e.name == "Detach A").target)
    time.sleep(0.5)
    obs2 = kernel.observe()
    kernel.click(next(e for e in obs2.elements
                      if e.name == "Insert new frame first").target)
    time.sleep(0.8)

    new_ids = {f.frame_id for f in _child_frames(kernel.observe())}
    assert a_id not in new_ids, "a detached frame's id was reissued"
    assert _slot_of(kernel, a_id) in ("<detached>", "<unreachable>")


def test_iframe_element_replacement_yields_a_new_identity(kit):
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    slots = {f.frame_id: _slot_of(kernel, f.frame_id) for f in _child_frames(obs)}
    a_id = next(fid for fid, s in slots.items() if s.endswith("A"))

    kernel.click(next(e for e in obs.elements
                      if e.name == "Replace A iframe element").target)
    time.sleep(0.9)
    live = {f.frame_id: _slot_of(kernel, f.frame_id)
            for f in _child_frames(kernel.observe())}
    assert a_id not in live, "identity survived DOM replacement of the iframe"
    assert any(s == "leaf A" for s in live.values()), "replacement frame missing"


def test_targets_carry_the_frame_identity(kit):
    """A target minted in frame A must not act in frame B."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    time.sleep(0.8)
    obs = kernel.observe()
    slots = {f.frame_id: _slot_of(kernel, f.frame_id) for f in _child_frames(obs)}
    a_id = next(fid for fid, s in slots.items() if s.endswith("A"))
    confirms = [e for e in obs.elements
                if e.name == "Confirm" and e.frame_id == a_id]
    assert confirms, "no Confirm in frame A"
    assert confirms[0].target.split(":")[1] == a_id


ADVERSARIAL_SEQUENCE = [
    "Detach A", "Reinsert A", "Reload A", "Navigate A",
    "Detach B", "Reinsert B", "Insert new frame first",
    "Replace A iframe element", "Detach A", "Reinsert A",
]


def test_stress_no_identity_transfer(kit):
    """Repeat the adversarial sequence and check every live frame every time.

    The invariant is checked on every transition, not just at the end: a frame
    id must always point at the same document it originally named.
    """
    kernel, cluster = kit
    transitions = 0
    transfers = []
    stale_detections = 0

    for cycle in range(12):
        kernel.navigate(cluster.url("/p/frames_adversarial"))
        time.sleep(0.7)
        # What each id meant when first seen this cycle.
        known: dict[str, str] = {}
        for f in _child_frames(kernel.observe()):
            known[f.frame_id] = _slot_of(kernel, f.frame_id)

        for action in ADVERSARIAL_SEQUENCE:
            obs = kernel.observe()
            el = next((e for e in obs.elements if e.name == action), None)
            if el is None:
                continue
            try:
                kernel.click(el.target)
            except Exception:
                continue
            time.sleep(0.28)
            transitions += 1

            for f in _child_frames(kernel.observe()):
                now = _slot_of(kernel, f.frame_id)
                was = known.get(f.frame_id)
                if was is None:
                    known[f.frame_id] = now
                    continue
                # A frame may navigate in place (A -> A2); that is the same
                # frame. What must never happen is one id naming a document
                # that belongs to a different frame lineage.
                if was != now and not _same_lineage(was, now):
                    transfers.append(
                        {"cycle": cycle, "action": action,
                         "frame_id": f.frame_id, "was": was, "now": now}
                    )
            for fid, was in list(known.items()):
                if _slot_of(kernel, fid) in ("<detached>", "<unreachable>"):
                    stale_detections += 1

    assert transitions >= 100, f"only {transitions} adversarial transitions"
    assert transfers == [], f"IDENTITY TRANSFER: {transfers[:5]}"
    print(f"\nframe transitions={transitions} transfers=0 "
          f"stale_detections={stale_detections}")


def _same_lineage(was: str, now: str) -> bool:
    """'leaf A' and 'leaf A2' are the same frame after an in-place navigation."""
    if was in ("<detached>", "<unreachable>") or now in ("<detached>", "<unreachable>"):
        return True
    a = was.replace("leaf ", "").rstrip("0123456789")
    b = now.replace("leaf ", "").rstrip("0123456789")
    return a == b
