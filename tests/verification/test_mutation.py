"""Mutation testing: evidence that the suite can actually fail.

A suite where everything passes proves nothing unless breaking the thing under
test makes it fail. Each test here disables one specific guard and asserts that
a false SATISFIED appears — then the unmutated control shows it does not.

This mirrors the P0 campaign's use of deliberately-unsafe control arms
(`UNSAFE_NAME_RESOLVE`, `blind_replay`), which is what established that the safe
mechanisms were load-bearing rather than incidental.
"""

from __future__ import annotations

import pytest

from browser_agent_v2.verification import (
    ElementPresence,
    FieldValueEquals,
    OperationRecorded,
    TextPresence,
    VerificationRequest,
    VerificationStatus,
    Verifier,
)
from browser_agent_v2.verification import verifier as verifier_module
from tests.verification.harness import FixtureDurableEvidence, FrozenEvidenceSource

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


def test_disabling_the_freshness_guard_produces_a_false_success(fresh, monkeypatch):
    """The stale-evidence guard is what prevents the false success.

    With `_advanced` forced to True, the pre-action snapshot is accepted and the
    Verifier reports SATISFIED for a state that is no longer true. That is
    exactly the failure the guard exists to prevent, and seeing it appear on
    demand is what makes the passing test meaningful.
    """
    obs_before = fresh.goto("/p/verify_outcomes")
    step = fresh.act(
        obs_before,
        lambda: fresh.kernel.click(fresh.find(obs_before, name="Show panel").target),
    )
    postcondition = ElementPresence(
        page_id=obs_before.page_id, role="button", name="Close panel",
        expect_present=False,
    )
    stale = Verifier(FrozenEvidenceSource(obs_before, fresh.kernel))

    guarded = fresh.verify(step, postcondition, verifier=stale)
    assert guarded.status is AMB, "control: the guard should refuse stale evidence"

    monkeypatch.setattr(verifier_module, "_advanced", lambda before, after: True)
    mutated = fresh.verify(step, postcondition, verifier=stale)
    assert mutated.status is SAT, (
        "mutation produced no false success, so the stale test was not "
        "exercising the freshness guard"
    )


def test_disabling_frame_pinning_produces_a_wrong_frame_false_success(fresh, monkeypatch):
    """Without the frame-identity refusal, a renumbered frame satisfies."""
    obs = fresh.goto("/p/frames")
    import time

    time.sleep(0.6)
    obs = fresh.observe()
    detach = fresh.find(obs, contains="Detach same-origin")
    step = fresh.act(obs, lambda: fresh.kernel.click(detach.target))
    time.sleep(0.4)

    unpinned = ElementPresence(
        page_id=obs.page_id, role="button", name="Confirm", frame_id="f1"
    )
    guarded = fresh.verify(step, unpinned)
    assert guarded.status is AMB, "control: an unpinned frame index must be refused"

    # Mutation: trust the positional index, which is what the original bug did.
    original = verifier_module.Verifier._verify_element
    monkeypatch.setattr(
        verifier_module.Verifier, "_verify_element",
        lambda self, pc, request: _trust_index(original, self, pc, request),
    )
    mutated = fresh.verify(step, unpinned)
    assert mutated.status is SAT, (
        "mutation produced no false success; the frame test was not exercising "
        "the frame-identity guard"
    )


def _trust_index(original, self, pc, request):
    """Re-create the pre-fix behaviour: resolve strictly by positional index."""
    from browser_agent_v2.verification.contracts import Check, satisfied, not_satisfied, Reason
    from browser_agent_v2.verification.evidence import EvidenceUnavailable

    try:
        obs = self._fresh(pc.page_id, request)
    except EvidenceUnavailable as exc:
        return self._unavailable("ElementPresence", exc)
    matches = [
        e for e in obs.elements
        if e.frame_id == pc.frame_id and e.role == pc.role
        and e.name.strip() == pc.name.strip()
    ]
    present = len(matches) > 0
    check = Check("element_presence", present == pc.expect_present)
    if present == pc.expect_present:
        return satisfied("ElementPresence", [check], **self._prov(obs))
    return not_satisfied("ElementPresence", Reason.ELEMENT_MISSING, [check],
                         **self._prov(obs))


def test_disabling_value_comparison_produces_a_false_success(fresh, monkeypatch):
    """If the value check stopped comparing, wrong text would pass."""
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    pc = FieldValueEquals(page_id=obs.page_id, target=el.target,
                          expected="Tampa", name="Plain text")
    step = fresh.act(obs, lambda: fresh.kernel.type_text(el.target, "Orlando"))

    guarded = fresh.verify(step, pc)
    assert guarded.status is NOT, "control: a wrong value must be rejected"

    monkeypatch.setattr(
        verifier_module.Verifier, "_read_field",
        lambda self, pc_, obs_: (pc_.expected, "mutated", None),
    )
    mutated = fresh.verify(step, pc)
    assert mutated.status is SAT, "the value test was not comparing anything"


def test_treating_unavailable_durable_evidence_as_success_is_detectable(fresh, monkeypatch):
    """The AMBIGUOUS-not-SATISFIED rule for consequential actions has teeth."""
    import time, uuid

    op = f"BK-{uuid.uuid4().hex[:10]}"
    obs = fresh.goto("/p/verify_submit")
    fresh.kernel.type_text(fresh.find(obs, name="Operation ID").target, op)
    obs2 = fresh.observe()
    step = fresh.act(
        obs2, lambda: fresh.kernel.click(fresh.find(obs2, name="Submit booking").target)
    )
    time.sleep(0.4)

    blind = Verifier(fresh.source, durable=FixtureDurableEvidence(
        fresh.cluster.primary_origin, reachable=False))
    pc = OperationRecorded(page_id=obs2.page_id, operation_id=op)

    guarded = fresh.verify(step, pc, verifier=blind)
    assert guarded.status is AMB, "control: an unreachable channel must be ambiguous"

    # Mutation: an optimistic channel that reports "found" when it cannot tell.
    class Optimistic:
        def lookup_operation(self, operation_id):
            from browser_agent_v2.verification import OperationRecord

            return OperationRecord(operation_id=operation_id, found=True)

    optimistic = Verifier(fresh.source, durable=Optimistic())
    mutated = fresh.verify(step, pc, verifier=optimistic)
    assert mutated.status is SAT, "the durable-evidence test was not load-bearing"


def test_page_scoping_mutation_produces_a_cross_page_false_success(fresh, monkeypatch):
    """Ignoring page scope lets another tab's text satisfy the check."""
    import time

    page_a = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    page_b = fresh.kernel.new_tab(fresh.url("/p/verify_page_failure"))
    time.sleep(0.3)
    try:
        obs_b = fresh.observe(page_b)
        pc = TextPresence(page_id=page_b, text="Success")
        guarded = fresh.verify(fresh.act(obs_b, lambda: None), pc)
        assert guarded.status is NOT, "control: page A's text must not satisfy page B"

        # Mutation: resolve the observation from whichever page is active.
        monkeypatch.setattr(
            verifier_module.Verifier, "_fresh",
            lambda self, page_id, request: self._source.observe(page_a),
        )
        mutated = fresh.verify(fresh.act(obs_b, lambda: None), pc)
        assert mutated.status is SAT, "the page-scoping test was not load-bearing"
    finally:
        for pid in (page_a, page_b):
            try:
                fresh.kernel.close_agent_tab(pid)
            except Exception:
                pass
