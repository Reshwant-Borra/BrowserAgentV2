"""Consequential submissions.

Uses the P0 side-effect fixture, which runs with `dedupe=false` — a worst-case
web application that really will perform the same booking twice. Verification of
a consequential action is answered from durable evidence outside the browser,
because the browser's own confirmation text is exactly what a crash removes.

ADR-014: when the durable channel cannot be reached the answer is AMBIGUOUS, and
AMBIGUOUS must never become a retry. The Verifier reports; reconciliation is the
controller's job, and the controller does not exist yet.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid

import pytest

from browser_agent_v2.verification import (
    AllOf,
    OperationRecorded,
    Reason,
    TextPresence,
    VerificationRequest,
    VerificationStatus,
    Verifier,
)
from tests.verification.harness import FixtureDurableEvidence

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


def _submit(fresh, operation_id: str, *, amount: str = "1"):
    """Fill the consequential form and press the submit control."""
    obs = fresh.goto("/p/verify_submit")
    fresh.kernel.type_text(fresh.find(obs, name="Operation ID").target, operation_id)
    fresh.kernel.type_text(fresh.find(obs, name="Amount").target, amount)
    obs2 = fresh.observe()
    submit = fresh.find(obs2, name="Submit booking")
    step = fresh.act(obs2, lambda: fresh.kernel.click(submit.target))
    time.sleep(0.5)  # let the page's own fetch settle; not a verifier retry
    return obs2, step


def _effect_count(fresh, operation_id: str) -> int:
    with urllib.request.urlopen(fresh.url("/api/effects"), timeout=10) as r:
        data = json.loads(r.read())
    return sum(1 for a in data["arrivals"] if a["operation_id"] == operation_id)


def test_completed_submission_is_satisfied(fresh):
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    result = fresh.verify(step, OperationRecorded(page_id=obs.page_id, operation_id=op))
    assert result.status is SAT
    assert result.reason is Reason.OK
    assert result.evidence["confirmation_ref"] is not None
    assert _effect_count(fresh, op) == 1


def test_submission_that_never_happened_is_not_satisfied(fresh):
    """Durable evidence definitively says no. That is NOT_SATISFIED, not unknown."""
    op = f"BK-never-{uuid.uuid4().hex[:8]}"
    obs = fresh.goto("/p/verify_submit")
    step = fresh.act(obs, lambda: None)
    result = fresh.verify(step, OperationRecorded(page_id=obs.page_id, operation_id=op))
    assert result.status is NOT
    assert result.reason is Reason.OPERATION_NOT_RECORDED
    assert _effect_count(fresh, op) == 0


def test_browser_confirmation_alone_is_not_the_evidence(fresh):
    """A different operation id must not be satisfied by a page that says
    'Booking confirmed' for some other booking."""
    other = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, other)
    confirmed = fresh.verify(
        step, TextPresence(page_id=obs.page_id, text="Booking confirmed")
    )
    assert confirmed.status is SAT, "the page really does show a confirmation"

    mine = f"BK-mine-{uuid.uuid4().hex[:8]}"
    result = fresh.verify(
        step, OperationRecorded(page_id=obs.page_id, operation_id=mine)
    )
    assert result.status is NOT
    assert result.reason is Reason.OPERATION_NOT_RECORDED


def test_unreachable_durable_channel_is_ambiguous(fresh):
    """The crash case: the operation may or may not have landed."""
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    assert _effect_count(fresh, op) == 1, "the effect really did happen"

    blind = Verifier(fresh.source, durable=FixtureDurableEvidence(
        fresh.cluster.primary_origin, reachable=False))
    result = fresh.verify(
        step, OperationRecorded(page_id=obs.page_id, operation_id=op), verifier=blind
    )
    assert result.status is AMB
    assert result.reason is Reason.EVIDENCE_UNAVAILABLE
    assert result.evidence["cause"] == "DURABLE_CHANNEL_DOWN"


def test_no_durable_source_configured_is_ambiguous_not_satisfied(fresh):
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    no_durable = Verifier(fresh.source)
    result = fresh.verify(
        step, OperationRecorded(page_id=obs.page_id, operation_id=op),
        verifier=no_durable,
    )
    assert result.status is AMB
    assert result.evidence["cause"] == "NO_DURABLE_SOURCE"


def test_ambiguous_verification_performs_no_side_effect(fresh):
    """The safety property: verifying an ambiguous outcome must not resubmit.

    Counted against the server's own arrival log, which records every arrival
    including duplicates.
    """
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    before = _effect_count(fresh, op)
    assert before == 1

    blind = Verifier(fresh.source, durable=FixtureDurableEvidence(
        fresh.cluster.primary_origin, reachable=False))
    for _ in range(5):
        r = fresh.verify(
            step, OperationRecorded(page_id=obs.page_id, operation_id=op),
            verifier=blind,
        )
        assert r.status is AMB
    assert _effect_count(fresh, op) == before, "verification caused a duplicate effect"


def test_repeated_verification_is_side_effect_free(fresh):
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    for _ in range(10):
        assert fresh.verify(
            step, OperationRecorded(page_id=obs.page_id, operation_id=op)
        ).status is SAT
    assert _effect_count(fresh, op) == 1


def test_submission_requires_both_confirmation_and_durable_record(fresh):
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    result = fresh.verify(
        step,
        AllOf(page_id=obs.page_id, parts=(
            TextPresence(page_id=obs.page_id, text=f"Reference {op}"),
            OperationRecorded(page_id=obs.page_id, operation_id=op),
        )),
    )
    assert result.status is SAT


def test_composite_submission_is_ambiguous_when_durable_evidence_is_lost(fresh):
    """Page says confirmed, world cannot be asked: overall AMBIGUOUS.

    A definite YES on the visible half must not outvote an unknown on the half
    that actually matters.
    """
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    blind = Verifier(fresh.source, durable=FixtureDurableEvidence(
        fresh.cluster.primary_origin, reachable=False))
    result = fresh.verify(
        step,
        AllOf(page_id=obs.page_id, parts=(
            TextPresence(page_id=obs.page_id, text=f"Reference {op}"),
            OperationRecorded(page_id=obs.page_id, operation_id=op),
        )),
        verifier=blind,
    )
    assert result.status is AMB


def test_composite_definite_failure_outranks_ambiguity(fresh):
    """If one part is definitively false, the composite is false."""
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs, step = _submit(fresh, op)
    blind = Verifier(fresh.source, durable=FixtureDurableEvidence(
        fresh.cluster.primary_origin, reachable=False))
    result = fresh.verify(
        step,
        AllOf(page_id=obs.page_id, parts=(
            TextPresence(page_id=obs.page_id, text="this text is definitely absent"),
            OperationRecorded(page_id=obs.page_id, operation_id=op),
        )),
        verifier=blind,
    )
    assert result.status is NOT
    assert result.reason is Reason.COMPOSITE_FAILED


def test_known_limitation_text_in_a_bare_div_is_invisible(fresh):
    """Pinning a real observation-layer limitation so it cannot hide.

    `submit_op.html` renders its confirmation inside a bare <div>. The
    observation collects text from h1-h3/p/li/td/label/span only, so that
    confirmation never reaches `text_blocks` even though a person can read it
    on screen. The Verifier faithfully reports what the observation contains,
    which here means NOT_SATISFIED for text that is genuinely on the page.

    This is an observation-format limitation, not a Verifier defect, and the
    observation format is explicitly frozen for this gate. It is the reason
    Experiment 6's worker could never record a SATISFIED verification.
    """
    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs = fresh.goto("/p/submit_op")
    fresh.kernel.type_text(fresh.find(obs, name="Operation ID").target, op)
    obs2 = fresh.observe()
    step = fresh.act(
        obs2, lambda: fresh.kernel.click(fresh.find(obs2, name="Submit booking").target)
    )
    time.sleep(0.5)

    on_screen = fresh.kernel.page_object().inner_text("#confirmation")
    assert f"Reference {op}" in on_screen, "the page really does show the confirmation"

    text_result = fresh.verify(
        step, TextPresence(page_id=obs2.page_id, text=f"Reference {op}")
    )
    assert text_result.status is NOT, "div text unexpectedly became observable"

    # The durable channel is unaffected, which is exactly why consequential
    # verification is answered from durable evidence rather than page text.
    durable_result = fresh.verify(
        step, OperationRecorded(page_id=obs2.page_id, operation_id=op)
    )
    assert durable_result.status is SAT
