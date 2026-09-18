"""Fixture C: a crashable external world for falsifying M3 recovery
(docs/IMPLEMENTATION_PLAN.md M3, docs/BUILD_SPEC.md "Gate M3").

The world lives in its own JSON file, written atomically (temp + fsync +
os.replace) on every mutation, so it survives controller death -- including
a real SIGKILL of the controller process. A `WorldClient` is one controller
session's view of it: UI observations (M1 `Observation`s with session-local
opaque handles), independent state observations (M2 evidence) and dispatch.

Effect classes (docs/DECISIONS.md D-020), one UI button each:
- A `place_order`   -- service dedups on the idempotency key (= action_id).
- B `record_payment` -- non-idempotent append, but each payment carries the
                        action_id reference and can be queried later.
- C `set_theme`     -- naturally idempotent state-set.
- D `send_notification` -- non-idempotent; the only evidence is a toast
                        visible to the *dispatching session* -- gone after a
                        restart, so the outcome cannot be reconciled.

`_truth` (never exposed by `observe_*`) is the grading oracle's ledger:
real effect applications and dispatch calls per action_id, stale/wrong-
target dispatches, and dispatches that repeated an already-applied effect.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import uuid
from pathlib import Path
from typing import Any, Callable

from computer_agent.types import EffectClass, ExecutionRef, Observation, ObservationVersion, TargetCandidate
from computer_agent.verification import (
    UNAVAILABLE,
    Count,
    CountDelta,
    Eq,
    Exists,
    Unchanged,
    UnchangedExcept,
    VerificationSpec,
)

KIND_CLASS = {
    "place_order": EffectClass.IDEMPOTENCY_KEY,
    "record_payment": EffectClass.QUERYABLE,
    "set_theme": EffectClass.STATE_SET,
    "send_notification": EffectClass.NON_IDEMPOTENT_UNQUERYABLE,
}
CLASS_KIND = {c: k for k, c in KIND_CLASS.items()}
LABELS = {"place_order": "Place order", "record_payment": "Record payment",
          "set_theme": "Set theme", "send_notification": "Send notification"}
WORLD_BOUNDARIES = ("during_dispatch_before_effect", "after_effect_before_return")
CRASH_BOUNDARIES = (
    "before_intent_persist", "after_intent_persist", "after_freshness_before_dispatch_started",
    "after_dispatch_started", "during_dispatch_before_effect", "after_effect_before_return",
    "after_dispatch_returned", "after_observation_before_persist", "after_observation_persisted",
    "after_verification_persisted", "after_commit_before_step_complete", "after_step_complete",
)


class SimulatedCrash(BaseException):
    """In-process controller death. BaseException so no `except Exception` can swallow it."""


class StaleDispatch(Exception):
    pass


# -- world file ---------------------------------------------------------------------


def new_world(path: Path, rng: random.Random) -> None:
    ui = []
    for n, kind in enumerate(KIND_CLASS, start=1):
        ui.append({"true_id": f"btn-{n}", "role": "button", "name": LABELS[kind], "kind": kind,
                   "container": "toolbar", "enabled": True, "visible": True})
    rng.shuffle(ui)
    _write(path, {
        "ui": ui, "ui_version": 1, "next_true_id": 100,
        "orders": {}, "payments": [], "settings": {"theme": "light", "density": "normal"},
        "toast": None,
        "_hidden_notifications": 0,
        "_truth": {"effects": {}, "dispatch_calls": {}, "repeat_after_applied": {},
                   "stale_dispatches": 0, "wrong_target_dispatches": 0, "log": []},
    })


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as fh:
        json.dump(data, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def spec_for(intent: dict) -> VerificationSpec:
    """The declared VerificationSpec per action kind (the 'skill' side)."""
    aid, kind, args = intent["action_id"], intent["kind"], intent["args"]
    if kind == "place_order":
        return VerificationSpec(
            success=(Exists(("orders", aid)), Eq(("orders", aid, "item"), args["item"])),
            invariants=(UnchangedExcept(("orders",), frozenset({aid})), Unchanged(("payments",)),
                        Unchanged(("settings",))))
    if kind == "record_payment":
        return VerificationSpec(
            success=(Count(("payments",), 1, 1, where={"ref": aid, "amount": args["amount"]}),),
            invariants=(Count(("payments",), 0, 1, where={"ref": aid}), CountDelta(("payments",), 0, 1),
                        Unchanged(("orders",)), Unchanged(("settings",))))
    if kind == "set_theme":
        return VerificationSpec(
            success=(Eq(("settings", "theme"), args["theme"]),),
            invariants=(UnchangedExcept(("settings",), frozenset({"theme"})), Unchanged(("orders",)),
                        Unchanged(("payments",))))
    return VerificationSpec(
        success=(Eq(("toast", "ref"), aid), Eq(("toast", "text"), args["text"])),
        invariants=(Unchanged(("orders",)), Unchanged(("payments",)), Unchanged(("settings",))))


class WorldClient:
    """One controller session's port into the world (implements controller.WorldPort)."""

    def __init__(self, path: Path, *, crash: Callable[[str], None] = lambda b: None,
                 fault: str = "honest", ui_mutation: tuple[str, int, str] | None = None) -> None:
        self.path = Path(path)
        self.session = uuid.uuid4().hex  # a restarted controller is a new session
        self.crash = crash
        self.fault = fault  # honest | lie_noop | fail_but_applied | collateral | blind_after_dispatch (applies to this session's first dispatch)
        self.ui_mutation = ui_mutation  # (mutation, on the Nth observe_ui call, target kind)
        self._ui_calls = 0
        self._handles = itertools.count(1)
        self._handle_map: dict[tuple[int, str], str] = {}
        self._dispatched = 0
        self._blind = 0  # remaining observe_state calls that return UNAVAILABLE

    def observe_ui(self) -> Observation:
        self._ui_calls += 1
        if self.ui_mutation and self._ui_calls == self.ui_mutation[1]:
            mutate_ui(self.path, self.ui_mutation[0], self.ui_mutation[2])
        w = load(self.path)
        version = ObservationVersion(w["ui_version"])
        cands = []
        for el in w["ui"]:
            h = f"h-{next(self._handles)}"
            self._handle_map[(version.sequence, h)] = el["true_id"]
            cands.append(TargetCandidate(
                execution_ref=ExecutionRef(version, h), role=el["role"], name=el["name"], text=el["name"],
                states={"enabled": el["enabled"], "visible": el["visible"]}, container=el["container"],
                provenance={"source": "fixture_c"}))
        return Observation(version, tuple(cands))

    def observe_state(self) -> Any:
        if self._blind:
            self._blind -= 1
            return UNAVAILABLE
        w = load(self.path)
        toast = w["toast"] if w["toast"] and w["toast"]["session"] == self.session else None
        return {"orders": w["orders"], "payments": w["payments"], "settings": w["settings"],
                "toast": {"ref": toast["ref"], "text": toast["text"]} if toast else None}

    def dispatch(self, ref: ExecutionRef, intent: dict) -> dict:
        w = load(self.path)
        truth = w["_truth"]
        aid, kind = intent["action_id"], intent["kind"]
        truth["dispatch_calls"][aid] = truth["dispatch_calls"].get(aid, 0) + 1
        if ref.observation_version.sequence != w["ui_version"]:
            truth["stale_dispatches"] += 1
            _write(self.path, w)
            raise StaleDispatch(f"ref from v{ref.observation_version.sequence}, UI is v{w['ui_version']}")
        true_id = self._handle_map.get((ref.observation_version.sequence, ref.adapter_local_id))
        element = next((e for e in w["ui"] if e["true_id"] == true_id), None)
        if element is None or element["kind"] != kind:
            truth["wrong_target_dispatches"] += 1
            _write(self.path, w)
            return {"ok": True, "message": "clicked"}  # a wrong click still "succeeds"
        _write(self.path, w)
        self.crash("during_dispatch_before_effect")

        self._dispatched += 1
        fault = self.fault if self._dispatched == 1 else "honest"
        if fault != "lie_noop":
            _apply_effect(self.path, intent, self.session)
        if fault == "blind_after_dispatch":  # effect applied, evidence channel then goes dark
            self._blind = 4
        if fault == "collateral":  # prohibited extra mutation alongside the intended one
            w = load(self.path)
            w["settings"]["density"] = "compact"
            _write(self.path, w)
        self.crash("after_effect_before_return")
        if fault == "fail_but_applied":
            return {"ok": False, "message": "error: timeout"}
        return {"ok": True, "message": "ok"}


def _apply_effect(path: Path, intent: dict, session: str) -> None:
    w = load(path)
    truth = w["_truth"]
    aid, kind, args = intent["action_id"], intent["kind"], intent["args"]
    already = truth["effects"].get(aid, 0) > 0
    if already:
        truth["repeat_after_applied"][aid] = truth["repeat_after_applied"].get(aid, 0) + 1
    applied = True
    if kind == "place_order":
        if aid in w["orders"]:
            applied = False  # idempotency key: the service dedups
        else:
            w["orders"][aid] = {"item": args["item"]}
    elif kind == "record_payment":
        w["payments"].append({"ref": aid, "amount": args["amount"]})
    elif kind == "set_theme":
        w["settings"]["theme"] = args["theme"]
    elif kind == "send_notification":
        w["_hidden_notifications"] += 1
        w["toast"] = {"session": session, "ref": aid, "text": args["text"]}
    if applied:
        truth["effects"][aid] = truth["effects"].get(aid, 0) + 1
    truth["log"].append([aid, kind, applied])
    _write(path, w)


def mutate_ui(path: Path, mutation: str, kind: str) -> None:
    """UI mutations for combined M1->M3 scenarios. Every mutation bumps ui_version."""
    w = load(path)
    target = next(e for e in w["ui"] if e["kind"] == kind)
    if mutation == "replace_same_semantics":
        w["ui"][w["ui"].index(target)] = {**target, "true_id": f"btn-{w['next_true_id']}"}
        w["next_true_id"] += 1
    elif mutation == "duplicate_overlay":
        w["ui"].append({**target, "true_id": f"btn-{w['next_true_id']}", "kind": "decoy"})
        w["next_true_id"] += 1
    elif mutation == "disable":
        target["enabled"] = False
    elif mutation == "remove":
        w["ui"].remove(target)
    else:  # pragma: no cover
        raise ValueError(mutation)
    w["ui_version"] += 1
    _write(path, w)


def make_steps(classes: list[EffectClass], rng: random.Random) -> list[dict]:
    steps = []
    for n, c in enumerate(classes, start=1):
        kind = CLASS_KIND[c]
        args = {"place_order": {"item": rng.choice(["book", "lamp", "mug"])},
                "record_payment": {"amount": rng.randint(5, 500)},
                "set_theme": {"theme": rng.choice(["dark", "solarized", "contrast"])},
                "send_notification": {"text": f"shipment {rng.randint(1000, 9999)} ready"}}[kind]
        steps.append({"step_id": f"s{n}", "kind": kind, "args": args, "effect_class": c.value,
                      "target_spec": {"role": "button", "name": LABELS[kind],
                                      "state_constraints": {"enabled": True, "visible": True}}})
    return steps


# Combined M1 -> M2 -> M3 scenarios: name -> trial overrides (see m3_campaign.run_combined).
A_, B_, C_, D_ = EffectClass
COMBINED: dict[str, dict] = {
    "stale_target_before_dispatch": dict(cls=A_, ui_mutation=("disable", 2)),
    "target_replaced_same_semantics": dict(cls=B_, ui_mutation=("replace_same_semantics", 2)),
    "duplicate_target_after_reobservation": dict(cls=C_, ui_mutation=("duplicate_overlay", 2)),
    "target_removed_before_dispatch": dict(cls=D_, ui_mutation=("remove", 2)),
    "executor_lies_noop_class_a": dict(cls=A_, fault="lie_noop"),
    "executor_lies_noop_class_d": dict(cls=D_, fault="lie_noop"),
    "executor_reports_failure_but_applied": dict(cls=B_, fault="fail_but_applied"),
    "collateral_side_effect": dict(cls=C_, fault="collateral"),
    "evidence_unavailable_class_a_key_retry": dict(cls=A_, fault="blind_after_dispatch"),
    "evidence_unavailable_class_b": dict(cls=B_, fault="blind_after_dispatch"),
    "effect_then_crash_before_persist_class_b": dict(cls=B_, boundary="after_effect_before_return"),
    "effect_then_crash_before_persist_class_a": dict(cls=A_, boundary="after_dispatch_returned"),
    "class_d_ambiguous_crash": dict(cls=D_, boundary="after_effect_before_return"),
    "class_d_crash_after_observation_persisted": dict(cls=D_, boundary="after_observation_persisted"),
    "verified_success_then_restart": dict(cls=D_, boundary="after_step_complete"),
    "lie_then_crash_mid_retry": dict(cls=A_, fault="lie_noop", boundary="after_dispatch_returned"),
    "stale_target_then_crash_after_intent": dict(cls=B_, boundary="after_intent_persist",
                                                 ui_mutation=("replace_same_semantics", 2)),
    "policy_blocked_kind": dict(cls=C_, granted_exclude=True),
    "happy_path_no_crash": dict(cls=B_),
}
COMBINED_SCENARIOS = tuple(COMBINED)
