"""Developer Console view layer: runs a backend/harness trial and serializes
its already-computed results into display-safe JSON.

This module decides nothing. Every verdict it returns (resolution,
freshness, dispatch safety, verification outcome, recovery state) is a
value some backend or harness function already produced; this code only
copies and renames fields. Opaque `ExecutionRef.adapter_local_id` values
are never emitted -- only the observation version a ref is bound to.

Nothing under `computer_agent/` imports this package (D-025): the backend
is fully testable with the console absent.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from typing import Any

from computer_agent.types import ExecutionRef, TargetSpec, summarize_candidate
from computer_agent.verification import Indeterminate

from tests.computer_agent.campaign import run_trial
from tests.computer_agent.fixtures.scenarios import SCENARIO_NAMES

MAX_CANDIDATES = 25  # bounded display; the backend never truncates its own data


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Indeterminate):
        return f"<indeterminate: {value.reason}>"
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return value


def _spec(spec: TargetSpec) -> dict[str, Any]:
    return _jsonable(asdict(spec))


def _ref(ref: ExecutionRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return {"observation_version": ref.observation_version.sequence, "handle": "<opaque>"}


def _states(states) -> str:
    return " ".join(f"{k}={v}" for k, v in states.items())


def scenarios() -> dict[str, Any]:
    from tests.computer_agent.fixtures.fixture_b import CASE_NAMES

    from tests.computer_agent.fixtures.fixture_c import COMBINED_SCENARIOS, CRASH_BOUNDARIES
    from computer_agent.types import EffectClass

    crash = [f"crash:{c.value}:{b}" for c in EffectClass for b in CRASH_BOUNDARIES]
    return {"m1": list(SCENARIO_NAMES), "m2": list(CASE_NAMES),
            "m3": {"combined": [*COMBINED_SCENARIOS, *crash]}}


def _predicates(results) -> list[dict[str, str]]:
    return [{"predicate": r.predicate, "value": r.value.value, "detail": r.detail} for r in results]


def m2_view(case: str, seed: int) -> dict[str, Any]:
    from tests.computer_agent import m2_campaign
    from tests.computer_agent.fixtures.fixture_b import CASE_NAMES

    if case not in CASE_NAMES:
        raise KeyError(case)
    cap: dict[str, Any] = {}
    t = m2_campaign.run_trial(case, seed, capture=cap)
    result, spec = cap["result"], cap["spec"]
    timeline = [
        {"event": "OBSERVED", "detail": "independent pre-dispatch observation (before state)"},
        {"event": "DISPATCHED", "detail": f"behavior={t.behavior}"},
        {"event": "EXECUTOR_CLAIM", "detail": f"ok={t.executor_claim_ok} {t.executor_claim_message!r} "
                                              "(recorded only; never given to the verifier)"},
    ]
    for i, outcome in enumerate(t.history, start=1):
        timeline.append({"event": "OBSERVED_AFTER", "detail": f"observation {i}: evaluates to {outcome}"})
    timeline.append({"event": t.verdict, "detail": t.reason})
    timeline.append({"event": "GRADED", "source": "harness oracle",
                     "detail": "FALSE_SUCCESS" if t.false_success else
                     f"truly established={t.truly_established}"})
    return {
        "kind": "m2",
        "verdict": {"verification_outcome": t.verdict, "executor_claimed_ok": t.executor_claim_ok,
                    "oracle": "FALSE_SUCCESS" if t.false_success else ("FALSE_FAILURE" if t.false_failure else "correct")},
        "task": {"fixture": "Fixture B (DeceptiveService)", "case": case, "behavior": t.behavior, "seed": seed},
        "action_intent": t.intent,
        "executor_claim": {"ok": t.executor_claim_ok, "message": t.executor_claim_message,
                           "lied": t.executor_lied},
        "before_state": _jsonable(cap["before"]),
        "after_state": _jsonable(cap["observations"][-1]) if cap["observations"] else None,
        "verification_spec": {"success": [repr(p) for p in spec.success],
                              "invariants": [repr(p) for p in spec.invariants]},
        "verification_outcome": {"outcome": t.verdict, "reason": t.reason,
                                 "observations_used": t.observations_used, "history": t.history,
                                 "success_predicates": _predicates(result.success_results)},
        "side_effect_check": _predicates(result.invariant_results),
        "grading": {"truly_established": t.truly_established, "false_success": t.false_success,
                    "false_failure": t.false_failure,
                    "truth_after (oracle only)": _jsonable(cap["truth_final"])},
        "timeline": timeline,
    }


def m1_view(scenario: str, seed: int) -> dict[str, Any]:
    if scenario not in SCENARIO_NAMES:
        raise KeyError(scenario)
    cap: dict[str, Any] = {}
    record = run_trial(scenario, seed, capture=cap)
    obs0, res0, obs1, fresh = cap["observation_0"], cap["resolution_0"], cap["observation_1"], cap["freshness"]

    matched = {id(c) for c in res0.candidates}
    observed = [
        {"role": c.role, "name": c.name, "container": c.container, "states": _states(c.states),
         "matched_spec": id(c) in matched, "selected": c is res0.selected}
        for c in obs0.candidates[:MAX_CANDIDATES]
    ]

    timeline = [
        {"event": "OBSERVED", "detail": f"T0 observation v{obs0.version.sequence}, {len(obs0.candidates)} candidates"},
        {"event": "TARGET_RESOLVED" if record.resolution_outcome_t0 == "RESOLVED" else "TARGET_REJECTED",
         "detail": f"{record.resolution_outcome_t0}: {res0.reason or 'unique match'}"},
        {"event": "MUTATION_APPLIED", "detail": f"scenario mutation ({scenario})", "source": "harness"},
        {"event": "OBSERVED", "detail": f"T1 observation v{obs1.version.sequence}, {len(obs1.candidates)} candidates"},
    ]
    if fresh is not None:
        timeline.append({"event": "FRESHNESS_PASSED" if fresh.safe_to_dispatch else "FRESHNESS_FAILED",
                         "detail": f"{fresh.outcome.value}: {fresh.reason}"})
    timeline.append({"event": "DISPATCHED" if record.dispatched else "ABSTAINED",
                     "detail": record.freshness_reason})
    timeline.append({"event": "GRADED", "detail": record.safety, "source": "harness oracle"})

    return {
        "kind": "m1",
        "verdict": {"dispatch_safety": record.safety, "resolution": res0.outcome.value,
                    "freshness": "FRESHNESS_PASSED" if fresh and fresh.safe_to_dispatch
                    else ("FRESHNESS_FAILED" if fresh else "not run"),
                    "dispatch": "DISPATCHED" if record.dispatched else "ABSTAINED"},
        "task": {"fixture": "Fixture A (MutableUIGraph)", "scenario": scenario, "seed": seed,
                 "expected_t0_outcome": record.expected_t0_outcome},
        "target_spec": _spec(cap["spec"]),
        "observation": {"t0_version": obs0.version.sequence, "t1_version": obs1.version.sequence,
                        "t0_candidate_count": len(obs0.candidates), "t1_candidate_count": len(obs1.candidates)},
        "candidates": {"observed": observed, "truncated": len(obs0.candidates) > MAX_CANDIDATES,
                       "matched_count": len(res0.candidates)},
        "resolution": {"outcome": res0.outcome.value, "reason": res0.reason,
                       "selected": _jsonable(asdict(summarize_candidate(res0.selected))) if res0.selected else None},
        "execution_ref": _ref(res0.selected.execution_ref if res0.selected else None),
        "freshness": None if fresh is None else {
            "safe_to_dispatch": fresh.safe_to_dispatch, "outcome": fresh.outcome.value,
            "reason": fresh.reason, "dispatch_ref": _ref(fresh.execution_ref)},
        "dispatch": {"dispatched": record.dispatched, "stale_ref": record.dispatch_was_stale_ref,
                     "touched_fixture_object": record.dispatch_touched_true_id},
        "grading": {"safety": record.safety, "oracle_expected_t1": record.expected_outcome_t1,
                    "oracle_expected_object": record.expected_true_id_t1,
                    "oracle_agrees_with_resolver": record.oracle_agrees_with_resolver_t1,
                    "identity_shifted": record.identity_shifted},
        "timeline": timeline,
    }


def _payload_summary(payload: dict[str, Any]) -> str:
    out = []
    for k, v in payload.items():
        if k == "before":
            v = "<before-state snapshot>"
        elif k == "observations":
            v = f"<{len(v)} post-action observation(s)>"
        elif k in ("steps", "in_flight"):
            v = json.dumps(_jsonable(v))[:160]
        out.append(f"{k}={_jsonable(v)}")
    return " ".join(out)


def m3_view(scenario: str, seed: int) -> dict[str, Any]:
    from computer_agent.types import EffectClass
    from tests.computer_agent import m3_campaign
    from tests.computer_agent.fixtures.fixture_c import COMBINED

    cap: dict[str, Any] = {}
    if scenario in COMBINED:
        trial = m3_campaign.run_combined(scenario, seed, capture=cap)
    elif scenario.startswith("crash:"):
        _, cls, boundary = scenario.split(":")
        trial = m3_campaign.run_trial(EffectClass(cls), boundary, seed, capture=cap)
    else:
        raise KeyError(scenario)
    events, state, markers = cap["events"], cap["state"], cap["markers"]

    timeline: list[dict[str, Any]] = []
    pending = sorted(markers)
    for ev in events:
        while pending and pending[0][0] < ev.seq:
            _, marker, detail = pending.pop(0)
            timeline.append({"event": marker, "detail": detail, "source": "harness"})
        label = ev.payload.get("outcome") if ev.type.value == "VERIFICATION_RECORDED" else ev.type.value
        where = "/".join(x for x in (ev.step_id, ev.action_id) if x)
        timeline.append({"event": label, "detail": f"#{ev.seq} {where} {_payload_summary(ev.payload)}".strip(),
                         "source": "journal"})
    for _, marker, detail in pending:
        timeline.append({"event": marker, "detail": detail, "source": "harness"})

    def last(action_id: str, type_: str) -> dict | None:
        found = [e.payload for e in events if e.action_id == action_id and e.type.value == type_]
        return found[-1] if found else None

    def step_last(step_id: str, type_: str) -> dict | None:
        found = [e.payload for e in events if e.step_id == step_id and e.type.value == type_]
        return found[-1] if found else None

    lifecycle: dict[str, dict[str, Any]] = {}
    for step in state.steps.values():
        aid = step.action_ids[-1] if step.action_ids else None
        a = state.actions.get(aid) if aid else None
        claim = last(aid, "DISPATCH_RETURNED") if aid else None
        observed_after = last(aid, "OBSERVED_AFTER") if aid else None
        lifecycle[step.step_id] = {
            "action": f"{step.plan['kind']} (class {step.plan['effect_class']})",
            "target": step.plan["target_spec"].get("name"),
            "observation_version": (step_last(step.step_id, "OBSERVED") or {}).get("version"),
            "resolution": "TARGET_RESOLVED" if step_last(step.step_id, "TARGET_RESOLVED") else
                          (step_last(step.step_id, "TARGET_REJECTED") or {}).get("outcome"),
            "freshness": "FRESHNESS_PASSED" if aid and last(aid, "FRESHNESS_PASSED") else
                         ("FRESHNESS_FAILED" if aid and last(aid, "FRESHNESS_FAILED") else None),
            "intent_persisted": aid,
            "dispatches": a.dispatches if a else 0,
            "executor_claim": f"ok={claim['claim']['ok']} {claim['claim']['message']}" if claim else None,
            "post_action_observations": len(observed_after["observations"]) if observed_after else None,
            "verification": a.outcome if a else None,
            "durable_result": a.phase if a else None,
            "recovery": ("OUTCOME_RECONCILED" if a and a.reconciled else
                         "OUTCOME_UNKNOWN" if aid and last(aid, "OUTCOME_UNKNOWN") else None),
            "step_status": step.status,
        }

    world = cap["world"]["_truth"]
    return {
        "kind": "m3",
        "verdict": {"task": trial.final, "oracle_safety_failures": trial.safety_failures,
                    "crashes": trial.crashes or None, "controller_runs": trial.runs,
                    "restarts_journaled": state.recoveries},
        "task": {"fixture": "Fixture C (crashable world) + SQLite WAL journal", "scenario": scenario,
                 "seed": seed, "executor_fault": cap["plan"].fault},
        "lifecycle": lifecycle,
        "oracle": {k: getattr(trial, k) for k in (
            "duplicate_effects", "lost_effects", "incorrect_verified_success", "unsafe_retries",
            "unresolved_auto_advanced", "stale_or_wrong_target_dispatches", "reconstruction_failures")}
        | {"external_effects (hidden ledger)": world["effects"], "dispatch_calls": world["dispatch_calls"]},
        "timeline": timeline,
    }
