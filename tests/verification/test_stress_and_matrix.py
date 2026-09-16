"""Repeated runs of the critical primitives, and the classification matrix.

Two jobs:

1. Stress. A deterministic verifier that is right once is not evidence. Each
   critical primitive is repeated at the counts required by the gate.
2. Classification. Every outcome is scored against a known-correct label so
   false SATISFIED, false NOT_SATISFIED and false AMBIGUOUS are counted rather
   than assumed to be zero.

The counts are written to `tests/verification/results/` so the gate report
quotes measured numbers rather than the numbers the suite was asked for.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from pathlib import Path

import pytest

from browser_agent_v2.verification import (
    MAIN_FRAME,
    DownloadPresent,
    ElementPresence,
    FieldValueEquals,
    OperationRecorded,
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

RESULTS = Path(__file__).resolve().parent / "results"
TALLY: Counter = Counter()
MATRIX: list[dict] = []


def record(category: str, expected: VerificationStatus, actual: VerificationStatus):
    """Score one outcome against its known-correct label."""
    TALLY[f"{category}:runs"] += 1
    correct = expected is actual
    TALLY[f"{category}:pass" if correct else f"{category}:fail"] += 1
    TALLY[f"true_{expected.value}" if correct else f"false_{actual.value}"] += 1
    if not correct:
        TALLY[f"{category}:false_{actual.value}"] += 1
    MATRIX.append(
        {"category": category, "expected": expected.value,
         "actual": actual.value, "correct": correct}
    )
    return correct


# ------------------------------------------------------------------- TYPE


def test_stress_type_exact_verification(fresh):
    """50 runs: 25 correct values expected SATISFIED, 25 mutated expected NOT."""
    values = ["Tampa", "Orlando", "São Paulo", "a  b", " lead", "trail ",
              "O'Brien", "東京", "x" * 60, "12.50 USD", "a,b;c", "tab\tsep"]
    for i in range(50):
        want = values[i % len(values)]
        mutate = i % 2 == 1
        typed = (want + "!") if mutate else want
        expected = NOT if mutate else SAT
        obs = fresh.goto("/p/inputs")
        el = fresh.find(obs, name="Plain text")
        result, _ = fresh.act_and_verify(
            obs,
            lambda t=typed: fresh.kernel.type_text(el.target, t),
            FieldValueEquals(page_id=obs.page_id, target=el.target,
                             expected=want, name="Plain text"),
        )
        assert record("TYPE", expected, result.status), (
            f"run {i}: typed={typed!r} expected {expected} got {result.to_json()}"
        )
    assert TALLY["TYPE:runs"] == 50
    assert TALLY["TYPE:fail"] == 0


# ----------------------------------------------------------------- SELECT


def test_stress_select_verification(fresh):
    """30 runs alternating correct and incorrect option values."""
    options = ["us", "ca", "mx"]
    for i in range(30):
        chosen = options[i % 3]
        wrong = i % 2 == 1
        expect_value = options[(i + 1) % 3] if wrong else chosen
        expected = NOT if wrong else SAT
        obs = fresh.goto("/p/selects")
        el = fresh.find(obs, name="Country")
        result, _ = fresh.act_and_verify(
            obs,
            lambda c=chosen: fresh.kernel.select(el.target, c),
            SelectStub(obs.page_id, el.target, expect_value),
        )
        assert record("SELECT", expected, result.status), f"run {i}"
    assert TALLY["SELECT:runs"] == 30
    assert TALLY["SELECT:fail"] == 0


def SelectStub(page_id, target, expected_value):
    from browser_agent_v2.verification import SelectValueEquals

    return SelectValueEquals(page_id=page_id, target=target,
                             expected_value=expected_value, name="Country")


# ------------------------------------------------- wrong-control rejection


def test_stress_wrong_control_rejection(fresh):
    """50 runs. The kernel reports success every time; half are the wrong control."""
    for i in range(50):
        wrong = i % 2 == 1
        obs = fresh.goto("/p/verify_outcomes")
        name = "Decline request" if wrong else "Approve request"
        btn = fresh.find(obs, name=name)
        result, step = fresh.act_and_verify(
            obs,
            lambda t=btn.target: fresh.kernel.click(t),
            TextPresence(page_id=obs.page_id, text="Right outcome recorded"),
        )
        assert step.execution_status == "OK", "the click must always succeed"
        assert record("WRONG_CONTROL", NOT if wrong else SAT, result.status), (
            f"run {i}: clicked {name}"
        )
    assert TALLY["WRONG_CONTROL:runs"] == 50
    assert TALLY["WRONG_CONTROL:fail"] == 0


# ------------------------------------------------------------- NAVIGATION


def test_stress_navigation_verification(fresh):
    """30 runs alternating the intended destination and a decoy."""
    for i in range(30):
        wrong = i % 2 == 1
        obs = fresh.goto("/p/verify_outcomes")
        name = "Go somewhere else" if wrong else "Go to confirmation"
        btn = fresh.find(obs, name=name)
        result, _ = fresh.act_and_verify(
            obs,
            lambda t=btn.target: fresh.kernel.click(t),
            UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm")),
        )
        assert record("NAVIGATION", NOT if wrong else SAT, result.status), f"run {i}"
    assert TALLY["NAVIGATION:runs"] == 30
    assert TALLY["NAVIGATION:fail"] == 0


# ---------------------------------------------------------- PAGE / FRAME


def test_stress_page_and_frame_scoping(fresh):
    """30 runs: 15 page-scoped, 15 frame-scoped, half of each wrongly scoped."""
    page_a = fresh.kernel.new_tab(fresh.url("/p/verify_page_success"))
    page_b = fresh.kernel.new_tab(fresh.url("/p/verify_page_failure"))
    time.sleep(0.3)
    try:
        for i in range(15):
            wrong_page = i % 2 == 1
            # "Success" exists only on page A
            target_page = page_b if wrong_page else page_a
            obs = fresh.observe(target_page)
            result = fresh.verify(
                fresh.act(obs, lambda: None),
                TextPresence(page_id=target_page, text="Success"),
            )
            assert record("PAGE_SCOPE", NOT if wrong_page else SAT, result.status), i
    finally:
        for pid in (page_a, page_b):
            try:
                fresh.kernel.close_agent_tab(pid)
            except Exception:
                pass

    for i in range(15):
        obs = fresh.goto("/p/frames")
        time.sleep(0.45)
        obs = fresh.observe()
        children = sorted({e.frame_id for e in obs.elements
                           if e.frame_id != obs.main_frame_id})
        assert children, "fixture must expose child frames"
        # Alternate a correctly scoped child-frame check against a deliberately
        # wrong scope: a control that exists only in a child frame, asserted
        # against the main frame.
        wrong_scope = i % 2 == 1
        fresh.kernel.page_object().evaluate(
            "() => { const b = document.getElementById('top-action'); if (b) b.remove(); }"
        )
        obs = fresh.observe()
        pc = ElementPresence(
            page_id=obs.page_id, role="button", name="Confirm",
            frame_id=MAIN_FRAME if wrong_scope else children[0],
        )
        result = fresh.verify(fresh.act(obs, lambda: None), pc)
        assert record("FRAME_SCOPE", NOT if wrong_scope else SAT, result.status), i

    assert TALLY["PAGE_SCOPE:runs"] + TALLY["FRAME_SCOPE:runs"] == 30
    assert TALLY["PAGE_SCOPE:fail"] == 0
    assert TALLY["FRAME_SCOPE:fail"] == 0


# ----------------------------------------------------------- STALE EVIDENCE


def test_stress_stale_evidence_rejection(fresh):
    """30 runs. A pre-action snapshot must never satisfy a post-action claim."""
    for i in range(30):
        obs_before = fresh.goto("/p/verify_outcomes")
        step = fresh.act(
            obs_before,
            lambda: fresh.kernel.click(
                fresh.find(obs_before, name="Show panel").target),
        )
        stale = Verifier(FrozenEvidenceSource(obs_before, fresh.kernel))
        result = fresh.verify(
            step,
            ElementPresence(page_id=obs_before.page_id, role="button",
                            name="Close panel", expect_present=False),
            verifier=stale,
        )
        assert record("STALE", AMB, result.status), f"run {i}: {result.to_json()}"
    assert TALLY["STALE:runs"] == 30
    assert TALLY["STALE:fail"] == 0


# ------------------------------------------------------------ POPUP / PAGE


def test_stress_popup_verification(fresh):
    """20 runs alternating the expected popup and an unrelated one."""
    for i in range(20):
        wrong = i % 2 == 1
        obs = fresh.goto("/p/verify_outcomes")
        name = "Open other popup" if wrong else "Open confirmation popup"
        btn = fresh.find(obs, contains=name)
        step = fresh.act_expecting_page(obs, lambda t=btn.target: fresh.kernel.click(t))
        assert step.new_page_ids, f"run {i}: no popup"
        popup = step.new_page_ids[0]
        result = fresh.verify(
            step,
            PageState(page_id=popup, expect_exists=True,
                      expect_opener_page_id=obs.page_id,
                      expect_url=fresh.url("/p/verify_confirm")),
        )
        assert record("POPUP", NOT if wrong else SAT, result.status), f"run {i}"
        fresh.kernel.close_agent_tab(popup)
    assert TALLY["POPUP:runs"] == 20
    assert TALLY["POPUP:fail"] == 0


# --------------------------------------------------------------- DOWNLOAD


def test_stress_download_verification(fresh):
    """20 runs alternating a real completed download and no download."""
    for i in range(20):
        wrong = i % 2 == 1
        fresh.downloads.reset()
        obs = fresh.goto("/p/verify_outcomes")
        page = fresh.kernel.page_object()
        name = "Do nothing" if wrong else "Download report"
        el = fresh.find(obs, name=name)
        step = fresh.act(
            obs,
            lambda t=el.target: fresh.downloads.capture(
                page, lambda: fresh.kernel.click(t), timeout_ms=1500
            ),
        )
        result = fresh.verify(
            step,
            DownloadPresent(page_id=obs.page_id, filename="report.csv", min_bytes=10),
        )
        assert record("DOWNLOAD", NOT if wrong else SAT, result.status), f"run {i}"
    assert TALLY["DOWNLOAD:runs"] == 20
    assert TALLY["DOWNLOAD:fail"] == 0


# -------------------------------------------------------------- AMBIGUITY


def test_stress_ambiguity_classification(fresh):
    """20 runs over the distinct routes to AMBIGUOUS."""
    obs = fresh.goto("/p/verify_outcomes")
    broken = Verifier(BrokenEvidenceSource("DISCONNECTED"))
    stale = Verifier(FrozenEvidenceSource(obs, fresh.kernel))
    cases = [
        (broken, TextPresence(page_id=obs.page_id, text="x")),
        (broken, ElementPresence(page_id=obs.page_id, role="button", name="x")),
        (broken, UrlIs(page_id=obs.page_id, expected="x")),
        (broken, PageState(page_id=obs.page_id)),
        (broken, FieldValueEquals(page_id=obs.page_id, target="t", expected="x")),
        # no durable channel configured, for a consequential action
        (Verifier(fresh.source),
         OperationRecorded(page_id=obs.page_id, operation_id="never")),
        # no artifact store configured
        (Verifier(fresh.source),
         DownloadPresent(page_id=obs.page_id, filename="nothing.csv")),
    ]
    for i in range(20):
        if i % 7 == 6:
            # stale evidence: a pre-action snapshot replayed after an action
            step = fresh.act(
                obs, lambda: fresh.kernel.click(
                    fresh.find(obs, name="Show panel").target)
            )
            result = fresh.verify(
                step,
                ElementPresence(page_id=obs.page_id, role="button",
                                name="Close panel", expect_present=False),
                verifier=stale,
            )
        else:
            verifier, pc = cases[i % len(cases)]
            result = verifier.verify(VerificationRequest(postcondition=pc))
        assert record("AMBIGUITY", AMB, result.status), (
            f"run {i}: -> {result.to_json()}"
        )
        assert result.reason.value in {
            "EVIDENCE_UNAVAILABLE", "STALE_EVIDENCE",
            "EVIDENCE_CONTRADICTORY", "FIELD_AMBIGUOUS",
        }
    assert TALLY["AMBIGUITY:runs"] == 20
    assert TALLY["AMBIGUITY:fail"] == 0


# ----------------------------------------------------------------- report


@pytest.fixture(scope="module", autouse=True)
def _emit_report():
    yield
    RESULTS.mkdir(parents=True, exist_ok=True)
    categories = sorted({m["category"] for m in MATRIX})
    payload = {
        "per_category": {
            c: {
                "runs": TALLY[f"{c}:runs"],
                "pass": TALLY[f"{c}:pass"],
                "fail": TALLY[f"{c}:fail"],
                "false_SATISFIED": TALLY[f"{c}:false_SATISFIED"],
            }
            for c in categories
        },
        "classification_matrix": {
            "true_SATISFIED": TALLY["true_SATISFIED"],
            "true_NOT_SATISFIED": TALLY["true_NOT_SATISFIED"],
            "true_AMBIGUOUS": TALLY["true_AMBIGUOUS"],
            "false_SATISFIED": TALLY["false_SATISFIED"],
            "false_NOT_SATISFIED": TALLY["false_NOT_SATISFIED"],
            "false_AMBIGUOUS": TALLY["false_AMBIGUOUS"],
        },
        "total_runs": len(MATRIX),
    }
    (RESULTS / "stress_and_matrix.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print("\n=== verifier stress / classification ===")
    print(json.dumps(payload, indent=2))


def test_zz_no_false_satisfied_anywhere():
    """Runs last. The single number that decides the gate."""
    assert TALLY["false_SATISFIED"] == 0, (
        f"false SATISFIED outcomes: "
        f"{[m for m in MATRIX if not m['correct'] and m['actual'] == 'SATISFIED']}"
    )
