"""Experiment 7 — human handoff and resume.

Question
--------
Can the agent pause for a human and resume without trusting stale state?

Protocol under test (END_TO_END_SYSTEM_SPEC section 13):

    operate -> checkpoint -> WAITING_FOR_USER -> human acts in the browser
            -> resume -> invalidate ALL old targets -> rediscover pages
            -> fresh observation -> continue the same subgoal

Invariant: after a human has touched the browser, NO pre-handoff target is
trusted. Not "usually"; not "unless the page looks the same".

The human is simulated by driving the raw browser directly, entirely outside
the kernel's API, so the kernel genuinely does not know what happened.

Reproduce:
    python -m experiments.human_handoff.run_handoff --reps 10
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.contracts import KernelError, Owner
from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel
from experiments.side_effect_recovery.journal import Journal

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

PASS, FAIL, FATAL, HARNESS = "PASS", "FAIL", "FATAL_STALE_TRUSTED", "HARNESS_ERROR"


def rec(status, detail, **kw):
    return {"status": status, "detail": detail, **kw}

def observed_text(obs) -> str:
    """Join an observation's text blocks.

    Observation Contract V1 makes each block a frame-scoped record rather than a
    bare string. Tolerates both so historical observations still render.
    """
    out = []
    for b in getattr(obs, "text_blocks", []) or []:
        out.append(b.text if hasattr(b, "text") else str(b))
    return " ".join(out)



def find(obs, **kw):
    for e in obs.elements:
        if "name" in kw and e.name.strip() != kw["name"]:
            continue
        if "contains" in kw and kw["contains"].lower() not in e.name.lower():
            continue
        return e
    return None


def checkpoint(j: Journal, state: str, subgoal: str, **kw):
    j.append("CHECKPOINT", state=state, subgoal=subgoal, **kw)


def resume(k, j: Journal, subgoal: str):
    """The resume half of the protocol. Nothing from before survives it."""
    k.invalidate_all_observations("resume after human handoff")
    pages = k.list_pages()
    j.append(
        "RESUMED",
        subgoal=subgoal,
        rediscovered_pages=[
            {"page_id": p.page_id, "owner": p.owner.value, "url": p.url, "closed": p.closed}
            for p in pages
        ],
    )
    return pages


def assert_all_stale(k, targets) -> tuple[bool, list]:
    """Every pre-handoff target must fail closed."""
    survived = []
    for t in targets:
        try:
            k.read_value(t)
            survived.append(t)
        except KernelError:
            pass
        except Exception:
            pass
    return (not survived), survived


def reach_password_stage(k, c):
    k.navigate(c.url("/p/login"))
    return k.observe()


# ==========================================================================
# scenarios: what the human does while the agent is paused
# ==========================================================================


def _handoff_cycle(k, c, j, human_action, subgoal="sign in to the portal"):
    obs = reach_password_stage(k, c)
    pre_targets = [e.target for e in obs.elements]
    checkpoint(j, "WAITING_FOR_USER", subgoal,
               reason="password entry is the human's job",
               observation_id=obs.observation_id)

    page = k.page_object()
    human_action(k, c, page)
    time.sleep(0.4)

    resume(k, j, subgoal)
    all_stale, survived = assert_all_stale(k, pre_targets)
    return obs, pre_targets, all_stale, survived


def h01_human_completes_login(k, c, j):
    def human(k_, c_, page):
        # The human types the password and clears MFA/CAPTCHA themselves.
        page.fill("#user", "student")
        page.fill("#pass", "hunter2")
        page.click("#signin")
        time.sleep(0.2)
        page.fill("#code", "483921")
        page.click("#verify")
        time.sleep(0.2)
        page.check("#human")
        time.sleep(0.2)
        page.click("#acct-school")

    _o, _t, all_stale, survived = _handoff_cycle(k, c, j, human)
    obs2 = k.observe()
    reached = find(obs2, name="Continue") is not None
    if not all_stale:
        return rec(FATAL, f"pre-handoff targets still usable after resume: {survived[:4]}")
    return rec(PASS if reached else FAIL,
               f"all {len(_t)} pre-handoff targets invalidated; dashboard reached={reached}")


def h02_human_navigates_away(k, c, j):
    def human(k_, c_, page):
        page.goto(c_.url("/p/duplicate_names"), wait_until="domcontentloaded")

    _o, t, all_stale, survived = _handoff_cycle(k, c, j, human)
    if not all_stale:
        return rec(FATAL, f"targets survived a human navigation: {survived[:4]}")
    obs2 = k.observe()
    return rec(PASS, f"all {len(t)} targets invalidated; agent re-observed {obs2.url}")


def h03_human_rerenders_page(k, c, j):
    def human(k_, c_, page):
        page.evaluate(
            """() => {
                 // Same URL, same document, whole form rebuilt from scratch.
                 const b = document.body;
                 b.innerHTML = b.innerHTML;
               }"""
        )

    _o, t, all_stale, survived = _handoff_cycle(k, c, j, human)
    if not all_stale:
        return rec(FATAL, f"targets survived a human-triggered rerender: {survived[:4]}")
    return rec(PASS, f"all {len(t)} targets invalidated after in-place rerender")


def h04_human_opens_tab(k, c, j):
    created = {}

    def human(k_, c_, page):
        p2 = k_.context.new_page()
        p2.goto(c_.url("/p/basic"), wait_until="domcontentloaded")
        created["p"] = p2

    _o, t, all_stale, survived = _handoff_cycle(k, c, j, human)
    pages = k.list_pages()
    user_pages = [p for p in pages if p.owner is Owner.USER and not p.closed]
    if not all_stale:
        return rec(FATAL, f"targets survived: {survived[:4]}")
    return rec(PASS if user_pages else FAIL,
               f"rediscovered {len(pages)} pages; "
               f"human tab registered as USER={bool(user_pages)}")


def h05_human_closes_agent_tab(k, c, j):
    extra = {}

    def human(k_, c_, page):
        pid = k_.new_tab(c_.url("/p/basic"))
        extra["pid"] = pid
        k_._pages[pid].close()

    _o, t, all_stale, survived = _handoff_cycle(k, c, j, human)
    st = {p.page_id: p.closed for p in k.list_pages()}
    closed_ok = st.get(extra.get("pid")) is True
    if not all_stale:
        return rec(FATAL, f"targets survived: {survived[:4]}")
    return rec(PASS if closed_ok else FAIL,
               f"closed tab reflected in registry={closed_ok}")


def h06_human_switches_account(k, c, j):
    """The human signs in as a *different* account than the agent expected."""
    def human(k_, c_, page):
        page.fill("#user", "someone-else")
        page.fill("#pass", "x")
        page.click("#signin")
        time.sleep(0.15)
        page.fill("#code", "111111")
        page.click("#verify")
        time.sleep(0.15)
        page.check("#human")
        time.sleep(0.15)
        page.click("#acct-work")

    _o, t, all_stale, survived = _handoff_cycle(k, c, j, human)
    if not all_stale:
        return rec(FATAL, f"targets survived an account switch: {survived[:4]}")
    obs2 = k.observe()
    txt = observed_text(obs2)
    saw_work = "account=work" in txt
    return rec(PASS if saw_work else FAIL,
               f"fresh observation reports the account the human actually chose: "
               f"work={saw_work}")


def h07_agent_does_not_overwrite_human(k, c, j):
    """After the human fills a field, resuming must not clobber their input."""
    obs = k.navigate(c.url("/p/login")) or k.observe()
    checkpoint(j, "WAITING_FOR_USER", "sign in", reason="password")
    page = k.page_object()
    page.fill("#user", "human-typed-name")
    resume(k, j, "sign in")
    obs2 = k.observe()
    el = find(obs2, name="Username")
    val = k.read_value(el.target) if el else None
    return rec(PASS if val == "human-typed-name" else FAIL,
               f"username field after resume={val!r}")


def h08_confirmation_handoff(k, c, j):
    """WAITING_FOR_CONFIRMATION around a consequential control."""
    k.navigate(c.url("/p/submit_op"))
    obs = k.observe()
    pre = [e.target for e in obs.elements]
    checkpoint(j, "WAITING_FOR_CONFIRMATION", "submit the booking",
               reason="consequential action requires approval")
    page = k.page_object()
    page.fill("#amount", "3")  # the human edits the amount while deciding
    resume(k, j, "submit the booking")
    all_stale, survived = assert_all_stale(k, pre)
    obs2 = k.observe()
    el = find(obs2, name="Amount")
    val = k.read_value(el.target) if el else None
    if not all_stale:
        return rec(FATAL, f"pre-confirmation targets still usable: {survived[:4]}")
    return rec(PASS if val == "3" else FAIL,
               f"targets invalidated; human's edited amount preserved={val!r}")


SCENARIOS = [
    ("HH-01-human-completes-login", h01_human_completes_login),
    ("HH-02-human-navigates-away", h02_human_navigates_away),
    ("HH-03-human-rerenders-page", h03_human_rerenders_page),
    ("HH-04-human-opens-tab", h04_human_opens_tab),
    ("HH-05-human-closes-tab", h05_human_closes_agent_tab),
    ("HH-06-human-switches-account", h06_human_switches_account),
    ("HH-07-agent-does-not-overwrite-human", h07_agent_does_not_overwrite_human),
    ("HH-08-confirmation-handoff", h08_confirmation_handoff),
]


def restart_during_handoff(cluster) -> dict:
    """Controller dies while WAITING_FOR_USER. The human finishes the login.
    A fresh controller must resume the subgoal without trusting anything old."""
    profile = tempfile.mkdtemp(prefix="bav2hh_")
    jpath = tempfile.mktemp(suffix=".sqlite")
    try:
        j = Journal(jpath)
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        k.navigate(cluster.url("/p/login"))
        obs = k.observe()
        pre = [e.target for e in obs.elements]
        checkpoint(j, "WAITING_FOR_USER", "sign in to the portal", reason="password")
        # human logs in
        page = k.page_object()
        page.fill("#user", "student")
        page.fill("#pass", "hunter2")
        page.click("#signin")
        time.sleep(0.2)
        page.fill("#code", "483921")
        page.click("#verify")
        time.sleep(0.2)
        page.check("#human")
        time.sleep(0.2)
        page.click("#acct-school")
        time.sleep(0.3)
        k.shutdown()  # controller dies here

        # fresh controller, same persistent profile
        k2 = DirectPlaywrightKernel(profile, headless=True)
        k2.start()
        events = Journal(jpath).events()
        cp = [e for e in events if e["kind"] == "CHECKPOINT"][-1]
        subgoal = cp["payload"]["subgoal"]
        k2.navigate(cluster.url("/p/login"))
        resume(k2, Journal(jpath), subgoal)
        all_stale, survived = assert_all_stale(k2, pre)
        obs2 = k2.observe()
        txt = observed_text(obs2)
        session_alive = "account=school" in txt
        k2.shutdown()
        if not all_stale:
            return rec(FATAL, f"pre-restart targets usable after restart: {survived[:4]}")
        return rec(PASS if session_alive else FAIL,
                   f"subgoal recovered={subgoal!r}; session survived restart="
                   f"{session_alive}; all pre-handoff targets invalid")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        Path(jpath).unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=10)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    cluster = FixtureCluster(tempfile.mktemp(suffix=".sqlite")).start()
    rows = []
    try:
        for rep in range(1, args.reps + 1):
            for name, fn in SCENARIOS:
                profile = tempfile.mkdtemp(prefix="bav2hh_")
                jpath = tempfile.mktemp(suffix=".sqlite")
                k = None
                row = {"rep": rep, "case": name}
                try:
                    k = DirectPlaywrightKernel(profile, headless=True)
                    k.start()
                    row.update(fn(k, cluster, Journal(jpath)))
                except Exception as e:
                    row.update(rec(HARNESS, f"{type(e).__name__}: {e}",
                                   traceback=traceback.format_exc()[-700:]))
                finally:
                    if k:
                        try:
                            k.shutdown()
                        except Exception:
                            pass
                    shutil.rmtree(profile, ignore_errors=True)
                    Path(jpath).unlink(missing_ok=True)
                rows.append(row)
            try:
                rows.append({"rep": rep, "case": "HH-09-restart-during-handoff",
                             **restart_during_handoff(cluster)})
            except Exception as e:
                rows.append({"rep": rep, "case": "HH-09-restart-during-handoff",
                             **rec(HARNESS, f"{type(e).__name__}: {e}")})
            print(f"rep {rep}/{args.reps}", flush=True)
    finally:
        cluster.stop()

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    by_case = {}
    for n in sorted({r["case"] for r in rows}):
        sub = [r for r in rows if r["case"] == n]
        cc: dict[str, int] = {}
        for r in sub:
            cc[r["status"]] = cc.get(r["status"], 0) + 1
        by_case[n] = cc

    payload = {
        "experiment": "E7_human_handoff_resume",
        "question": "Can the agent pause for a human and resume without trusting stale state?",
        "invariant": "after human interaction, no pre-handoff target is trusted",
        "environment": capture({"experiment": "E7_human_handoff_resume"}),
        "reps": args.reps,
        "summary": {
            "total_runs": len(rows),
            "counts": counts,
            "stale_targets_trusted": counts.get(FATAL, 0),
            "fatal_cases": sorted({r["case"] for r in rows if r["status"] == FATAL}),
            "failing_cases": sorted({r["case"] for r in rows if r["status"] == FAIL}),
            "harness_error_cases": sorted(
                {r["case"] for r in rows if r["status"] == HARNESS}
            ),
            "by_case": by_case,
        },
        "raw": rows,
    }
    out = RESULTS / "experiment7_raw.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))
    print(f"\nraw -> {out}")


if __name__ == "__main__":
    main()
