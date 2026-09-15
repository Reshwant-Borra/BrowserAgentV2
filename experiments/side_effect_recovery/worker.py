"""Experiment 6 worker: performs ONE consequential submission, optionally dying
at a named boundary, then exits.

Crashes are real: os._exit(70) skips every finally block, atexit hook, buffer
flush and destructor. Anything not already committed to the journal is gone,
which is exactly what a hard crash means.

Invoked as a subprocess by run_side_effects.py so that the recovery pass runs
in a genuinely fresh process with nothing in memory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.kernel_direct import DirectPlaywrightKernel
from experiments.side_effect_recovery.journal import Journal

# Boundaries from MASTER_VALIDATION_PLAN section 7.
CRASH_POINTS = [
    "none",
    "before_intent_commit",
    "after_intent_commit_before_execute",
    "during_execute",
    "after_server_committed_before_result",
    "after_result_before_result_commit",
    "after_result_commit_before_verification",
    "during_reconciliation",
]


def die(point: str):
    sys.stderr.write(f"[worker] simulated hard crash at {point}\n")
    sys.stderr.flush()
    os._exit(70)


def find(obs, name):
    for e in obs.elements:
        if e.name.strip() == name:
            return e
    raise LookupError(f"{name!r} not in observation: {[e.name for e in obs.elements]}")


def run(args):
    j = Journal(args.journal)
    crash = args.crash

    k = DirectPlaywrightKernel(args.profile, headless=True)
    k.start()
    try:
        k.navigate(args.url)
        obs = k.observe()
        j.append("OBSERVED", observation_id=obs.observation_id, url=obs.url)

        # ---- prepare the intent (in memory only) ---------------------------
        intent_id = args.intent_id
        operation_id = args.operation_id
        if crash == "before_intent_commit":
            die(crash)

        # ---- commit the intent ---------------------------------------------
        j.append(
            "INTENT_PREPARED",
            intent_id=intent_id,
            operation_id=operation_id,
            action="CLICK",
            risk="CONSEQUENTIAL",
            idempotence="UNKNOWN",
            url=args.url,
            amount=args.amount,
        )
        if crash == "after_intent_commit_before_execute":
            die(crash)

        # ---- fill the form (non-consequential) ------------------------------
        k.type_text(find(obs, "Operation ID").target, operation_id)
        k.type_text(find(obs, "Amount").target, str(args.amount))
        if args.post_delay_ms:
            k.type_text(
                find(obs, "Server post-commit delay ms").target, str(args.post_delay_ms)
            )
        obs2 = k.observe()

        # ---- THE ordering rule: DISPATCHED is durable before the browser acts
        j.append("INTENT_DISPATCHED", intent_id=intent_id, operation_id=operation_id)

        submit = find(obs2, "Submit booking")
        if crash == "during_execute":
            # Crash with the click in flight: issue it and die immediately.
            page = k.page_object()
            page.evaluate(
                "() => { document.getElementById('submit').click(); }"
            )
            die(crash)

        if crash == "after_server_committed_before_result":
            page = k.page_object()
            page.evaluate("() => { document.getElementById('submit').click(); }")
            # post_delay_ms holds the response open while the effect is already
            # committed server-side.
            time.sleep(max(0.15, args.post_delay_ms / 1000.0 * 0.5))
            die(crash)

        k.click(submit.target)
        time.sleep(0.4)

        if crash == "after_result_before_result_commit":
            die(crash)

        # ---- record the browser-visible result ------------------------------
        page = k.page_object()
        state = page.evaluate("() => ({s: window.__submit_state, r: window.__last_result})")
        j.append(
            "ACTION_RESULT",
            intent_id=intent_id,
            execution_status="OK" if state.get("s") == "done" else "UNKNOWN",
            browser_state=state.get("s"),
            server_reply=state.get("r"),
        )
        if crash == "after_result_commit_before_verification":
            die(crash)

        # ---- deterministic verification --------------------------------------
        obs3 = k.observe()
        text = " ".join(obs3.text_blocks)
        satisfied = f"Reference {operation_id}" in text
        j.append(
            "VERIFICATION",
            intent_id=intent_id,
            status="SATISFIED" if satisfied else "AMBIGUOUS",
            evidence=text[:300],
        )
        j.append("INTENT_COMPLETED", intent_id=intent_id)
        print(json.dumps({"ok": True, "verified": satisfied}))
    finally:
        try:
            k.shutdown()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--intent-id", dest="intent_id", required=True)
    ap.add_argument("--operation-id", dest="operation_id", required=True)
    ap.add_argument("--amount", type=int, default=1)
    ap.add_argument("--post-delay-ms", dest="post_delay_ms", type=int, default=0)
    ap.add_argument("--crash", default="none", choices=CRASH_POINTS)
    run(ap.parse_args())


if __name__ == "__main__":
    main()
