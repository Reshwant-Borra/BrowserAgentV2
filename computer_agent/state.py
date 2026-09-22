"""Authoritative controller state, materialized deterministically from the journal (M3).

`replay(events)` is a pure fold: the same events always produce an equal
`TaskState`. It also enforces the action lifecycle -- an event that is not
a legal transition from the action's current phase (dispatch without a
persisted intent, commit without verified success, step completion without
a committed verified action, ...) raises `JournalIntegrityError` rather
than being materialized into plausible-looking state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .journal import Event, EventType as E
from .types import EffectClass
from .verification import VerificationOutcome


class JournalIntegrityError(Exception):
    pass


class Phase:
    INTENT_PERSISTED = "INTENT_PERSISTED"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    DISPATCH_RETURNED = "DISPATCH_RETURNED"
    OBSERVED_AFTER = "OBSERVED_AFTER"
    VERIFIED = "VERIFIED"
    RETRY_PENDING = "RETRY_PENDING"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    COMMITTED = "COMMITTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ABANDONED = "ABANDONED"


TERMINAL_PHASES = {Phase.COMMITTED, Phase.NEEDS_REVIEW, Phase.ABANDONED}
DISPATCHED_UNRESOLVED = {Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED}

# event type -> phases it may legally follow
_ALLOWED_FROM: dict[E, set[str]] = {
    E.FRESHNESS_PASSED: {Phase.INTENT_PERSISTED, Phase.RETRY_PENDING},
    E.FRESHNESS_FAILED: {Phase.INTENT_PERSISTED, Phase.RETRY_PENDING},
    E.ACTION_ABANDONED: {Phase.INTENT_PERSISTED, Phase.RETRY_PENDING},
    E.DISPATCH_STARTED: {Phase.INTENT_PERSISTED, Phase.RETRY_PENDING},
    E.DISPATCH_RETURNED: {Phase.DISPATCH_STARTED},
    E.OBSERVED_AFTER: {Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED},
    E.VERIFICATION_RECORDED: {Phase.OBSERVED_AFTER},
    E.OUTCOME_RECONCILED: {Phase.VERIFIED},
    E.ACTION_COMMITTED: {Phase.VERIFIED},
    E.ACTION_FAILED: {Phase.VERIFIED},
    E.OUTCOME_UNKNOWN: {Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED, Phase.VERIFIED},
    E.NEEDS_REVIEW: {Phase.VERIFIED, Phase.OUTCOME_UNKNOWN},
}


@dataclass
class ActionState:
    action_id: str
    step_id: str
    kind: str
    args: dict[str, Any]
    effect_class: EffectClass
    target_spec: dict[str, Any]
    phase: str = Phase.INTENT_PERSISTED
    dispatches: int = 0
    before: Any = None
    observations: list[Any] = field(default_factory=list)
    outcome: str | None = None
    reconciled: bool = False
    history: list[str] = field(default_factory=list)


@dataclass
class StepState:
    step_id: str
    plan: dict[str, Any]
    status: str = "PENDING"  # PENDING | COMPLETED | BLOCKED | NEEDS_REVIEW
    action_ids: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class TaskState:
    task_id: str
    granted_kinds: tuple[str, ...] = ()
    steps: dict[str, StepState] = field(default_factory=dict)
    actions: dict[str, ActionState] = field(default_factory=dict)
    status: str = "RUNNING"  # RUNNING | COMPLETED
    recoveries: int = 0
    event_count: int = 0

    def in_flight(self) -> list[ActionState]:
        return [a for a in self.actions.values() if a.phase not in TERMINAL_PHASES]

    def step_of(self, action: ActionState) -> StepState:
        return self.steps[action.step_id]


def replay(events: Iterable[Event]) -> TaskState:
    events = iter(events)
    try:
        first = next(events)
    except StopIteration:
        raise JournalIntegrityError("no events for task") from None
    if first.type != E.TASK_CREATED:
        raise JournalIntegrityError(f"first event must be TASK_CREATED, got {first.type}")
    p = first.payload
    state = TaskState(first.task_id, tuple(p["granted_kinds"]),
                      {s["step_id"]: StepState(s["step_id"], s) for s in p["steps"]})
    state.event_count = 1
    return advance(state, events)


def advance(state: TaskState, events: Iterable[Event]) -> TaskState:
    """Fold events onto an already-materialized `TaskState`, in place.

    `events` must be exactly the suffix of the task's journal strictly after
    whatever was last folded into `state` -- never a `TASK_CREATED`, which
    only appears once and is consumed by `replay()`. This lets a caller that
    keeps a `TaskState` cache (see `Controller.state`) apply only the events
    it hasn't seen yet instead of re-replaying a task's entire history on
    every call; skipping, reordering, or duplicating events here would
    silently desync the cache from the journal, so callers must source
    `events` from `Journal.events_since(task_id, <state's last-applied seq>)`.
    """
    for ev in events:
        _apply(state, ev)
        state.event_count += 1
    return state


def _apply(s: TaskState, ev: Event) -> None:
    t, p = ev.type, ev.payload
    if t == E.TASK_CREATED:
        raise JournalIntegrityError("duplicate TASK_CREATED")
    if t in (E.OBSERVED, E.TARGET_RESOLVED, E.TARGET_REJECTED, E.POLICY_ALLOWED, E.POLICY_BLOCKED,
             E.STATE_RECONSTRUCTED):
        return  # diagnostic: carried in the journal for audit/display, not state-bearing
    if t == E.RECOVERY_STARTED:
        s.recoveries += 1
        return
    if t == E.TASK_COMPLETED:
        if any(st.status != "COMPLETED" for st in s.steps.values()):
            raise JournalIntegrityError("TASK_COMPLETED with incomplete steps")
        s.status = "COMPLETED"
        return
    if t == E.ACTION_INTENT_PERSISTED:
        step = s.steps.get(ev.step_id or "")
        if step is None or step.status != "PENDING" or ev.action_id in s.actions:
            raise JournalIntegrityError(f"illegal intent {ev.action_id} for step {ev.step_id}")
        if any(s.actions[a].phase not in TERMINAL_PHASES for a in step.action_ids):
            raise JournalIntegrityError(f"second live intent for step {ev.step_id}")
        s.actions[ev.action_id] = ActionState(
            ev.action_id, ev.step_id, p["kind"], p["args"], EffectClass(p["effect_class"]), p["target_spec"])
        step.action_ids.append(ev.action_id)
        s.actions[ev.action_id].history.append(t.value)
        return
    if t in (E.STEP_COMPLETED, E.STEP_BLOCKED):
        step = s.steps.get(ev.step_id or "")
        if step is None or step.status != "PENDING":
            raise JournalIntegrityError(f"{t.value} for non-pending step {ev.step_id}")
        if t == E.STEP_COMPLETED:
            ok = [a for a in step.action_ids if s.actions[a].phase == Phase.COMMITTED
                  and s.actions[a].outcome == VerificationOutcome.VERIFIED_SUCCESS.value]
            if not ok:
                raise JournalIntegrityError(f"STEP_COMPLETED without verified committed action: {ev.step_id}")
            step.status = "COMPLETED"
        else:
            step.status, step.reason = "BLOCKED", p.get("reason", "")
        return

    a = s.actions.get(ev.action_id or "")
    if a is None:
        raise JournalIntegrityError(f"{t.value} for unknown action {ev.action_id}")
    if a.phase not in _ALLOWED_FROM[t]:
        raise JournalIntegrityError(f"{t.value} illegal from phase {a.phase} ({a.action_id})")
    a.history.append(t.value)
    if t in (E.FRESHNESS_PASSED, E.FRESHNESS_FAILED):
        return
    if t == E.ACTION_ABANDONED:
        a.phase = Phase.ABANDONED
    elif t == E.DISPATCH_STARTED:
        a.phase, a.before, a.observations, a.outcome = Phase.DISPATCH_STARTED, p["before"], [], None
        a.dispatches += 1
        if p["dispatch"] != a.dispatches:
            raise JournalIntegrityError(f"dispatch number mismatch for {a.action_id}")
    elif t == E.DISPATCH_RETURNED:
        a.phase = Phase.DISPATCH_RETURNED
    elif t == E.OBSERVED_AFTER:
        a.phase, a.observations = Phase.OBSERVED_AFTER, p["observations"]
    elif t == E.VERIFICATION_RECORDED:
        a.phase, a.outcome = Phase.VERIFIED, p["outcome"]
    elif t == E.OUTCOME_RECONCILED:
        if a.outcome != VerificationOutcome.VERIFIED_SUCCESS.value:
            raise JournalIntegrityError("reconciled without verified success")
        a.reconciled = True
    elif t == E.ACTION_COMMITTED:
        if a.outcome != VerificationOutcome.VERIFIED_SUCCESS.value:
            raise JournalIntegrityError(f"commit without VERIFIED_SUCCESS ({a.outcome})")
        a.phase = Phase.COMMITTED
    elif t == E.ACTION_FAILED:
        if a.outcome == VerificationOutcome.VERIFIED_SUCCESS.value:
            raise JournalIntegrityError("ACTION_FAILED after VERIFIED_SUCCESS")
        a.phase = Phase.RETRY_PENDING
    elif t == E.OUTCOME_UNKNOWN:
        a.phase = Phase.OUTCOME_UNKNOWN
    elif t == E.NEEDS_REVIEW:
        a.phase = Phase.NEEDS_REVIEW
        step = s.step_of(a)
        step.status, step.reason = "NEEDS_REVIEW", p.get("reason", "")
