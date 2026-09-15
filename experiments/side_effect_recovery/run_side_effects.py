"""Experiment 6 — ambiguous side-effect / crash recovery.

Question
--------
Can BrowserAgent survive a crash around a state-changing operation without
blindly performing it twice?

Critical invariant: ZERO duplicate side effects caused by blind retry.

Design
------
The fixture server is a WORST-CASE web application: `dedupe=false`, so it
happily performs the same booking twice. Server-side idempotency would hide an
agent-side double submit, so it is deliberately switched off. Every accepted
effect is counted from the server's durable ledger, not from the agent's logs.

Each trial:
    1. a worker subprocess performs one consequential submission and dies
       (os._exit) at one of seven boundaries;
    2. a recovery subprocess starts fresh with only the journal and the world;
    3. the server ledger is counted.

Two recovery policies run over identical crash points:
    reconcile     — the architecture under test
    blind_replay  — the forbidden control, present to prove duplicates are
                    detectable at all

Reproduce:
    python -m experiments.side_effect_recovery.run_side_effects --reps 3
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.side_effect_recovery.journal import Journal
from experiments.side_effect_recovery.worker import CRASH_POINTS

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ROOT = Path(__file__).resolve().parents[2]

POST_DELAY_FOR = {"after_server_committed_before_result": 1200}


def effects_for(origin: str, op: str) -> dict:
    with urllib.request.urlopen(f"{origin}/api/effects", timeout=15) as r:
        d = json.loads(r.read())
    arrivals = [a for a in d["arrivals"] if a["operation_id"] == op]
    with urllib.request.urlopen(f"{origin}/api/op?operation_id={op}", timeout=15) as r:
        lookup = json.loads(r.read())
    # The ledger records a duplicate acceptance under "<op>#dup...".
    dup_rows = [a for a in d["arrivals"] if a["operation_id"] == op and a["duplicate"]]
    return {
        "arrivals": len(arrivals),
        "duplicate_arrivals": len(dup_rows),
        "committed": bool(lookup.get("found")),
        "lookup": lookup,
    }


def committed_effect_count(origin: str, op: str) -> int:
    """How many real effects exist for this operation, including duplicates."""
    with urllib.request.urlopen(f"{origin}/api/effects", timeout=15) as r:
        d = json.loads(r.read())
    n = 0
    for a in d["arrivals"]:
        if a["operation_id"] != op:
            continue
        # Every non-duplicate arrival commits an effect; with dedupe=false a
        # duplicate arrival commits a SECOND one.
        n += 1
    return n


def run_proc(cmd: list[str], timeout=300) -> dict:
    p = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout
    )
    return {"rc": p.returncode, "stdout": p.stdout.strip()[-2000:],
            "stderr": p.stderr.strip()[-1200:]}


def trial(cluster, crash: str, policy: str, idx: int, evidence="available") -> dict:
    op = f"BK-{crash}-{policy}-{idx}-{int(time.time()*1000)%100000}"
    intent = f"intent_{idx}"
    jpath = tempfile.mktemp(suffix=".sqlite", prefix="journal_")
    profile = tempfile.mkdtemp(prefix="bav2se_")
    row = {"crash_point": crash, "policy": policy, "operation_id": op,
           "evidence": evidence}
    try:
        # "during_reconciliation" means the crash happens in the RECOVERY pass,
        # so the worker runs to the same place as the post-commit window and the
        # interruption is injected afterwards.
        worker_crash = (
            "after_server_committed_before_result"
            if crash == "during_reconciliation" else crash
        )
        w = run_proc([
            sys.executable, "-m", "experiments.side_effect_recovery.worker",
            "--journal", jpath, "--profile", profile,
            "--url", cluster.url("/p/submit_op"),
            "--intent-id", intent, "--operation-id", op,
            "--post-delay-ms", str(POST_DELAY_FOR.get(worker_crash, 0)),
            "--crash", worker_crash,
        ])
        row["worker_rc"] = w["rc"]
        row["worker_crashed"] = w["rc"] == 70
        row["effects_after_crash"] = committed_effect_count(cluster.primary_origin, op)

        if crash == "during_reconciliation" and policy == "reconcile":
            r0 = run_proc([
                sys.executable, "-m", "experiments.side_effect_recovery.recovery",
                "--journal", jpath, "--origin", cluster.primary_origin,
                "--policy", policy, "--evidence", evidence, "--crash-during",
            ])
            row["reconciliation_crash_rc"] = r0["rc"]
            row["reconciliation_crashed"] = r0["rc"] == 70

        r = run_proc([
            sys.executable, "-m", "experiments.side_effect_recovery.recovery",
            "--journal", jpath, "--origin", cluster.primary_origin,
            "--policy", policy, "--evidence", evidence,
        ])
        row["recovery_rc"] = r["rc"]
        try:
            rec = json.loads(r["stdout"].splitlines()[-1]) if r["stdout"] else {}
        except Exception:
            rec = {"parse_error": r["stdout"][-400:]}
        row["recovery"] = {k: rec.get(k) for k in ("policy", "action", "state", "basis")}

        # Carry out what recovery decided, in a fresh process.
        replayed = False
        if policy == "blind_replay" and rec.get("action") == "REPLAY":
            replayed = True
        elif policy == "reconcile" and rec.get("action") == "SAFE_TO_EXECUTE" \
                and rec.get("intent"):
            replayed = True
        if replayed:
            profile2 = tempfile.mkdtemp(prefix="bav2se2_")
            try:
                w2 = run_proc([
                    sys.executable, "-m", "experiments.side_effect_recovery.worker",
                    "--journal", jpath, "--profile", profile2,
                    "--url", cluster.url("/p/submit_op"),
                    "--intent-id", intent + "_retry", "--operation-id", op,
                    "--crash", "none",
                ])
                row["replay_rc"] = w2["rc"]
            finally:
                shutil.rmtree(profile2, ignore_errors=True)
        row["replayed"] = replayed

        final = committed_effect_count(cluster.primary_origin, op)
        row["final_effect_count"] = final
        row["duplicate_side_effect"] = final > 1
        row["journal_events"] = [e["kind"] for e in Journal(jpath).events()]
        return row
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        try:
            Path(jpath).unlink(missing_ok=True)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--policies", default="reconcile,blind_replay")
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    cluster = FixtureCluster(tempfile.mktemp(suffix=".sqlite")).start()
    rows = []
    crash_points = [c for c in CRASH_POINTS if c != "none"]
    try:
        for policy in args.policies.split(","):
            policy = policy.strip()
            for rep in range(1, args.reps + 1):
                for crash in crash_points:
                    r = trial(cluster, crash, policy, rep)
                    r["rep"] = rep
                    rows.append(r)
                    print(
                        f"  [{policy}] rep{rep} {crash:42s} "
                        f"crashed={r.get('worker_crashed')} "
                        f"after_crash={r.get('effects_after_crash')} "
                        f"action={r['recovery'].get('action')} "
                        f"final={r['final_effect_count']} "
                        f"dup={r['duplicate_side_effect']}",
                        flush=True,
                    )
                # Evidence-channel-unavailable variant (reconcile only).
                if policy == "reconcile":
                    r = trial(cluster, "after_server_committed_before_result",
                              policy, rep, evidence="unavailable")
                    r["rep"] = rep
                    rows.append(r)
                    print(
                        f"  [{policy}] rep{rep} evidence-unavailable"
                        f"{'':22s} action={r['recovery'].get('action')} "
                        f"final={r['final_effect_count']} "
                        f"dup={r['duplicate_side_effect']}",
                        flush=True,
                    )
    finally:
        cluster.stop()

    summary = {}
    for policy in sorted({r["policy"] for r in rows}):
        sub = [r for r in rows if r["policy"] == policy]
        dups = [r for r in sub if r["duplicate_side_effect"]]
        summary[policy] = {
            "trials": len(sub),
            "crashes_injected": sum(1 for r in sub if r.get("worker_crashed")),
            "duplicate_side_effects": len(dups),
            "duplicate_crash_points": sorted({r["crash_point"] for r in dups}),
            "final_effect_distribution": _dist(r["final_effect_count"] for r in sub),
            "recovery_actions": _dist(r["recovery"].get("action") for r in sub),
            "states": _dist(r["recovery"].get("state") for r in sub),
            "by_crash_point": {
                cp: {
                    "n": len([r for r in sub if r["crash_point"] == cp]),
                    "actions": _dist(
                        r["recovery"].get("action") for r in sub if r["crash_point"] == cp
                    ),
                    "states": _dist(
                        r["recovery"].get("state") for r in sub if r["crash_point"] == cp
                    ),
                    "effects": _dist(
                        r["final_effect_count"] for r in sub if r["crash_point"] == cp
                    ),
                    "duplicates": sum(
                        1 for r in sub
                        if r["crash_point"] == cp and r["duplicate_side_effect"]
                    ),
                }
                for cp in sorted({r["crash_point"] for r in sub})
            },
        }

    payload = {
        "experiment": "E6_ambiguous_side_effect_recovery",
        "question": "Can the agent survive a crash around a state-changing operation "
                    "without performing it twice?",
        "invariant": "zero duplicate side effects caused by blind retry",
        "server_mode": "dedupe=false (worst-case app; duplicates really happen)",
        "environment": capture({"experiment": "E6_ambiguous_side_effect_recovery"}),
        "crash_points": crash_points,
        "reps": args.reps,
        "summary": summary,
        "raw": rows,
    }
    out = RESULTS / "experiment6_raw.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nraw -> {out}")


def _dist(it):
    d: dict[str, int] = {}
    for v in it:
        d[str(v)] = d.get(str(v), 0) + 1
    return dict(sorted(d.items()))


if __name__ == "__main__":
    main()
