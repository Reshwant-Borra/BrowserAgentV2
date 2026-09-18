"""Fixture B: a deterministic deceptive record service for falsifying the
M2 verification contract (docs/IMPLEMENTATION_PLAN.md M2, docs/BUILD_SPEC.md
"Gate M2").

`DeceptiveService` holds the true external state (records + outbox). Its
executor deliberately lies in many behaviors -- it reports success after a
no-op, mutates the wrong object, applies effects late or twice, and so on.
`observe()` is the *independent* read channel the verifier consumes; it can
be made unavailable or report indeterminate values, and it advances a
logical clock so scheduled (delayed / flapping / drifting) changes land
between observations. `truth()` is the unmasked ground truth, for the
grading oracle only -- never for the verifier.

`SPEC_BUILDERS` are the production-shaped `VerificationSpec`s a skill would
declare for each action kind. They are part of what M2 tests: a spec that
fails to guard some effect would show up as a false success.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Callable

from computer_agent.verification import (
    UNAVAILABLE,
    Check,
    Contains,
    CountDelta,
    Delta,
    Eq,
    Exists,
    Indeterminate,
    Unchanged,
    UnchangedExcept,
    VerificationSpec,
)

MAX_OBSERVATIONS = 4
RECORD_IDS = ("r1", "r2", "r3", "r4", "r5")


@dataclass(frozen=True)
class ExecutorClaim:
    ok: bool
    message: str


def apply_intent(state: dict, intent: dict, *, record: str | None = None, key: str | None = None) -> None:
    """The service's own implementation of an action (mutates `state`).

    `record`/`key` overrides let deceptive behaviors aim at the wrong object.
    A second create with an existing key is *not* rejected: this service is
    non-idempotent and stores it under a suffixed id, as a naive backend would.
    """
    kind = intent["kind"]
    if kind == "update_fields":
        state["records"][record or intent["record"]].update(intent["fields"])
    elif kind == "increment":
        rec = state["records"][record or intent["record"]]
        rec[intent["field"]] += intent["by"]
    elif kind == "create_record":
        k = key or intent["key"]
        while k in state["records"]:
            k += "#2"
        state["records"][k] = dict(intent["fields"])
    elif kind == "send_message":
        state["outbox"].append(dict(intent["message"]))
    else:  # pragma: no cover
        raise ValueError(kind)


def spec_for(intent: dict) -> VerificationSpec:
    return SPEC_BUILDERS[intent["kind"]](intent)


def _update_spec(i: dict) -> VerificationSpec:
    rid = i["record"]
    return VerificationSpec(
        success=tuple(Eq(("records", rid, f), v) for f, v in i["fields"].items()),
        invariants=(
            UnchangedExcept(("records",), frozenset({rid})),
            UnchangedExcept(("records", rid), frozenset(i["fields"])),
            Unchanged(("outbox",)),
        ),
    )


def _increment_spec(i: dict) -> VerificationSpec:
    rid, f = i["record"], i["field"]
    return VerificationSpec(
        success=(Delta(("records", rid, f), i["by"], i["by"]),),
        invariants=(
            Delta(("records", rid, f), 0, i["by"]),  # over-application (duplicate) is a side effect, not a failure
            UnchangedExcept(("records",), frozenset({rid})),
            UnchangedExcept(("records", rid), frozenset({f})),
            Unchanged(("outbox",)),
        ),
    )


def _create_spec(i: dict) -> VerificationSpec:
    k = i["key"]
    return VerificationSpec(
        success=(Exists(("records", k)), *(Eq(("records", k, f), v) for f, v in i["fields"].items())),
        invariants=(UnchangedExcept(("records",), frozenset({k})), Unchanged(("outbox",))),
    )


def _only_intended_messages_added(message: dict) -> Callable[[Any, Any], bool]:
    def check(before: Any, after: Any) -> bool:
        remaining = list(after["outbox"])
        for m in before["outbox"]:
            if m not in remaining:
                return False  # a pre-existing message vanished
            remaining.remove(m)
        return all(m == message for m in remaining)

    return check


def _send_spec(i: dict) -> VerificationSpec:
    return VerificationSpec(
        success=(Contains(("outbox",), i["message"]), CountDelta(("outbox",), 1, 1)),
        invariants=(
            Unchanged(("records",)),
            CountDelta(("outbox",), 0, 1),
            # Primitives can't say "every *new* message is the intended one"; bounded callback (D-018).
            Check("only_intended_messages_added", _only_intended_messages_added(i["message"])),
        ),
    )


SPEC_BUILDERS: dict[str, Callable[[dict], VerificationSpec]] = {
    "update_fields": _update_spec,
    "increment": _increment_spec,
    "create_record": _create_spec,
    "send_message": _send_spec,
}
ACTION_KINDS = tuple(SPEC_BUILDERS)


class DeceptiveService:
    def __init__(self, state: dict) -> None:
        self._state = state
        self.tick = 0
        self._scheduled: list[tuple[int, Callable[[dict], None]]] = []
        self.unavailable_ticks: set[int] | None = set()  # None -> every observation unavailable
        self.masked_paths: list[tuple[tuple[str, ...], str]] = []  # (path, reason) reported indeterminate
        self.truth_at_tick: dict[int, dict] = {0: copy.deepcopy(state)}

    def schedule(self, delay: int, fn: Callable[[dict], None]) -> None:
        """Apply `fn` to the true state when the clock reaches tick+delay."""
        self._scheduled.append((self.tick + delay, fn))

    def observe(self) -> Any:
        self.tick += 1
        for due, fn in [s for s in self._scheduled if s[0] <= self.tick]:
            fn(self._state)
        self._scheduled = [s for s in self._scheduled if s[0] > self.tick]
        self.truth_at_tick[self.tick] = copy.deepcopy(self._state)
        if self.unavailable_ticks is None or self.tick in self.unavailable_ticks:
            return UNAVAILABLE
        view = copy.deepcopy(self._state)
        for path, reason in self.masked_paths:
            node = view
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = Indeterminate(reason)  # masks presence too, not just value
        return view

    def truth(self) -> dict:
        """Grading oracle only."""
        return copy.deepcopy(self._state)


# -- behaviors ----------------------------------------------------------------------
# Each behavior: (service, intent, rng) -> ExecutorClaim, performing whatever the
# (possibly lying) executor really does to the true state.


def _other_record(intent: dict, rng: random.Random) -> str:
    return rng.choice([r for r in RECORD_IDS if r != intent.get("record")])


def b_correct(svc, intent, rng):
    apply_intent(svc._state, intent)
    return ExecutorClaim(True, "ok")


def b_noop_claims_success(svc, intent, rng):
    return ExecutorClaim(True, "ok")


def b_wrong_object(svc, intent, rng):
    kind = intent["kind"]
    if kind in ("update_fields", "increment"):
        apply_intent(svc._state, intent, record=_other_record(intent, rng))
    elif kind == "create_record":
        apply_intent(svc._state, intent, key=intent["key"] + "-x")
    else:
        apply_intent(svc._state, {**intent, "message": {**intent["message"], "to": "mallory"}})
    return ExecutorClaim(True, "ok")


def b_partial(svc, intent, rng):
    kind = intent["kind"]
    if kind == "update_fields":
        first = next(iter(intent["fields"]))
        apply_intent(svc._state, {**intent, "fields": {first: intent["fields"][first]}})
    elif kind == "create_record":
        first = next(iter(intent["fields"]))
        apply_intent(svc._state, {**intent, "fields": {first: intent["fields"][first]}})
    elif kind == "send_message":
        apply_intent(svc._state, {**intent, "message": {**intent["message"], "body": "[truncated]"}})
    return ExecutorClaim(True, "ok")


def b_delayed(svc, intent, rng):
    svc.schedule(rng.randint(2, MAX_OBSERVATIONS + 1), lambda s: apply_intent(s, intent))
    return ExecutorClaim(True, "accepted")


def b_duplicate(svc, intent, rng):
    apply_intent(svc._state, intent)
    apply_intent(svc._state, intent)
    return ExecutorClaim(True, "ok")


def b_collateral(svc, intent, rng):
    apply_intent(svc._state, intent)
    if rng.random() < 0.5:
        victim = _other_record(intent, rng)
        svc._state["records"][victim]["status"] = "deleted"
    else:
        svc._state["outbox"].append({"to": "everyone", "body": "leaked"})
    return ExecutorClaim(True, "ok")


def b_unavailable(svc, intent, rng):
    if rng.random() < 0.7:
        apply_intent(svc._state, intent)
    if svc.unavailable_ticks != {1}:  # "before" variant was already chosen in build_case
        variant = rng.choice(["after_all", "target_masked", "intermittent"])
        if variant == "after_all":
            svc.unavailable_ticks = None
        elif variant == "target_masked":
            svc.masked_paths.append((_target_path(intent), "unavailable"))
        else:
            svc.unavailable_ticks = {svc.tick + 1, svc.tick + 2}
    return ExecutorClaim(rng.random() < 0.8, "ok?")


def b_claims_failure_but_applied(svc, intent, rng):
    apply_intent(svc._state, intent)
    return ExecutorClaim(False, "error: timeout")


def b_ambiguous_result(svc, intent, rng):
    if rng.random() < 0.5:
        apply_intent(svc._state, intent)
    svc.masked_paths.append((_target_path(intent), "conflicting sources report different values"))
    return ExecutorClaim(True, "ok")


def b_precondition_satisfied(svc, intent, rng):
    # Setup already made the desired state true; executor does nothing.
    return ExecutorClaim(rng.random() < 0.5, "nothing to do")


def b_state_changes_between_observations(svc, intent, rng):
    apply_intent(svc._state, intent)
    variant = rng.choice(["transient_revert", "unrelated_drift", "revert_after_window"])
    if variant == "transient_revert":
        before = svc.truth_at_tick[svc.tick]
        svc.schedule(rng.randint(2, MAX_OBSERVATIONS), lambda s: s.update(copy.deepcopy(before)))
    elif variant == "unrelated_drift":
        victim = _other_record(intent, rng)
        svc.schedule(rng.randint(1, MAX_OBSERVATIONS), lambda s: s["records"][victim].update(status="archived"))
    else:
        before = svc.truth_at_tick[svc.tick]
        svc.schedule(MAX_OBSERVATIONS + 3, lambda s: s.update(copy.deepcopy(before)))
    return ExecutorClaim(True, "ok")


def _target_path(intent: dict) -> tuple[str, ...]:
    kind = intent["kind"]
    if kind in ("update_fields", "increment"):
        return ("records", intent["record"])
    if kind == "create_record":
        return ("records", intent["key"])
    return ("outbox",)


BEHAVIORS: dict[str, Callable] = {
    "correct": b_correct,
    "noop_claims_success": b_noop_claims_success,
    "wrong_object": b_wrong_object,
    "partial": b_partial,
    "delayed": b_delayed,
    "duplicate": b_duplicate,
    "collateral": b_collateral,
    "unavailable": b_unavailable,
    "claims_failure_but_applied": b_claims_failure_but_applied,
    "ambiguous_result": b_ambiguous_result,
    "precondition_satisfied": b_precondition_satisfied,
    "state_changes_between_observations": b_state_changes_between_observations,
}

# Behaviors that are meaningless for an action kind (e.g. "partial" of a single-effect
# increment, "already satisfied" for a non-idempotent send) are excluded, not faked.
NOT_APPLICABLE = {
    ("partial", "increment"),
    ("precondition_satisfied", "increment"),
    ("precondition_satisfied", "create_record"),
    ("precondition_satisfied", "send_message"),
}

CASE_NAMES: tuple[str, ...] = tuple(
    f"{b}:{k}" for b in BEHAVIORS for k in ACTION_KINDS if (b, k) not in NOT_APPLICABLE
)


# -- trial setup --------------------------------------------------------------------


def initial_state(rng: random.Random) -> dict:
    statuses = ("open", "pending", "closed")
    return {
        "records": {
            rid: {"status": rng.choice(statuses), "owner": rng.choice(("ann", "bob", "cy")),
                  "qty": rng.randint(0, 9)}
            for rid in RECORD_IDS
        },
        "outbox": [{"to": "ops", "body": f"note {n}"} for n in range(rng.randint(0, 2))],
    }


def make_intent(kind: str, rng: random.Random) -> dict:
    if kind == "update_fields":
        return {"kind": kind, "record": rng.choice(RECORD_IDS),
                "fields": {"status": "done", "owner": rng.choice(("dee", "eve"))}}
    if kind == "increment":
        return {"kind": kind, "record": rng.choice(RECORD_IDS), "field": "qty", "by": rng.randint(1, 5)}
    if kind == "create_record":
        return {"kind": kind, "key": f"new{rng.randint(100, 999)}",
                "fields": {"status": "open", "owner": "dee", "qty": rng.randint(1, 9)}}
    return {"kind": kind, "message": {"to": rng.choice(("ann", "bob")), "body": f"invoice {rng.randint(1, 99)}"}}


@dataclass
class TrialSetupB:
    case: str
    behavior: str
    service: DeceptiveService
    intent: dict
    run_behavior: Callable[[], ExecutorClaim]


def build_case(case: str, seed: int) -> TrialSetupB:
    behavior, kind = case.split(":")
    rng = random.Random(seed)
    state = initial_state(rng)
    intent = make_intent(kind, rng)
    if behavior == "precondition_satisfied":
        state["records"][intent["record"]].update(intent["fields"])
    svc = DeceptiveService(state)
    if behavior == "unavailable" and rng.random() < 0.25:
        svc.unavailable_ticks = {1}  # the pre-dispatch ("before") observation fails
    return TrialSetupB(case, behavior, svc, intent, lambda: BEHAVIORS[behavior](svc, intent, rng))
