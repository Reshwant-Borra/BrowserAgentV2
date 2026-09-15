"""Experiment 6 recovery pass.

Runs in a fresh process with nothing but the journal and the world. Decides,
for the interrupted intent, which of three states holds:

    DEFINITELY_NOT_EXECUTED   safe to execute now
    DEFINITELY_EXECUTED       record the outcome; never replay
    AMBIGUOUS                 escalate to the human; never replay

Two policies are implemented. `reconcile` is the architecture under test.
`blind_replay` is the control — the thing the repository forbids — included so
the experiment can show that the safe policy is doing real work.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.side_effect_recovery.journal import Journal

NOT_EXECUTED = "DEFINITELY_NOT_EXECUTED"
EXECUTED = "DEFINITELY_EXECUTED"
AMBIGUOUS = "AMBIGUOUS"


def durable_evidence(origin: str, operation_id: str) -> dict:
    """Ask the world, not the agent's memory, whether the effect landed."""
    try:
        with urllib.request.urlopen(
            f"{origin}/api/op?operation_id={operation_id}", timeout=10
        ) as r:
            return {"reachable": True, **json.loads(r.read())}
    except Exception as e:
        return {"reachable": False, "error": str(e)[:200]}


def classify(journal: Journal, origin: str, evidence_available: bool = True) -> dict:
    intent = journal.open_intent()
    if intent is None:
        return {
            "state": NOT_EXECUTED,
            "basis": "no open intent in the journal; nothing was ever dispatched",
            "intent": None,
        }

    status = intent["status"]
    op = (intent.get("data") or {}).get("operation_id")

    if status == "PREPARED":
        # DISPATCHED is always committed before the browser is touched, so a
        # PREPARED intent provably never reached the browser.
        return {
            "state": NOT_EXECUTED,
            "basis": "intent is PREPARED and was never DISPATCHED; the ordering "
                     "rule guarantees the browser was not touched",
            "intent": intent,
        }

    if status in ("RESULT_RECORDED", "VERIFIED"):
        return {
            "state": EXECUTED,
            "basis": f"journal already holds an ActionResult for {op}",
            "intent": intent,
        }

    # DISPATCHED: the agent's own memory cannot distinguish the cases. Only
    # durable external evidence can.
    if not evidence_available:
        return {
            "state": AMBIGUOUS,
            "basis": "intent was DISPATCHED and no durable evidence channel is "
                     "available; escalating to the user rather than replaying",
            "intent": intent,
        }
    ev = durable_evidence(origin, op)
    if not ev.get("reachable"):
        return {
            "state": AMBIGUOUS,
            "basis": f"evidence channel unreachable ({ev.get('error')}); refusing "
                     "to replay a consequential action",
            "intent": intent,
            "evidence": ev,
        }
    if ev.get("found"):
        return {
            "state": EXECUTED,
            "basis": f"durable record exists for operation {op} "
                     f"(seq {ev.get('confirmation_seq')})",
            "intent": intent,
            "evidence": ev,
        }
    return {
        "state": NOT_EXECUTED,
        "basis": f"durable store has no record of operation {op}",
        "intent": intent,
        "evidence": ev,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--policy", default="reconcile", choices=["reconcile", "blind_replay"])
    ap.add_argument("--evidence", default="available",
                    choices=["available", "unavailable"])
    ap.add_argument("--crash-during", dest="crash_during", action="store_true",
                    help="die after classifying but before persisting the outcome, "
                         "so a second recovery pass must cope with a half-finished "
                         "reconciliation")
    args = ap.parse_args()

    j = Journal(args.journal)

    if args.policy == "blind_replay":
        # CONTROL ARM. This is the behaviour the architecture forbids; it exists
        # only to prove the duplicate is detectable when it happens.
        intent = j.open_intent()
        decision = {
            "policy": "blind_replay",
            "state": "IGNORED",
            "action": "REPLAY" if intent else "NOTHING_TO_REPLAY",
            "intent": intent,
        }
        print(json.dumps(decision))
        return

    cl = classify(j, args.origin, evidence_available=(args.evidence == "available"))
    if args.crash_during:
        # Reconciliation itself is interruptible. Dying here leaves the journal
        # exactly as it was, so the next pass must reach the same conclusion
        # from the same durable evidence rather than assuming progress was made.
        import os
        sys.stderr.write("[recovery] simulated hard crash during reconciliation\n")
        sys.stderr.flush()
        os._exit(70)
    if cl["state"] == EXECUTED:
        action = "RECORD_AS_DONE_NO_REPLAY"
        if cl.get("intent"):
            j.append("RECONCILED", intent_id=cl["intent"]["intent_id"],
                     state=cl["state"], basis=cl["basis"])
            j.append("INTENT_COMPLETED", intent_id=cl["intent"]["intent_id"])
    elif cl["state"] == NOT_EXECUTED:
        action = "SAFE_TO_EXECUTE"
        if cl.get("intent"):
            j.append("RECONCILED", intent_id=cl["intent"]["intent_id"],
                     state=cl["state"], basis=cl["basis"])
    else:
        action = "ESCALATE_TO_USER_WAITING_FOR_CONFIRMATION"
        if cl.get("intent"):
            j.append("RECONCILED", intent_id=cl["intent"]["intent_id"],
                     state=cl["state"], basis=cl["basis"])
            j.append("HANDOFF_REQUIRED", intent_id=cl["intent"]["intent_id"],
                     reason="ambiguous consequential action")
    print(json.dumps({"policy": "reconcile", "action": action, **cl}))


if __name__ == "__main__":
    main()
