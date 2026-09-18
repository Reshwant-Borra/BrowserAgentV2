"""Durable deterministic controller: the consequential-action lifecycle (M3).

See `docs/IMPLEMENTATION_PLAN.md` M3, `docs/DECISIONS.md` D-019/D-020/D-022.
One controller owns the lifecycle; M1 grounding and M2 verification are
used as-is:

    read durable state -> fresh observation -> resolve TargetSpec
      -> reject ambiguity/absence -> policy gate (M3 placeholder: granted kinds)
      -> persist ACTION_INTENT -> fresh observation + pre-dispatch freshness
      -> persist DISPATCH_STARTED (with independently observed before-state)
      -> dispatch -> independently observe -> persist OBSERVED_AFTER
      -> verify -> persist VERIFICATION_RECORDED -> commit -> advance step

The executor's return value is journaled as DISPATCH_RETURNED for audit and
is never an input to verification or advancement. `run()` always starts by
rebuilding state from the journal, so a fresh controller in a new process
after a crash continues from durable truth only.

`crash` is a fault-injection hook called with a boundary name at every
durable boundary (default: no-op). Tests use it to kill the process.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from . import recovery
from .grounding import freshness_check, resolve
from .journal import EventType as E, Journal
from .recovery import Next
from .state import ActionState, Phase, TaskState, replay
from .types import ExecutionRef, Observation, ResolutionOutcome, TargetSpec
from .verification import VerificationOutcome, VerificationSpec, judge, verify

BOUNDARIES = (
    "before_intent_persist",
    "after_intent_persist",
    "after_freshness_before_dispatch_started",
    "after_dispatch_started",
    "after_dispatch_returned",
    "after_observation_before_persist",
    "after_observation_persisted",
    "after_verification_persisted",
    "after_commit_before_step_complete",
    "after_step_complete",
)


class WorldPort(Protocol):
    """What the controller needs from an adapter. Observation and dispatch are separate channels."""

    def observe_ui(self) -> Observation: ...
    def observe_state(self) -> Any: ...
    def dispatch(self, ref: ExecutionRef, intent: dict[str, Any]) -> dict[str, Any]: ...


def _spec(d: dict[str, Any]) -> TargetSpec:
    return TargetSpec(**d)


class Controller:
    def __init__(
        self,
        journal: Journal,
        port: WorldPort,
        spec_for: Callable[[dict[str, Any]], VerificationSpec],
        *,
        crash: Callable[[str], None] = lambda boundary: None,
        max_observations: int = 4,
    ) -> None:
        self.j, self.port, self.spec_for, self.crash = journal, port, spec_for, crash
        self.max_observations = max_observations

    # -- journal helpers ------------------------------------------------------------

    def _diag(self, task_id: str, t: E, payload: dict | None = None, **ids: Any) -> None:
        self.j.append(task_id, t, f"{task_id}/{t.value}/{self.j.next_seq()}", payload, **ids)

    def _act(self, task_id: str, a: ActionState, t: E, payload: dict | None = None, *, n: int | None = None) -> None:
        n = a.dispatches if n is None else n
        self.j.append(task_id, t, f"{a.action_id}/{n}/{t.value}", payload, step_id=a.step_id, action_id=a.action_id)

    def state(self, task_id: str) -> TaskState:
        return replay(self.j.events(task_id))

    # -- public API -----------------------------------------------------------------

    def create_task(self, task_id: str, steps: list[dict[str, Any]], granted_kinds: list[str]) -> None:
        self.j.append(task_id, E.TASK_CREATED, f"{task_id}/TASK_CREATED",
                      {"steps": steps, "granted_kinds": granted_kinds})

    def run(self, task_id: str) -> TaskState:
        s = self.state(task_id)
        if s.status == "COMPLETED":
            return s
        if s.event_count > 1:  # a previous controller instance got this far: this is a restart
            self._diag(task_id, E.RECOVERY_STARTED)
            self._diag(task_id, E.STATE_RECONSTRUCTED, {
                "events_replayed": s.event_count,
                "steps": {k: v.status for k, v in s.steps.items()},
                "in_flight": {a.action_id: a.phase for a in s.in_flight()},
            })
        for step_id in list(s.steps):
            s = self.state(task_id)
            step = s.steps[step_id]
            if step.status == "PENDING":
                self._drive_step(task_id, step_id)
                step = self.state(task_id).steps[step_id]
            if step.status != "COMPLETED":
                return self.state(task_id)  # blocked / needs review: halt, never skip ahead
        self.j.append(task_id, E.TASK_COMPLETED, f"{task_id}/TASK_COMPLETED")
        return self.state(task_id)

    # -- lifecycle ------------------------------------------------------------------

    def _drive_step(self, task_id: str, step_id: str) -> None:
        s = self.state(task_id)
        step = s.steps[step_id]
        live = [s.actions[a] for a in step.action_ids if s.actions[a].phase != Phase.NEEDS_REVIEW]
        if live:
            return self._recover(task_id, live[-1])
        plan = step.plan
        target = _spec(plan["target_spec"])

        obs = self.port.observe_ui()
        self._diag(task_id, E.OBSERVED, {"version": obs.version.sequence, "candidates": len(obs.candidates)},
                   step_id=step_id)
        res = resolve(target, obs)
        if res.outcome != ResolutionOutcome.RESOLVED:
            self._diag(task_id, E.TARGET_REJECTED, {"outcome": res.outcome.value, "reason": res.reason},
                       step_id=step_id)
            return self._block(task_id, step_id, f"target {res.outcome.value}: {res.reason}")
        self._diag(task_id, E.TARGET_RESOLVED, {"version": obs.version.sequence}, step_id=step_id)

        if plan["kind"] not in s.granted_kinds:  # M3 placeholder for the M5 policy engine
            self._diag(task_id, E.POLICY_BLOCKED, {"kind": plan["kind"]}, step_id=step_id)
            return self._block(task_id, step_id, f"policy: {plan['kind']} not granted")
        self._diag(task_id, E.POLICY_ALLOWED, {"kind": plan["kind"]}, step_id=step_id)

        action_id = f"{step_id}.a{len(step.action_ids) + 1}"
        self.crash("before_intent_persist")
        self.j.append(task_id, E.ACTION_INTENT_PERSISTED, f"{action_id}/0/{E.ACTION_INTENT_PERSISTED.value}", {
            "kind": plan["kind"], "args": plan["args"], "effect_class": plan["effect_class"],
            "target_spec": plan["target_spec"]}, step_id=step_id, action_id=action_id)
        self.crash("after_intent_persist")
        self._attempt(task_id, action_id, res.selected.execution_ref)

    def _attempt(self, task_id: str, action_id: str, ref: ExecutionRef | None = None) -> None:
        """One dispatch of a logical action whose intent is durable and which is not in flight."""
        a = self.state(task_id).actions[action_id]
        target = _spec(a.target_spec)
        if ref is None:  # refs are never durable: re-ground from the persisted TargetSpec
            obs = self.port.observe_ui()
            self._diag(task_id, E.OBSERVED, {"version": obs.version.sequence, "candidates": len(obs.candidates)},
                       step_id=a.step_id, action_id=action_id)
            res = resolve(target, obs)
            if res.outcome != ResolutionOutcome.RESOLVED:
                return self._abandon(task_id, a, f"re-grounding {res.outcome.value}: {res.reason}")
            ref = res.selected.execution_ref

        fresh = freshness_check(ref, target, self.port.observe_ui())
        if not fresh.safe_to_dispatch:
            self._diag(task_id, E.FRESHNESS_FAILED, {"outcome": fresh.outcome.value, "reason": fresh.reason},
                       step_id=a.step_id, action_id=action_id)
            return self._abandon(task_id, a, f"freshness {fresh.outcome.value}: {fresh.reason}")
        self._diag(task_id, E.FRESHNESS_PASSED, {"reason": fresh.reason}, step_id=a.step_id, action_id=action_id)
        self.crash("after_freshness_before_dispatch_started")

        intent = {"action_id": action_id, "kind": a.kind, "args": a.args}
        before = self.port.observe_state()
        n = a.dispatches + 1
        self._act(task_id, a, E.DISPATCH_STARTED, {"dispatch": n, "before": before}, n=n)
        self.crash("after_dispatch_started")
        try:
            claim = self.port.dispatch(fresh.execution_ref, intent)
        except Exception as exc:  # an adapter error is a claim too -- still not evidence
            claim = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        self._act(task_id, a, E.DISPATCH_RETURNED, {"claim": claim}, n=n)
        self.crash("after_dispatch_returned")
        self._verify_and_settle(task_id, action_id, reconciling=False)

    def _verify_and_settle(self, task_id: str, action_id: str, *, reconciling: bool) -> None:
        a = self.state(task_id).actions[action_id]
        result, observations = verify(self.spec_for(self._intent(a)), a.before, self.port.observe_state,
                                      max_observations=self.max_observations)
        self.crash("after_observation_before_persist")
        self._act(task_id, a, E.OBSERVED_AFTER, {"observations": observations, "reconciling": reconciling})
        self.crash("after_observation_persisted")
        self._record_verdict(task_id, action_id, result.outcome, result.reason, reconciling)

    def _record_verdict(self, task_id: str, action_id: str, outcome: VerificationOutcome, reason: str,
                        reconciling: bool) -> None:
        a = self.state(task_id).actions[action_id]
        self._act(task_id, a, E.VERIFICATION_RECORDED, {"outcome": outcome.value, "reason": reason})
        self.crash("after_verification_persisted")
        if reconciling and outcome == VerificationOutcome.VERIFIED_SUCCESS:
            self._act(task_id, a, E.OUTCOME_RECONCILED, {"reason": "effect already present; not repeated"})
        self._settle(task_id, action_id)

    def _settle(self, task_id: str, action_id: str) -> None:
        a = self.state(task_id).actions[action_id]
        nxt = recovery.after_verification(a.effect_class, VerificationOutcome(a.outcome), a.dispatches)
        if nxt == Next.COMMIT:
            self._act(task_id, a, E.ACTION_COMMITTED, {"outcome": a.outcome})
            self.crash("after_commit_before_step_complete")
            self._complete(task_id, a)
        elif nxt == Next.RETRY:
            self._act(task_id, a, E.ACTION_FAILED, {"outcome": a.outcome, "retry": True})
            self._attempt(task_id, action_id)
        else:
            if nxt == Next.OUTCOME_UNKNOWN:
                self._act(task_id, a, E.OUTCOME_UNKNOWN, {"outcome": a.outcome})
            self._review(task_id, action_id, f"verification {a.outcome} for class {a.effect_class.value}")

    # -- restart reconciliation ------------------------------------------------------

    def _recover(self, task_id: str, a: ActionState) -> None:
        nxt = recovery.on_restart(a)
        if nxt == Next.RESUME_DISPATCH:
            self._attempt(task_id, a.action_id)
        elif nxt == Next.RECONCILE:
            self._verify_and_settle(task_id, a.action_id, reconciling=True)
        elif nxt == Next.OUTCOME_UNKNOWN:
            self._act(task_id, a, E.OUTCOME_UNKNOWN, {
                "reason": "dispatch may have happened; class D effect is neither idempotent nor queryable"})
            self._review(task_id, a.action_id, "OUTCOME_UNKNOWN after restart (class D): not retried")
        elif nxt == Next.JUDGE_PERSISTED:
            result = judge(self.spec_for(self._intent(a)), a.before, a.observations)
            self._record_verdict(task_id, a.action_id, result.outcome,
                                 result.reason + " (re-judged from persisted observations)", reconciling=True)
        elif nxt == Next.SETTLE_PERSISTED:
            self._settle(task_id, a.action_id)
        elif nxt == Next.NEEDS_REVIEW:
            self._review(task_id, a.action_id, "outcome unknown")
        elif nxt == Next.COMPLETE_STEP:
            self._complete(task_id, a)
        elif nxt == Next.BLOCK_STEP:
            self._block(task_id, a.step_id, "action abandoned before dispatch")

    # -- terminal transitions ------------------------------------------------------------

    def _complete(self, task_id: str, a: ActionState) -> None:
        self.j.append(task_id, E.STEP_COMPLETED, f"{a.step_id}/STEP_COMPLETED", {"action_id": a.action_id},
                      step_id=a.step_id)
        self.crash("after_step_complete")

    def _review(self, task_id: str, action_id: str, reason: str) -> None:
        a = self.state(task_id).actions[action_id]
        self._act(task_id, a, E.NEEDS_REVIEW, {"reason": reason})

    def _abandon(self, task_id: str, a: ActionState, reason: str) -> None:
        self._diag(task_id, E.ACTION_ABANDONED, {"reason": reason}, step_id=a.step_id, action_id=a.action_id)
        self._block(task_id, a.step_id, reason)

    def _block(self, task_id: str, step_id: str, reason: str) -> None:
        self.j.append(task_id, E.STEP_BLOCKED, f"{step_id}/STEP_BLOCKED", {"reason": reason}, step_id=step_id)

    @staticmethod
    def _intent(a: ActionState) -> dict[str, Any]:
        return {"action_id": a.action_id, "kind": a.kind, "args": a.args}
