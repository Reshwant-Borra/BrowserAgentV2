"""Freshness, and the meaning of AMBIGUOUS.

Two separate claims:

* A pre-action observation can never satisfy a postcondition about the state
  the action was supposed to produce.
* AMBIGUOUS means the evidence is insufficient or contradictory — never "an
  error occurred" and never "the answer is no".
"""

from __future__ import annotations

import time

import pytest

from browser_agent_v2.verification import (
    AMBIGUITY_REASONS,
    DialogState,
    ElementPresence,
    FieldValueEquals,
    PageState,
    Reason,
    TextPresence,
    UrlIs,
    VerificationRequest,
    VerificationStatus,
    Verifier,
)
from browser_agent_v2.verification.postconditions import TextMatch
from tests.verification.harness import BrokenEvidenceSource, FrozenEvidenceSource

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


# --------------------------------------------------------------- freshness


def test_pre_action_observation_cannot_satisfy(fresh):
    """The stale snapshot genuinely contains the satisfying state.

    The page starts with the panel closed. We open it, then verify "panel is
    absent" against the PRE-action observation, in which it truly was absent. A
    verifier that accepts stale evidence reports SATISFIED; the truth is that
    the panel is now open.
    """
    obs_before = fresh.goto("/p/verify_outcomes")
    absent_now = fresh.verify(
        fresh.act(obs_before, lambda: None),
        ElementPresence(page_id=obs_before.page_id, role="button",
                        name="Close panel", expect_present=True),
    )
    assert absent_now.status is NOT, "panel must start closed"

    step = fresh.act(
        obs_before,
        lambda: fresh.kernel.click(fresh.find(obs_before, name="Show panel").target),
    )
    stale_source = FrozenEvidenceSource(obs_before, fresh.kernel)
    stale_verifier = Verifier(stale_source, durable=fresh.durable)
    result = fresh.verify(
        step,
        ElementPresence(page_id=obs_before.page_id, role="button",
                        name="Close panel", expect_present=False),
        verifier=stale_verifier,
    )
    assert result.status is AMB, "a pre-action snapshot was accepted as evidence"
    assert result.reason is Reason.STALE_EVIDENCE
    assert result.evidence["cause"] == "STALE_OBSERVATION"


def test_stale_observation_cannot_satisfy_a_value_check(fresh):
    obs_before = fresh.goto("/p/inputs")
    el = fresh.find(obs_before, name="Plain text")
    fresh.kernel.type_text(el.target, "Tampa")
    obs_typed = fresh.observe()

    step = fresh.act(obs_typed, lambda: fresh.kernel.type_text(el.target, "Orlando"))
    stale_verifier = Verifier(FrozenEvidenceSource(obs_typed, fresh.kernel))
    result = fresh.verify(
        step,
        FieldValueEquals(page_id=obs_typed.page_id, target=el.target,
                         expected="Tampa", name="Plain text"),
        verifier=stale_verifier,
    )
    assert result.status is AMB
    assert result.reason is Reason.STALE_EVIDENCE


def test_replaying_the_same_observation_id_is_refused(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    request = VerificationRequest(
        postcondition=TextPresence(page_id=obs.page_id, text="idle"),
        observation_id_before=obs.observation_id,
    )
    stale_verifier = Verifier(FrozenEvidenceSource(obs, fresh.kernel))
    result = stale_verifier.verify(request)
    assert result.status is AMB
    assert result.reason is Reason.STALE_EVIDENCE


def test_fresh_observation_is_accepted(fresh):
    """Control: the same check passes when evidence really is fresh."""
    obs_before = fresh.goto("/p/verify_outcomes")
    step = fresh.act(
        obs_before,
        lambda: fresh.kernel.click(fresh.find(obs_before, name="Show panel").target),
    )
    result = fresh.verify(
        step,
        ElementPresence(page_id=obs_before.page_id, role="button",
                        name="Close panel", expect_present=True),
    )
    assert result.status is SAT
    assert result.evidence["observation_id"] != obs_before.observation_id


# --------------------------------------------------------------- ambiguity


def test_unreachable_evidence_is_ambiguous(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    broken = Verifier(BrokenEvidenceSource("DISCONNECTED"))
    result = broken.verify(
        VerificationRequest(
            postcondition=TextPresence(page_id=obs.page_id, text="anything"),
            observation_id_before=obs.observation_id,
        )
    )
    assert result.status is AMB
    assert result.reason is Reason.EVIDENCE_UNAVAILABLE
    assert result.evidence["cause"] == "DISCONNECTED"


def test_unreachable_page_list_is_ambiguous(fresh):
    broken = Verifier(BrokenEvidenceSource("BROWSER_GONE"))
    result = broken.verify(
        VerificationRequest(postcondition=PageState(page_id="page_1"))
    )
    assert result.status is AMB
    assert result.reason is Reason.EVIDENCE_UNAVAILABLE


def test_unreachable_dialog_state_is_ambiguous(fresh):
    broken = Verifier(BrokenEvidenceSource("BROWSER_GONE"))
    result = broken.verify(
        VerificationRequest(postcondition=DialogState(page_id="page_1"))
    )
    assert result.status is AMB


def test_ambiguity_always_carries_an_evidence_reason(fresh):
    """AMBIGUOUS is never a catch-all: its reason is always about evidence."""
    broken = Verifier(BrokenEvidenceSource("DISCONNECTED"))
    for pc in (
        TextPresence(page_id="page_1", text="x"),
        ElementPresence(page_id="page_1", role="button", name="x"),
        UrlIs(page_id="page_1", expected="x"),
        PageState(page_id="page_1"),
        DialogState(page_id="page_1"),
        FieldValueEquals(page_id="page_1", target="t", expected="x"),
    ):
        r = broken.verify(VerificationRequest(postcondition=pc))
        assert r.status is AMB, pc
        assert r.reason in AMBIGUITY_REASONS, (pc, r.reason)


def test_all_three_answers_are_reachable_for_one_postcondition_type(fresh):
    """SATISFIED / NOT_SATISFIED / AMBIGUOUS are genuinely distinct outcomes."""
    obs = fresh.goto("/p/verify_outcomes")
    fresh.kernel.click(fresh.find(obs, name="Approve request").target)
    obs2 = fresh.observe()
    step = fresh.act(obs2, lambda: None)

    yes = fresh.verify(step, TextPresence(page_id=obs2.page_id,
                                          text="Right outcome recorded"))
    no = fresh.verify(step, TextPresence(page_id=obs2.page_id,
                                         text="Wrong outcome recorded"))
    unknown = Verifier(BrokenEvidenceSource()).verify(
        VerificationRequest(
            postcondition=TextPresence(page_id=obs2.page_id, text="Right outcome recorded")
        )
    )
    assert (yes.status, no.status, unknown.status) == (SAT, NOT, AMB)


def test_ambiguous_result_carries_no_retry_instruction(fresh):
    """The Verifier reports; it never prescribes an action."""
    broken = Verifier(BrokenEvidenceSource())
    result = broken.verify(
        VerificationRequest(postcondition=PageState(page_id="page_1"))
    )
    blob = str(result.to_json()).lower()
    for word in ("retry", "again", "reload", "refresh", "maybe", "probably"):
        assert word not in blob, f"verifier result suggested {word!r}"


# -------------------------------------------------------------- navigation


def test_exact_url_required(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    step = fresh.act(
        obs, lambda: fresh.kernel.navigate(fresh.url("/p/verify_confirm")))
    assert fresh.verify(
        step, UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm"))
    ).status is SAT
    assert fresh.verify(
        step, UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_other"))
    ).status is NOT


def test_title_is_never_used_as_the_destination_signal(fresh):
    """Two different URLs share a title; only the URL decides."""
    a = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    try:
        obs = fresh.observe(a)
        step = fresh.act(
            obs, lambda: fresh.kernel.navigate(fresh.url("/p/verify_page_failure"), a))
        result = fresh.verify(
            step, UrlIs(page_id=a, expected=fresh.url("/p/verify_page_success"))
        )
        assert result.status is NOT, "identical titles must not satisfy a URL check"
    finally:
        fresh.kernel.close_agent_tab(a)


def test_spa_route_change_is_verified_by_url(fresh):
    obs = fresh.goto("/p/spa")
    btn = fresh.find(obs, name="Orders")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    assert fresh.verify(
        step, UrlIs(page_id=obs.page_id, expected="#orders", match=TextMatch.CONTAINS)
    ).status is SAT


def test_redirect_chain_lands_on_final_url(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    step = fresh.act(obs, lambda: fresh.kernel.navigate(fresh.url("/redirect?n=3")))
    assert fresh.verify(
        step, UrlIs(page_id=obs.page_id, expected=fresh.url("/redirect?n=0"))
    ).status is SAT


def test_failed_navigation_does_not_satisfy(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    step = fresh.act(obs, lambda: fresh.kernel.navigate(fresh.url("/slow?ms=9000")))
    assert step.execution_status == "KERNEL_ERROR"
    result = fresh.verify(
        step, UrlIs(page_id=obs.page_id, expected=fresh.url("/slow?ms=9000"))
    )
    assert result.status is NOT
    assert result.reason is Reason.URL_MISMATCH
