"""M3 crash-injection campaign: durable controller + Fixture C, graded by
an independent oracle.

Each trial: a 2-step task whose first step has the effect class under test
(the second step, a different class, checks the plan resumes after
recovery without re-dispatching completed work). The controller is killed
at the first hit of the chosen boundary (always inside step 1 on the
success path), then restarted as a *new* controller (new journal
connection, new world session) up to `MAX_RUNS` times; 25% of trials
inject a second crash at a random boundary during recovery.

Crash modes: in-process (`SimulatedCrash`, a BaseException) for the bulk
campaign, and real `SIGKILL` of a controller subprocess
(`python -m tests.computer_agent.m3_campaign --worker ...`) for the
subprocess subset.

Oracle independence: grading reads Fixture C's hidden `_truth` ledger and
the journal's raw SQLite rows with its own SQL. It never calls
`computer_agent.state`, `recovery` or `verification`.
"""

from __future__ import annotations

import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from computer_agent.controller import Controller
from computer_agent.journal import Journal
from computer_agent.state import replay
from computer_agent.types import EffectClass

from .fixtures.fixture_c import (
    COMBINED,
    CRASH_BOUNDARIES,
    KIND_CLASS,
    SimulatedCrash,
    WorldClient,
    load,
    make_steps,
    new_world,
    spec_for,
)

ROOT = Path(__file__).resolve().parents[2]
TASK = "task-1"
MAX_RUNS = 4
CLASSES = tuple(EffectClass)


@dataclass
class TrialPlan:
    effect_class: EffectClass
    boundary: str
    seed: int
    steps: list[dict]
    fault: str
    second_boundary: str | None


def plan_trial(effect_class: EffectClass, boundary: str, seed: int) -> TrialPlan:
    rng = random.Random(seed)
    other = rng.choice([c for c in CLASSES if c != effect_class])
    steps = make_steps([effect_class, other], rng)
    fault = rng.choices(["honest", "lie_noop", "fail_but_applied", "blind_after_dispatch"],
                        [0.6, 0.15, 0.15, 0.1])[0]
    second = rng.choice(CRASH_BOUNDARIES) if rng.random() < 0.25 else None
    return TrialPlan(effect_class, boundary, seed, steps, fault, second)


def _crasher(boundary: str | None, kill: bool):
    fired = {"n": 0}

    def crash(b: str) -> None:
        if b == boundary and not fired["n"]:
            fired["n"] += 1
            if kill:
                os.kill(os.getpid(), signal.SIGKILL)
            raise SimulatedCrash(b)

    crash.fired = fired  # type: ignore[attr-defined]
    return crash


def controller_session(workdir: Path, plan: TrialPlan, run_index: int, *, kill: bool = False,
                       ui_mutation=None, granted=None) -> tuple[bool, str | None]:
    """One controller process lifetime. Returns (crashed, boundary)."""
    boundary = plan.boundary if run_index == 0 else (plan.second_boundary if run_index == 1 else None)
    crash = _crasher(boundary, kill)
    journal = Journal(workdir / "journal.db")
    world = WorldClient(workdir / "world.json", crash=crash, fault=plan.fault if run_index == 0 else "honest",
                        ui_mutation=ui_mutation if run_index == 0 else None)
    ctrl = Controller(journal, world, spec_for, crash=crash)
    try:
        if run_index == 0:
            ctrl.create_task(TASK, plan.steps, granted or list(KIND_CLASS))
        ctrl.run(TASK)
        return False, None
    except SimulatedCrash as c:
        return True, str(c)
    finally:
        journal.close()


# -- oracle ----------------------------------------------------------------------------


def _raw_events(db: Path) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("SELECT seq, type, step_id, action_id, payload FROM events ORDER BY seq").fetchall()
    finally:
        con.close()


@dataclass
class M3Trial:
    effect_class: str
    boundary: str
    seed: int
    mode: str
    fault: str
    second_boundary: str | None
    crashes: list[str]
    runs: int
    final: str  # COMPLETED | BLOCKED | NEEDS_REVIEW | STUCK
    step_status: dict[str, str]
    duplicate_effects: int = 0
    lost_effects: int = 0
    incorrect_verified_success: int = 0
    unsafe_retries: int = 0
    unresolved_auto_advanced: int = 0
    dispatch_without_durable_start: int = 0
    stale_or_wrong_target_dispatches: int = 0
    reconstruction_failures: int = 0
    action_id_instability: int = 0
    reconciled: int = 0
    needs_review: int = 0
    outcome_unknown: int = 0
    safe_key_retries: int = 0
    idempotent_reapplies: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def safety_failures(self) -> int:
        return (self.duplicate_effects + self.lost_effects + self.incorrect_verified_success + self.unsafe_retries
                + self.unresolved_auto_advanced + self.dispatch_without_durable_start
                + self.stale_or_wrong_target_dispatches + self.reconstruction_failures + self.action_id_instability)


def grade(workdir: Path, plan: TrialPlan, crashes: list[str], runs: int, mode: str) -> M3Trial:
    world = load(workdir / "world.json")
    truth = world["_truth"]
    rows = _raw_events(workdir / "journal.db")
    types_by_action: dict[str, list[tuple[str, dict]]] = {}
    step_events: dict[str, list[str]] = {}
    intents: dict[str, list[str]] = {}
    for _, typ, step, action, payload in rows:
        p = json.loads(payload)
        if action:
            types_by_action.setdefault(action, []).append((typ, p))
        if step and typ in ("STEP_COMPLETED", "STEP_BLOCKED"):
            step_events.setdefault(step, []).append(typ)
        if typ == "ACTION_INTENT_PERSISTED":
            intents.setdefault(step, []).append(action)
    all_types = [r[1] for r in rows]

    t = M3Trial(plan.effect_class.value, plan.boundary, plan.seed, mode, plan.fault, plan.second_boundary,
                crashes, runs, "STUCK", {})
    for step in plan.steps:
        sid, kind, cls = step["step_id"], step["kind"], EffectClass(step["effect_class"])
        aids = intents.get(sid, [])
        if len(aids) > 1:
            t.action_id_instability += 1
            t.notes.append(f"{sid}: {len(aids)} logical actions")
        effects = sum(truth["effects"].get(a, 0) for a in aids)
        events = [e for a in aids for e in types_by_action.get(a, [])]
        etypes = [e[0] for e in events]
        verified_ok = any(ty == "VERIFICATION_RECORDED" and p["outcome"] == "VERIFIED_SUCCESS" for ty, p in events)
        completed = "STEP_COMPLETED" in step_events.get(sid, [])
        reviewed = "NEEDS_REVIEW" in etypes
        blocked = "STEP_BLOCKED" in step_events.get(sid, [])
        t.step_status[sid] = "COMPLETED" if completed else "NEEDS_REVIEW" if reviewed else \
            "BLOCKED" if blocked else "PENDING"

        if kind == "place_order":
            established = any(a in world["orders"] and world["orders"][a]["item"] == step["args"]["item"] for a in aids)
        elif kind == "record_payment":
            established = sum(1 for p in world["payments"] if p["ref"] in aids
                              and p["amount"] == step["args"]["amount"]) == 1
        elif kind == "set_theme":
            established = world["settings"]["theme"] == step["args"]["theme"]
        else:
            established = effects == 1

        if cls != EffectClass.STATE_SET and effects > 1:
            t.duplicate_effects += 1
            t.notes.append(f"{sid}: {effects} external effects")
        if verified_ok and not established:
            t.incorrect_verified_success += 1
        if completed and not verified_ok:
            t.unresolved_auto_advanced += 1
        if effects > 0 and not completed and not reviewed:
            t.lost_effects += 1
            t.notes.append(f"{sid}: effect happened but step is {t.step_status[sid]} without review")
        for a in aids:
            calls = truth["dispatch_calls"].get(a, 0)
            started = sum(1 for ty, _ in types_by_action.get(a, []) if ty == "DISPATCH_STARTED")
            if calls > started:
                t.dispatch_without_durable_start += 1
            repeats = truth["repeat_after_applied"].get(a, 0)
            if cls == EffectClass.NON_IDEMPOTENT_UNQUERYABLE and calls > 1:
                t.unsafe_retries += 1
                t.notes.append(f"{a}: class D dispatched {calls}x")
            elif cls == EffectClass.QUERYABLE and repeats:
                t.unsafe_retries += 1
            elif cls == EffectClass.IDEMPOTENCY_KEY:
                t.safe_key_retries += repeats
            elif cls == EffectClass.STATE_SET:
                t.idempotent_reapplies += repeats
        t.reconciled += etypes.count("OUTCOME_RECONCILED")
        t.needs_review += etypes.count("NEEDS_REVIEW")
        t.outcome_unknown += etypes.count("OUTCOME_UNKNOWN")

    t.stale_or_wrong_target_dispatches = truth["stale_dispatches"] + truth["wrong_target_dispatches"]
    statuses = list(t.step_status.values())
    if "TASK_COMPLETED" in all_types:
        t.final = "COMPLETED"
    elif "NEEDS_REVIEW" in statuses:
        t.final = "NEEDS_REVIEW"
    elif "BLOCKED" in statuses:
        t.final = "BLOCKED"
    if t.final == "STUCK":
        t.notes.append("task neither completed nor explicitly halted")
        t.reconstruction_failures += 1

    # Durable reconstruction: two independent replays from fresh connections must agree,
    # and must agree with the oracle's own reading of step status.
    j1, j2 = Journal(workdir / "journal.db"), Journal(workdir / "journal.db")
    try:
        s1, s2 = replay(j1.events(TASK)), replay(j2.events(TASK))
    except Exception as exc:  # integrity failure is a reconstruction failure
        t.reconstruction_failures += 1
        t.notes.append(f"replay failed: {exc}")
    else:
        # Compare canonical form: persisted Indeterminate evidence is (by design) never ==
        # to anything, so object equality would report identical replays as different.
        if repr(s1) != repr(s2) or {k: v.status for k, v in s1.steps.items()} != t.step_status:
            t.reconstruction_failures += 1
            t.notes.append(f"replay mismatch: {({k: v.status for k, v in s1.steps.items()})} vs {t.step_status}")
    finally:
        j1.close()
        j2.close()
    return t


# -- trial drivers ---------------------------------------------------------------------


def run_trial(effect_class: EffectClass, boundary: str | None, seed: int, *, plan: TrialPlan | None = None,
              capture: dict | None = None, **session_kw) -> M3Trial:
    plan = plan or plan_trial(effect_class, boundary, seed)
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        new_world(wd / "world.json", random.Random(seed))
        crashes: list[str] = []
        markers: list[tuple[int, str, str]] = []  # (after journal seq, marker, detail) for display
        runs = 0
        for runs in range(1, MAX_RUNS + 1):
            if runs > 1:
                markers.append((_last_seq(wd), "RESTART", f"controller run {runs}: new process/session"))
            crashed, where = controller_session(wd, plan, runs - 1, **session_kw)
            if not crashed:
                break
            crashes.append(where)
            markers.append((_last_seq(wd), "CRASH", f"controller killed at {where}"))
        trial = grade(wd, plan, crashes, runs, "in_process")
        if capture is not None:
            j = Journal(wd / "journal.db")
            capture.update(events=j.events(TASK), state=replay(j.events(TASK)), markers=markers,
                           world=load(wd / "world.json"), plan=plan)
            j.close()
        return trial


def _last_seq(wd: Path) -> int:
    if not (wd / "journal.db").exists():
        return 0
    return max((r[0] for r in _raw_events(wd / "journal.db")), default=0)


def run_combined(name: str, seed: int, capture: dict | None = None) -> M3Trial:
    """Combined M1->M2->M3 scenario (fixture_c.COMBINED) through the real controller."""
    spec = COMBINED[name]
    cls = spec["cls"]
    base = plan_trial(cls, spec.get("boundary", "none"), seed)
    plan = TrialPlan(cls, spec.get("boundary", "none"), seed, base.steps, spec.get("fault", "honest"), None)
    kind = plan.steps[0]["kind"]
    mut = spec.get("ui_mutation")
    granted = [k for k in KIND_CLASS if k != kind] if spec.get("granted_exclude") else None
    return run_trial(cls, None, seed, plan=plan, capture=capture,
                     ui_mutation=(mut[0], mut[1], kind) if mut else None, granted=granted)


def run_trial_subprocess(effect_class: EffectClass, boundary: str, seed: int, workdir: Path) -> M3Trial:
    """Same trial, but every controller lifetime is a separate OS process killed with SIGKILL."""
    plan = plan_trial(effect_class, boundary, seed)
    new_world(workdir / "world.json", random.Random(seed))
    crashes: list[str] = []
    runs = 0
    for runs in range(1, MAX_RUNS + 1):
        proc = subprocess.run(
            [sys.executable, "-m", "tests.computer_agent.m3_campaign", "--worker", str(workdir),
             effect_class.value, boundary, str(seed), str(runs - 1)],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        if proc.returncode == -signal.SIGKILL:
            crashes.append(f"SIGKILL@{plan.boundary if runs == 1 else plan.second_boundary}")
            continue
        if proc.returncode != 0:
            raise RuntimeError(f"worker failed rc={proc.returncode}: {proc.stderr[-2000:]}")
        break
    return grade(workdir, plan, crashes, runs, "subprocess_sigkill")


@dataclass
class M3Report:
    total_trials: int
    by_class: dict[str, int]
    by_final: dict[str, dict[str, int]]
    crash_fired: int
    second_crash_fired: int
    totals: dict[str, int]
    failing: list[dict]


METRICS = ("duplicate_effects", "lost_effects", "incorrect_verified_success", "unsafe_retries",
           "unresolved_auto_advanced", "dispatch_without_durable_start", "stale_or_wrong_target_dispatches",
           "reconstruction_failures", "action_id_instability", "reconciled", "needs_review", "outcome_unknown",
           "safe_key_retries", "idempotent_reapplies")


def run_campaign(per_class: int, base_seed: int = 0, evidence_dir: Path | None = None,
                 subprocess_mode: bool = False) -> M3Report:
    by_class: Counter = Counter()
    by_final: dict[str, Counter] = {c.value: Counter() for c in CLASSES}
    totals: Counter = Counter()
    fired = second = 0
    failing: list[dict] = []
    fh = None
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        tag = "m3_subprocess" if subprocess_mode else "m3_campaign"
        fh = (evidence_dir / f"{tag}-seed{base_seed}-n{per_class}perclass.jsonl").open("w")
    try:
        i = 0
        for c in CLASSES:
            for k in range(per_class):
                boundary = CRASH_BOUNDARIES[k % len(CRASH_BOUNDARIES)]
                seed = base_seed + i
                i += 1
                if subprocess_mode:
                    with tempfile.TemporaryDirectory() as tmp:
                        t = run_trial_subprocess(c, boundary, seed, Path(tmp))
                else:
                    t = run_trial(c, boundary, seed)
                by_class[c.value] += 1
                by_final[c.value][t.final] += 1
                fired += bool(t.crashes)
                second += len(t.crashes) > 1
                for m in METRICS:
                    totals[m] += getattr(t, m)
                if t.safety_failures:
                    failing.append({"class": c.value, "boundary": boundary, "seed": seed, "notes": t.notes})
                if fh:
                    fh.write(json.dumps(asdict(t)) + "\n")
    finally:
        if fh:
            fh.close()
    report = M3Report(sum(by_class.values()), dict(by_class), {k: dict(v) for k, v in by_final.items()},
                      fired, second, {m: totals[m] for m in METRICS}, failing)
    if evidence_dir is not None:
        tag = "m3_subprocess" if subprocess_mode else "m3_campaign"
        (evidence_dir / f"{tag}-seed{base_seed}-n{per_class}perclass-summary.json").write_text(
            json.dumps(asdict(report), indent=2))
    return report


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        workdir, cls, boundary, seed, run_index = sys.argv[2:7]
        controller_session(Path(workdir), plan_trial(EffectClass(cls), boundary, int(seed)), int(run_index),
                           kill=True)
        sys.exit(0)
    import argparse

    ap = argparse.ArgumentParser(description="Run the M3 crash-recovery campaign")
    ap.add_argument("--per-class", type=int, default=1044)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--subprocess", action="store_true")
    ap.add_argument("--evidence", type=Path, default=Path("computer_agent/results"))
    a = ap.parse_args()
    r = run_campaign(a.per_class, a.seed, a.evidence, a.subprocess)
    print(json.dumps({k: v for k, v in asdict(r).items() if k != "failing"}, indent=2))
    print("failing trials:", len(r.failing), r.failing[:5])
