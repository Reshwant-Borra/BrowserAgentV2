"""Page and frame scoping.

Experiments 4, 5 and 7 established that the realistic way a verifier reports a
false success is by finding the right-looking evidence in the wrong place:
identical text on another tab, an identical control in another frame. Every
test here is adversarial by construction — the satisfying text genuinely exists
somewhere, just not where the postcondition said to look.
"""

from __future__ import annotations

import time

import pytest

from browser_agent_v2.verification import (
    MAIN_FRAME,
    ElementPresence,
    PageState,
    Reason,
    TextPresence,
    UrlIs,
    VerificationStatus,
)

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


# ------------------------------------------------------------- page scoping


@pytest.fixture
def two_status_pages(fresh):
    """Two pages with byte-identical titles and conflicting verdict text."""
    a = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    b = fresh.kernel.new_tab(fresh.url("/p/verify_page_failure"))
    time.sleep(0.2)
    yield a, b
    for pid in (a, b):
        try:
            fresh.kernel.close_agent_tab(pid)
        except Exception:
            pass


def test_text_on_the_other_page_does_not_satisfy(fresh, two_status_pages):
    """'Success' exists — on page A. The postcondition is scoped to page B."""
    page_a, page_b = two_status_pages
    obs_b = fresh.observe(page_b)
    result = fresh.verify(
        fresh.act(obs_b, lambda: None),
        TextPresence(page_id=page_b, text="Success"),
    )
    assert result.status is NOT
    assert result.reason is Reason.TEXT_MISSING
    assert result.evidence["page_id"] == page_b

    # and the same assertion against page A is genuinely satisfied,
    # proving the fixture really does contain the text somewhere
    obs_a = fresh.observe(page_a)
    ok = fresh.verify(
        fresh.act(obs_a, lambda: None), TextPresence(page_id=page_a, text="Success")
    )
    assert ok.status is SAT


def test_identical_titles_do_not_merge_pages(fresh, two_status_pages):
    page_a, page_b = two_status_pages
    pages = {p.page_id: p for p in fresh.kernel.list_pages()}
    assert pages[page_a].title == pages[page_b].title, "fixture titles must collide"
    assert page_a != page_b

    obs_b = fresh.observe(page_b)
    result = fresh.verify(
        fresh.act(obs_b, lambda: None),
        TextPresence(page_id=page_b, text="Failure"),
    )
    assert result.status is SAT
    assert result.evidence["page_id"] == page_b


def test_duplicate_url_pages_are_distinguished(fresh):
    a = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    b = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    time.sleep(0.2)
    try:
        assert a != b
        obs = fresh.observe(b)
        res = fresh.verify(
            fresh.act(obs, lambda: None),
            PageState(page_id=b, expect_exists=True,
                      expect_url=fresh.url("/p/verify_page_success")),
        )
        assert res.status is SAT
        # a page id that was never minted must not be satisfied by its twin
        res2 = fresh.verify(
            fresh.act(obs, lambda: None), PageState(page_id="page_99999", expect_exists=True)
        )
        assert res2.status is NOT
        assert res2.reason is Reason.PAGE_MISSING
    finally:
        for pid in (a, b):
            try:
                fresh.kernel.close_agent_tab(pid)
            except Exception:
                pass


def test_element_on_the_other_page_does_not_satisfy(fresh, two_status_pages):
    page_a, page_b = two_status_pages
    obs_b = fresh.observe(page_b)
    # Both pages have a 'Continue' button; scope the check to a page that has none.
    fresh.kernel.page_object(page_b).evaluate(
        "() => document.getElementById('act').remove()"
    )
    obs_b2 = fresh.observe(page_b)
    result = fresh.verify(
        fresh.act(obs_b2, lambda: None),
        ElementPresence(page_id=page_b, role="button", name="Continue"),
    )
    assert result.status is NOT
    assert result.reason is Reason.ELEMENT_MISSING
    # page A still has it
    obs_a = fresh.observe(page_a)
    assert (
        fresh.verify(
            fresh.act(obs_a, lambda: None),
            ElementPresence(page_id=page_a, role="button", name="Continue"),
        ).status
        is SAT
    )


def test_url_check_is_scoped_to_the_named_page(fresh, two_status_pages):
    page_a, page_b = two_status_pages
    obs_b = fresh.observe(page_b)
    result = fresh.verify(
        fresh.act(obs_b, lambda: None),
        UrlIs(page_id=page_b, expected=fresh.url("/p/verify_page_success")),
    )
    assert result.status is NOT
    assert result.reason is Reason.URL_MISMATCH


def test_closed_page_cannot_satisfy(fresh):
    pid = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    time.sleep(0.2)
    obs = fresh.observe(pid)
    fresh.kernel.close_agent_tab(pid)
    result = fresh.verify(
        fresh.act(obs, lambda: None), PageState(page_id=pid, expect_exists=True)
    )
    assert result.status is NOT
    assert result.reason is Reason.PAGE_MISSING


def test_observing_a_closed_page_is_ambiguous_not_satisfied(fresh):
    pid = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    time.sleep(0.2)
    obs = fresh.observe(pid)
    fresh.kernel.close_agent_tab(pid)
    result = fresh.verify(
        fresh.act(obs, lambda: None), TextPresence(page_id=pid, text="Success")
    )
    assert result.status is AMB
    assert result.reason is Reason.EVIDENCE_UNAVAILABLE
    assert result.evidence["cause"] == "PAGE_CLOSED"


# ------------------------------------------------------------ frame scoping


def _child_frames(obs):
    return sorted({e.frame_id for e in obs.elements if e.frame_id != obs.main_frame_id})


def _frame_showing(fresh, obs, needle):
    """The minted id of the frame whose own heading contains `needle`."""
    for fid in _child_frames(obs):
        if any(needle in b.text for b in obs.text_blocks if b.frame_id == fid):
            return fid
    raise LookupError(f"no frame showing {needle!r}")


def test_control_in_another_frame_does_not_satisfy(fresh):
    """'Confirm' exists in the top frame and in two child frames."""
    obs = fresh.goto("/p/frames")
    time.sleep(0.6)
    obs = fresh.observe()
    confirms = [e for e in obs.elements if e.name.strip() == "Confirm"]
    frames = {e.frame_id for e in confirms}
    assert len(frames) >= 3, f"fixture must span frames, saw {frames}"

    # Remove the top-frame Confirm only; the child frames keep theirs.
    fresh.kernel.page_object().evaluate(
        "() => document.getElementById('top-action').remove()"
    )
    obs2 = fresh.observe()
    result = fresh.verify(
        fresh.act(obs2, lambda: None),
        ElementPresence(page_id=obs2.page_id, role="button", name="Confirm",
                        frame_id=MAIN_FRAME),
    )
    assert result.status is NOT, "a child frame's Confirm satisfied a top-frame check"
    assert result.reason is Reason.ELEMENT_MISSING

    # Under Observation Contract V1 a minted frame id needs no content pin.
    child = _child_frames(obs2)[0]
    ok = fresh.verify(
        fresh.act(obs2, lambda: None),
        ElementPresence(page_id=obs2.page_id, role="button", name="Confirm",
                        frame_id=child),
    )
    assert ok.status is SAT, "the control really does still exist in a child frame"
    assert ok.evidence["matched_frames"] == [child]


def test_minted_frame_id_needs_no_content_pin(fresh):
    """Replaces the old "unpinned child frame is refused" workaround test.

    That refusal existed because frame ids were positional. They are now minted
    identities, so an unpinned child-frame scope is answerable — and answering
    it correctly is strictly stronger than declining to answer.
    """
    obs = fresh.goto("/p/frames")
    time.sleep(0.6)
    obs = fresh.observe()
    child = _child_frames(obs)[0]
    result = fresh.verify(
        fresh.act(obs, lambda: None),
        ElementPresence(page_id=obs.page_id, role="button", name="Confirm",
                        frame_id=child),
    )
    assert result.status is SAT
    assert result.reason is Reason.OK
    assert result.evidence["requested_frame"] == child


def test_frame_detach_cannot_produce_a_false_success(fresh):
    """The pre-V1 defect, retested against minted identity.

    Detaching the same-origin child used to renumber the rest so that the old
    id came to mean the cross-origin child — which also has a "Confirm". With a
    minted id the detached frame simply has no elements, and no other frame can
    answer for it.
    """
    obs = fresh.goto("/p/frames")
    time.sleep(0.6)
    obs = fresh.observe()
    same_origin = _frame_showing(fresh, obs, "Child (primary)")
    cross_origin = _frame_showing(fresh, obs, "Child (secondary)")
    assert same_origin != cross_origin

    detach = fresh.find(obs, contains="Detach same-origin")
    step = fresh.act(obs, lambda: fresh.kernel.click(detach.target))
    time.sleep(0.4)

    after = fresh.observe()
    assert same_origin not in {e.frame_id for e in after.elements}, (
        "the detached frame still contributes elements"
    )
    assert cross_origin in {e.frame_id for e in after.elements}, (
        "the surviving frame lost its identity"
    )

    result = fresh.verify(
        step,
        ElementPresence(page_id=obs.page_id, role="button", name="Confirm",
                        frame_id=same_origin),
    )
    assert result.status is NOT, "another frame answered for the detached one"
    assert result.reason is Reason.ELEMENT_MISSING


def test_frame_scoped_check_names_the_frame_in_evidence(fresh):
    obs = fresh.goto("/p/frames")
    time.sleep(0.6)
    obs = fresh.observe()
    child = _child_frames(obs)[0]
    result = fresh.verify(
        fresh.act(obs, lambda: None),
        ElementPresence(page_id=obs.page_id, role="button", name="Confirm",
                        frame_id=child),
    )
    assert result.evidence["frame_id"] == child
    assert result.evidence["matched_frames"] == [child]


def test_child_frame_text_is_assertable_and_scoped(fresh):
    """Replaces the old "child-frame text is refused" test.

    Text is frame-scoped under V1, so a child frame's text can be asserted
    directly, and text that lives only in a child frame must not satisfy a
    main-frame assertion.
    """
    obs = fresh.goto("/p/frames")
    time.sleep(0.6)
    obs = fresh.observe()
    child = _frame_showing(fresh, obs, "Child (primary)")

    ok = fresh.verify(
        fresh.act(obs, lambda: None),
        TextPresence(page_id=obs.page_id, text="Child (primary)", frame_id=child),
    )
    assert ok.status is SAT

    wrong_scope = fresh.verify(
        fresh.act(obs, lambda: None),
        TextPresence(page_id=obs.page_id, text="Child (primary)",
                     frame_id=MAIN_FRAME),
    )
    assert wrong_scope.status is NOT, "child-frame text satisfied a main-frame check"
    assert wrong_scope.reason is Reason.TEXT_MISSING


def test_section_anchor_distinguishes_duplicate_control_names(fresh):
    obs = fresh.goto("/p/duplicate_names")
    submits = [e for e in obs.elements if e.name.strip() == "Submit"]
    assert len(submits) == 3
    ok = fresh.verify(
        fresh.act(obs, lambda: None),
        ElementPresence(page_id=obs.page_id, role="button", name="Submit",
                        section="Section B"),
    )
    assert ok.status is SAT
    missing = fresh.verify(
        fresh.act(obs, lambda: None),
        ElementPresence(page_id=obs.page_id, role="button", name="Submit",
                        section="Section Z"),
    )
    assert missing.status is NOT
