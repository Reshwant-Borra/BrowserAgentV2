"""Profile strategy confirmation.

Question
--------
Does a dedicated Playwright-managed persistent profile actually deliver the
properties the architecture assumes, and does it stay isolated from the user's
daily-driver browser?

Tested:
  * cookie persistence across controller restart
  * localStorage persistence across controller restart
  * a manually completed login surviving restart
  * a second controller restart (no drift)
  * isolation between two different agent profiles
  * isolation from the user's real Chrome profile directory (never touched)
  * profile lock behaviour when two controllers share one profile

Reproduce:
    python -m experiments.profile_strategy.run_profile --reps 6
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PASS, FAIL, HARNESS = "PASS", "FAIL", "HARNESS_ERROR"


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



def do_login(k, cluster):
    """Drive the fixture login all the way to the dashboard."""
    k.navigate(cluster.url("/p/login"))
    p = k.page_object()
    p.fill("#user", "student")
    p.fill("#pass", "hunter2")
    p.click("#signin")
    time.sleep(0.2)
    p.fill("#code", "483921")
    p.click("#verify")
    time.sleep(0.2)
    p.check("#human")
    time.sleep(0.2)
    p.click("#acct-school")
    time.sleep(0.3)


def storage(k, cluster):
    k.navigate(cluster.url("/p/login"))
    return k.storage_snapshot()


def c01_cookie_and_localstorage_survive_restart(cluster) -> dict:
    profile = tempfile.mkdtemp(prefix="bav2pf_")
    try:
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        do_login(k, cluster)
        before = storage(k, cluster)
        k.shutdown()

        k2 = DirectPlaywrightKernel(profile, headless=True)
        k2.start()
        after = storage(k2, cluster)
        k2.shutdown()

        cookie_ok = "bav2_stage=app" in after.get("cookie", "")
        ls_ok = after.get("local", {}).get("bav2_account") == "school"
        return rec(
            PASS if (cookie_ok and ls_ok) else FAIL,
            f"cookie_persisted={cookie_ok} localStorage_persisted={ls_ok}; "
            f"after={after}",
            before=before, after=after,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def c02_authenticated_page_usable_after_restart(cluster) -> dict:
    profile = tempfile.mkdtemp(prefix="bav2pf_")
    try:
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        do_login(k, cluster)
        k.shutdown()

        k2 = DirectPlaywrightKernel(profile, headless=True)
        k2.start()
        k2.navigate(cluster.url("/p/login"))
        obs = k2.observe()
        names = {e.name.strip() for e in obs.elements}
        txt = observed_text(obs)
        k2.shutdown()
        on_dashboard = "Continue" in names and "Sign out" in names
        return rec(PASS if on_dashboard else FAIL,
                   f"authenticated view restored={on_dashboard}; account_text="
                   f"{'account=school' in txt}; controls={sorted(names)[:6]}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def c03_two_restarts_no_drift(cluster) -> dict:
    profile = tempfile.mkdtemp(prefix="bav2pf_")
    try:
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        do_login(k, cluster)
        k.shutdown()
        states = []
        for _ in range(2):
            kk = DirectPlaywrightKernel(profile, headless=True)
            kk.start()
            states.append(storage(kk, cluster).get("local", {}).get("bav2_stage"))
            kk.shutdown()
        return rec(PASS if states == ["app", "app"] else FAIL, f"stages={states}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def c04_profiles_are_isolated(cluster) -> dict:
    """A second agent profile must NOT see the first profile's session."""
    p1 = tempfile.mkdtemp(prefix="bav2pfA_")
    p2 = tempfile.mkdtemp(prefix="bav2pfB_")
    try:
        k = DirectPlaywrightKernel(p1, headless=True)
        k.start()
        do_login(k, cluster)
        k.shutdown()

        k2 = DirectPlaywrightKernel(p2, headless=True)
        k2.start()
        s = storage(k2, cluster)
        k2.shutdown()
        leaked = bool(s.get("local")) or "bav2_stage" in s.get("cookie", "")
        return rec(FAIL if leaked else PASS,
                   f"second profile sees session={leaked}; storage={s}")
    finally:
        shutil.rmtree(p1, ignore_errors=True)
        shutil.rmtree(p2, ignore_errors=True)


def c05_user_chrome_profile_untouched(cluster) -> dict:
    """The agent must never read or write the human's real browser profile."""
    candidates = [
        Path(os.path.expanduser(r"~/AppData/Local/Google/Chrome/User Data")),
        Path(os.path.expanduser(r"~/.config/google-chrome")),
        Path(os.path.expanduser(r"~/Library/Application Support/Google/Chrome")),
    ]
    real = [p for p in candidates if p.exists()]
    profile = tempfile.mkdtemp(prefix="bav2pf_")
    try:
        before = {str(p): _mtime(p) for p in real}
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        do_login(k, cluster)
        k.shutdown()
        after = {str(p): _mtime(p) for p in real}
        changed = [p for p in before if before[p] != after[p]]
        used_dedicated = Path(profile, "Default").exists() or any(
            Path(profile).iterdir()
        )
        return rec(
            PASS if (not changed and used_dedicated) else FAIL,
            f"real chrome profiles found={[str(p) for p in real]}; "
            f"modified_by_run={changed}; dedicated profile populated={used_dedicated}",
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _mtime(p: Path):
    try:
        # Top-level listing only: enough to detect the agent writing into it.
        return sorted((c.name, c.stat().st_mtime) for c in p.iterdir())[:50]
    except Exception:
        return None


def c06_profile_lock_is_exclusive(cluster) -> dict:
    """Two controllers must not silently share one profile."""
    profile = tempfile.mkdtemp(prefix="bav2pf_")
    k = k2 = None
    try:
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        second_started = False
        err = ""
        try:
            k2 = DirectPlaywrightKernel(profile, headless=True)
            k2.start()
            second_started = True
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:160]}"
        # Either outcome is informative; silent sharing is the dangerous one.
        if second_started:
            return rec(
                FAIL,
                "a second controller attached to the same profile without error; "
                "the controller must enforce single ownership itself",
            )
        return rec(PASS, f"second controller refused: {err}")
    finally:
        for kk in (k2, k):
            if kk:
                try:
                    kk.shutdown()
                except Exception:
                    pass
        shutil.rmtree(profile, ignore_errors=True)


CASES = [
    ("PF-01-cookie-and-localstorage-restart", c01_cookie_and_localstorage_survive_restart),
    ("PF-02-authenticated-page-after-restart", c02_authenticated_page_usable_after_restart),
    ("PF-03-two-restarts-no-drift", c03_two_restarts_no_drift),
    ("PF-04-profiles-isolated", c04_profiles_are_isolated),
    ("PF-05-user-chrome-untouched", c05_user_chrome_profile_untouched),
    ("PF-06-profile-lock-exclusive", c06_profile_lock_is_exclusive),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    cluster = FixtureCluster(tempfile.mktemp(suffix=".sqlite")).start()
    rows = []
    try:
        for rep in range(1, args.reps + 1):
            for name, fn in CASES:
                row = {"rep": rep, "case": name}
                try:
                    row.update(fn(cluster))
                except Exception as e:
                    row.update(rec(HARNESS, f"{type(e).__name__}: {e}",
                                   traceback=traceback.format_exc()[-700:]))
                rows.append(row)
                print(f"  rep{rep} {name:42s} {row['status']:14s} "
                      f"{str(row.get('detail',''))[:80]}", flush=True)
    finally:
        cluster.stop()

    by_case = {}
    for n in sorted({r["case"] for r in rows}):
        sub = [r for r in rows if r["case"] == n]
        cc: dict[str, int] = {}
        for r in sub:
            cc[r["status"]] = cc.get(r["status"], 0) + 1
        by_case[n] = cc

    payload = {
        "experiment": "P0_profile_strategy",
        "question": "Does the dedicated persistent profile deliver persistence and isolation?",
        "environment": capture({"experiment": "P0_profile_strategy"}),
        "reps": args.reps,
        "summary": {
            "total_runs": len(rows),
            "counts": _dist(r["status"] for r in rows),
            "failing_cases": sorted({r["case"] for r in rows if r["status"] == FAIL}),
            "by_case": by_case,
        },
        "raw": rows,
    }
    out = RESULTS / "profile_strategy_raw.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))
    print(f"\nraw -> {out}")


def _dist(it):
    d: dict[str, int] = {}
    for v in it:
        d[str(v)] = d.get(str(v), 0) + 1
    return dict(sorted(d.items()))


if __name__ == "__main__":
    main()
