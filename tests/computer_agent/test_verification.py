"""Unit tests for computer_agent.verification: predicate vocabulary,
three-valued logic, outcome classification, confirmation/polling, and
structural independence from executor claims."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from computer_agent import verification as V
from computer_agent.verification import (
    UNAVAILABLE,
    Absent,
    And,
    Check,
    Contains,
    Count,
    CountDelta,
    Delta,
    Eq,
    Exists,
    Indeterminate,
    InRange,
    Ne,
    OneOf,
    Or,
    Transition,
    Tri,
    Unchanged,
    UnchangedExcept,
    VerificationOutcome as O,
    VerificationSpec,
    evaluate,
    judge,
    verify,
)

BEFORE = {"records": {"r1": {"status": "open", "qty": 3}, "r2": {"status": "open", "qty": 1}}, "outbox": []}
AFTER = {"records": {"r1": {"status": "closed", "qty": 5}, "r2": {"status": "open", "qty": 1}},
         "outbox": [{"to": "a", "body": "hi"}]}


def val(p, before=BEFORE, after=AFTER):
    return p.evaluate(before, after).value


@pytest.mark.parametrize("pred,expected", [
    (Eq(("records", "r1", "status"), "closed"), Tri.TRUE),
    (Eq(("records", "r1", "status"), "open"), Tri.FALSE),
    (Eq(("records", "nope", "status"), "closed"), Tri.FALSE),
    (Ne(("records", "r1", "status"), "open"), Tri.TRUE),
    (Exists(("records", "r2")), Tri.TRUE),
    (Exists(("records", "r9")), Tri.FALSE),
    (Absent(("records", "r9")), Tri.TRUE),
    (Absent(("records", "r1")), Tri.FALSE),
    (Contains(("outbox",), {"to": "a", "body": "hi"}), Tri.TRUE),
    (Contains(("outbox",), {"to": "b", "body": "hi"}), Tri.FALSE),
    (Contains(("records",), "r1"), Tri.TRUE),
    (OneOf(("records", "r1", "status"), ("closed", "archived")), Tri.TRUE),
    (InRange(("records", "r1", "qty"), 4, 6), Tri.TRUE),
    (InRange(("records", "r1", "status"), 0, 9), Tri.FALSE),
    (Count(("records",), 2, 2), Tri.TRUE),
    (Count(("records",), 1, 1, where={"status": "open"}), Tri.TRUE),
    (CountDelta(("outbox",), 1, 1), Tri.TRUE),
    (CountDelta(("records",), 1, 1), Tri.FALSE),
    (Delta(("records", "r1", "qty"), 2, 2), Tri.TRUE),
    (Delta(("records", "r1", "qty"), 1, 1), Tri.FALSE),
    (Transition(("records", "r1", "status"), "open", "closed"), Tri.TRUE),
    (Transition(("records", "r2", "status"), "open", "closed"), Tri.FALSE),
    (Unchanged(("records", "r2")), Tri.TRUE),
    (Unchanged(("records",)), Tri.FALSE),
    (UnchangedExcept(("records",), frozenset({"r1"})), Tri.TRUE),
    (UnchangedExcept(("records",), frozenset({"r2"})), Tri.FALSE),
])
def test_primitives(pred, expected):
    assert val(pred) == expected


def test_unchanged_except_catches_added_keys():
    after = {**AFTER, "records": {**AFTER["records"], "r1#2": {"status": "closed"}}}
    assert val(UnchangedExcept(("records",), frozenset({"r1"})), after=after) == Tri.FALSE


def test_indeterminate_is_unknown_never_true():
    after = {"records": {"r1": {"status": Indeterminate("syncing")}}, "outbox": []}
    for p in (Eq(("records", "r1", "status"), "closed"), Ne(("records", "r1", "status"), "open"),
              Exists(("records", "r1")), Unchanged(("records",)), Count(("records",), 0, 9)):
        assert val(p, after=after) == Tri.UNKNOWN, p
    for p in (Eq(("records",), 1), Delta(("records", "r1", "qty"), 0, 9), CountDelta(("outbox",), 0, 0)):
        assert val(p, after=UNAVAILABLE) == Tri.UNKNOWN
        assert val(p, before=UNAVAILABLE) == Tri.UNKNOWN or p.__class__ is Eq
    assert Indeterminate("x") != Indeterminate("x")


def test_kleene_and_or():
    t, f = Eq(("records", "r1", "status"), "closed"), Eq(("records", "r1", "status"), "open")
    u = Eq(("records", "r1", "status"), "closed")
    after_u = {"records": {"r1": {"status": Indeterminate("?")}}, "outbox": []}
    assert val(And((t, t))) == Tri.TRUE and val(And((t, f))) == Tri.FALSE
    assert val(Or((f, t))) == Tri.TRUE and val(Or((f, f))) == Tri.FALSE
    assert val(And((u, Exists(("outbox",)))), after=after_u) == Tri.UNKNOWN
    assert val(And((u, Absent(("outbox",)))), after=after_u) == Tri.FALSE  # FALSE dominates AND
    assert val(Or((u, Exists(("outbox",)))), after=after_u) == Tri.TRUE  # TRUE dominates OR
    with pytest.raises(ValueError):
        And(())


def test_check_callback_is_bounded():
    assert val(Check("grew", lambda b, a: len(a["outbox"]) > len(b["outbox"]))) == Tri.TRUE
    assert val(Check("boom", lambda b, a: 1 / 0)) == Tri.UNKNOWN
    assert val(Check("truthy-not-bool", lambda b, a: "yes")) == Tri.UNKNOWN

    def mutate(b, a):
        a["outbox"].clear()
        return True

    after = {"records": {}, "outbox": [1]}
    val(Check("mutator", mutate), after=after)
    assert after["outbox"] == [1], "callback must not be able to mutate observed evidence"


def test_empty_spec_refused():
    with pytest.raises(ValueError):
        VerificationSpec(success=())


SPEC = VerificationSpec(
    success=(Eq(("records", "r1", "status"), "closed"), Eq(("records", "r1", "qty"), 5)),
    invariants=(UnchangedExcept(("records",), frozenset({"r1"})), CountDelta(("outbox",), 0, 1)),
)


def test_outcome_classification():
    assert evaluate(SPEC, BEFORE, AFTER).outcome == O.VERIFIED_SUCCESS
    assert evaluate(SPEC, BEFORE, BEFORE).outcome == O.VERIFIED_FAILURE
    half = {**BEFORE, "records": {**BEFORE["records"], "r1": {"status": "closed", "qty": 3}}}
    assert evaluate(SPEC, BEFORE, half).outcome == O.PARTIAL_SUCCESS
    collateral = {**AFTER, "records": {**AFTER["records"], "r2": {"status": "closed", "qty": 1}}}
    assert evaluate(SPEC, BEFORE, collateral).outcome == O.UNEXPECTED_SIDE_EFFECT
    assert evaluate(SPEC, BEFORE, UNAVAILABLE).outcome == O.INCONCLUSIVE
    assert evaluate(SPEC, UNAVAILABLE, AFTER).outcome == O.INCONCLUSIVE


def test_judge_requires_confirmed_success():
    assert judge(SPEC, BEFORE, []).outcome == O.INCONCLUSIVE
    assert judge(SPEC, BEFORE, [AFTER]).outcome == O.INCONCLUSIVE  # seen once, unconfirmed
    assert judge(SPEC, BEFORE, [AFTER, AFTER]).outcome == O.VERIFIED_SUCCESS
    assert judge(SPEC, BEFORE, [AFTER, BEFORE, BEFORE]).outcome == O.VERIFIED_FAILURE  # transient
    assert judge(SPEC, BEFORE, [BEFORE, AFTER, AFTER]).outcome == O.VERIFIED_SUCCESS  # delayed
    assert judge(SPEC, BEFORE, [UNAVAILABLE, AFTER, AFTER]).outcome == O.VERIFIED_SUCCESS


def test_verify_polls_bounded_and_returns_evidence():
    seq = iter([BEFORE, AFTER, AFTER, AFTER, AFTER])
    result, observations = verify(SPEC, BEFORE, lambda: next(seq), max_observations=4)
    assert result.outcome == O.VERIFIED_SUCCESS and len(observations) == 3
    assert judge(SPEC, BEFORE, observations) == result  # re-derivable from persisted evidence
    calls = []
    result, observations = verify(SPEC, BEFORE, lambda: calls.append(1) or BEFORE, max_observations=4)
    assert result.outcome == O.VERIFIED_FAILURE and len(calls) == 4


def test_verifier_has_no_channel_for_executor_claims():
    for fn in (verify, judge, evaluate):
        params = set(inspect.signature(fn).parameters)
        assert params <= {"spec", "before", "after", "observe", "observations", "max_observations"}, fn
    tree = ast.parse(Path(V.__file__).read_text())
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= {"__future__", "copy", "dataclasses", "enum", "typing"}, imported
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    identifiers |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    assert not {i for i in identifiers if "claim" in i.lower() or "executor" in i.lower()}
