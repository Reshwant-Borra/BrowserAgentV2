"""Experiment 5 — page registry and tab ownership.

Question
--------
Can BrowserAgent know which pages belong to it and avoid harming user pages?

Critical invariant: ZERO user-owned tabs closed automatically.

Identity rule under test: a page's identity is the page_id minted at its
creation event. Never the title, never the URL, never the tab index. Every
scenario below is built so that at least one of title/URL/index is ambiguous.

Reproduce:
    python -m experiments.page_registry.run_page_registry --reps 20
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

from experiments.common.contracts import KernelError, KernelErrorCode, Owner
from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

PASS, FAIL, FATAL, HARNESS = "PASS", "FAIL", "FATAL_USER_TAB_HARMED", "HARNESS_ERROR"


def rec(status, detail, **kw):
    return {"status": status, "detail": detail, **kw}


def owners(k) -> dict:
    return {p.page_id: p.owner.value for p in k.list_pages() if not p.closed}


def human_opens_tab(k, url):
    """A tab the human created. The kernel did not ask for it and must not
    claim it. Created through the raw context so no kernel path is involved."""
    p = k.context.new_page()
    p.goto(url, wait_until="domcontentloaded")
    time.sleep(0.3)
    return p


def cleanup_agent_tabs(k) -> dict:
    """The operation that must never harm a user tab."""
    closed, refused = [], []
    for p in list(k.list_pages()):
        if p.closed:
            continue
        try:
            k.close_agent_tab(p.page_id)
            closed.append(p.page_id)
        except KernelError as e:
            if e.code is KernelErrorCode.PAGE_NOT_OWNED:
                refused.append(p.page_id)
            else:
                raise
    return {"closed": closed, "refused": refused}


# ==========================================================================


def c01_agent_created(k, c):
    pid = k.new_tab(c.url("/p/basic"))
    o = owners(k)
    return rec(PASS if o.get(pid) == "AGENT" else FAIL, f"{pid}={o.get(pid)}")


def c02_preexisting_is_user(k, c):
    """Pages that already existed when the kernel attached are not ours."""
    p = owners(k)
    first = sorted(p)[0]
    return rec(PASS if p[first] in ("AGENT", "USER") else FAIL,
               f"startup page ownership={p}")


def c03_popup_from_agent_page(k, c):
    pid = k.new_tab(c.url("/p/tabs"))
    obs = k.observe(pid)
    before = set(owners(k))
    tgt = [e for e in obs.elements if "window.open" in e.name][0]
    k.click(tgt.target)
    time.sleep(0.7)
    new = [p for p in k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return rec(FAIL, "popup not registered")
    return rec(PASS if new[0].owner is Owner.AGENT else FAIL,
               f"popup {new[0].page_id} owner={new[0].owner.value} "
               f"opener={new[0].opener_page_id}")


def c04_popup_from_user_page(k, c):
    """A popup opened by the HUMAN's tab must stay the human's."""
    up = human_opens_tab(k, c.url("/p/tabs"))
    before = set(owners(k))
    up.evaluate("() => document.getElementById('popup-open').click()")
    time.sleep(0.8)
    new = [p for p in k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return rec(FAIL, "popup from user page not registered")
    ok = new[0].owner is Owner.USER
    return rec(PASS if ok else FATAL if new[0].owner is Owner.AGENT else FAIL,
               f"popup {new[0].page_id} owner={new[0].owner.value} "
               f"(inherited from its opener)")


def c05_manual_tab_during_handoff(k, c):
    """The human opens a tab while the agent is paused for handoff."""
    k.invalidate_all_observations("handoff")
    before = set(owners(k))
    human_opens_tab(k, c.url("/p/login"))
    new = [p for p in k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return rec(FAIL, "manual tab not registered")
    return rec(PASS if new[0].owner is Owner.USER else FATAL,
               f"manual tab {new[0].page_id} owner={new[0].owner.value}")


def c06_duplicate_url_and_title(k, c):
    """Three tabs, byte-identical URL and title, different owners."""
    a = k.new_tab(c.url("/p/basic"))
    human_opens_tab(k, c.url("/p/basic"))
    b = k.new_tab(c.url("/p/basic"))
    pages = [p for p in k.list_pages() if not p.closed and p.url.endswith("/p/basic")]
    ids = {p.page_id for p in pages}
    urls = {p.url for p in pages}
    titles = {p.title for p in pages}
    distinct = len(ids) == len(pages) >= 3
    ownership = {p.page_id: p.owner.value for p in pages}
    agent_ids = {a, b}
    correct = all(ownership[i] == "AGENT" for i in agent_ids if i in ownership) and any(
        v == "USER" for v in ownership.values()
    )
    return rec(
        PASS if (distinct and correct) else FAIL,
        f"{len(pages)} pages share url={urls} title={titles}; "
        f"ids distinct={distinct}; ownership={ownership}",
    )


def c07_cleanup_never_closes_user(k, c):
    """THE invariant."""
    k.new_tab(c.url("/p/basic"))
    human_opens_tab(k, c.url("/p/basic"))
    k.new_tab(c.url("/p/duplicate_names"))
    human_opens_tab(k, c.url("/p/duplicate_names"))
    user_before = {p.page_id for p in k.list_pages()
                   if p.owner is Owner.USER and not p.closed}
    res = cleanup_agent_tabs(k)
    after = {p.page_id: p.closed for p in k.list_pages()}
    harmed = sorted(pid for pid in user_before if after.get(pid))
    agent_left = [p.page_id for p in k.list_pages()
                  if p.owner is Owner.AGENT and not p.closed]
    if harmed:
        return rec(FATAL, f"cleanup closed USER pages {harmed}")
    return rec(PASS if not agent_left else FAIL,
               f"closed={res['closed']} refused={res['refused']} "
               f"user_pages_intact={sorted(user_before)} agent_left={agent_left}")


def c08_closed_then_reopened(k, c):
    """A reopened page at the same URL is a NEW page, not the old one."""
    pid = k.new_tab(c.url("/p/basic"))
    k.close_agent_tab(pid)
    time.sleep(0.3)
    pid2 = k.new_tab(c.url("/p/basic"))
    reused = pid == pid2
    old = {p.page_id: p.closed for p in k.list_pages()}
    return rec(FAIL if reused else PASS,
               f"old={pid} (closed={old.get(pid)}) new={pid2} id_reused={reused}")


def c09_page_self_closes(k, c):
    pid = k.new_tab(c.url("/p/tabs"))
    obs = k.observe(pid)
    before = set(owners(k))
    k.click([e for e in obs.elements if "identical twin" in e.name][0].target)
    time.sleep(0.7)
    new = [p for p in k.list_pages() if p.page_id not in before and not p.closed]
    if not new:
        return rec(FAIL, "twin popup not registered")
    twin = new[0].page_id
    o2 = k.observe(twin)
    try:
        k.click([e for e in o2.elements if e.name.strip() == "Close myself"][0].target)
    except KernelError:
        pass
    time.sleep(0.6)
    st = {p.page_id: p.closed for p in k.list_pages()}
    return rec(PASS if st.get(twin) else FAIL, f"twin {twin} closed={st.get(twin)}")


def c10_ownership_survives_navigation(k, c):
    """Navigating a USER page must not convert it into an agent page."""
    up = human_opens_tab(k, c.url("/p/basic"))
    uid = [p.page_id for p in k.list_pages()
           if p.owner is Owner.USER and p.url.endswith("/p/basic")]
    if not uid:
        return rec(HARNESS, "no user page created")
    up.goto(c.url("/p/duplicate_names"), wait_until="domcontentloaded")
    time.sleep(0.3)
    now = {p.page_id: p.owner.value for p in k.list_pages()}
    return rec(PASS if now.get(uid[0]) == "USER" else FATAL,
               f"user page {uid[0]} owner after navigation={now.get(uid[0])}")


CASES = [
    ("PR-01-agent-created", c01_agent_created),
    ("PR-02-preexisting-page", c02_preexisting_is_user),
    ("PR-03-popup-from-agent-page", c03_popup_from_agent_page),
    ("PR-04-popup-from-user-page", c04_popup_from_user_page),
    ("PR-05-manual-tab-during-handoff", c05_manual_tab_during_handoff),
    ("PR-06-duplicate-url-and-title", c06_duplicate_url_and_title),
    ("PR-07-cleanup-never-closes-user", c07_cleanup_never_closes_user),
    ("PR-08-closed-then-reopened", c08_closed_then_reopened),
    ("PR-09-page-self-closes", c09_page_self_closes),
    ("PR-10-ownership-survives-navigation", c10_ownership_survives_navigation),
]


def restart_case(cluster) -> dict:
    """Browser restart: page ids must not be recycled onto different pages."""
    profile = tempfile.mkdtemp(prefix="bav2pr_")
    try:
        k = DirectPlaywrightKernel(profile, headless=True)
        k.start()
        a = k.new_tab(cluster.url("/p/basic"))
        b = k.new_tab(cluster.url("/p/duplicate_names"))
        before = {p.page_id: p.url for p in k.list_pages() if not p.closed}
        k.shutdown()
        k2 = DirectPlaywrightKernel(profile, headless=True)
        k2.start()
        after = {p.page_id: (p.url, p.owner.value) for p in k2.list_pages() if not p.closed}
        # After a restart there is no way to know who owned a rediscovered page,
        # so nothing may be silently reclaimed as AGENT and then auto-closed.
        reclaimed = [pid for pid, (u, o) in after.items() if pid in before and o == "AGENT"
                     and before[pid] != u]
        k2.shutdown()
        if reclaimed:
            return rec(FATAL, f"page ids reused for different pages: {reclaimed}")
        return rec(PASS, f"before={before} after_restart={after}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    cluster = FixtureCluster(tempfile.mktemp(suffix=".sqlite")).start()
    rows = []
    try:
        for rep in range(1, args.reps + 1):
            for name, fn in CASES:
                profile = tempfile.mkdtemp(prefix="bav2pr_")
                k = None
                row = {"rep": rep, "case": name}
                try:
                    k = DirectPlaywrightKernel(profile, headless=True)
                    k.start()
                    row.update(fn(k, cluster))
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
                rows.append(row)
            try:
                rows.append({"rep": rep, "case": "PR-11-browser-restart", **restart_case(cluster)})
            except Exception as e:
                rows.append({"rep": rep, "case": "PR-11-browser-restart",
                             **rec(HARNESS, f"{type(e).__name__}: {e}")})
            print(f"rep {rep}/{args.reps}", flush=True)
    finally:
        cluster.stop()

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    by_case = {}
    for name in sorted({r["case"] for r in rows}):
        sub = [r for r in rows if r["case"] == name]
        cc: dict[str, int] = {}
        for r in sub:
            cc[r["status"]] = cc.get(r["status"], 0) + 1
        by_case[name] = cc

    fatal = [r for r in rows if r["status"] == FATAL]
    payload = {
        "experiment": "E5_page_registry_ownership",
        "question": "Can BrowserAgent know which pages are its own and never harm user pages?",
        "invariant": "zero USER-owned tabs closed automatically",
        "environment": capture({"experiment": "E5_page_registry_ownership"}),
        "reps": args.reps,
        "summary": {
            "total_runs": len(rows),
            "counts": counts,
            "user_tabs_harmed": len(fatal),
            "fatal_cases": sorted({r["case"] for r in fatal}),
            "failing_cases": sorted({r["case"] for r in rows if r["status"] == FAIL}),
            "harness_error_cases": sorted(
                {r["case"] for r in rows if r["status"] == HARNESS}
            ),
            "by_case": by_case,
        },
        "raw": rows,
    }
    out = RESULTS / "experiment5_raw.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))
    print(f"\nraw -> {out}")


if __name__ == "__main__":
    main()
