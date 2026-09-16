"""Experiment 4 — observation invalidation.

Question
--------
Can BrowserAgent reliably prevent actions against stale browser state?

Required result: ZERO wrong-target executions. A stale target may safely fail;
it may never silently retarget.

Method
------
Twelve mutation scenarios are applied between observation and action. Each is
run under four candidate invalidation policies. Two of those policies are
deliberately UNSAFE controls (re-resolve by URL only; re-resolve by accessible
name). They are included so the result shows the safe mechanism is *necessary*,
not merely sufficient — a suite in which everything passes proves nothing about
which mechanism did the work.

Ground truth is the fixture server's out-of-band effect log.

Reproduce:
    python -m experiments.observation_invalidation.run_invalidation --reps 12
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.contracts import KernelError, Owner
from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel import InvalidationPolicy
from experiments.common.kernel_direct import DirectPlaywrightKernel

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

WRONG_TARGET = "WRONG_TARGET_EXECUTED"      # fatal
REFUSED = "REFUSED_TYPED"                    # correct
CORRECT = "EXECUTED_CORRECT_NODE"            # correct (target genuinely still valid)
NO_OP = "NO_ERROR_NO_EFFECT"                 # acceptable but noted
HARNESS = "HARNESS_ERROR"


def fx_reset(c):
    urllib.request.urlopen(c.url("/api/pagefx/reset"), timeout=10).read()


def fx(c):
    d = json.loads(urllib.request.urlopen(c.url("/api/pagefx/log"), timeout=10).read())
    return [e["name"] for e in d["entries"] if not e["name"].startswith("VALUE:")]


def find(obs, **kw):
    nth = kw.pop("nth", 0)
    hits = []
    for e in obs.elements:
        if "name" in kw and e.name.strip() != kw["name"]:
            continue
        if "contains" in kw and kw["contains"].lower() not in e.name.lower():
            continue
        if "frame_not" in kw and e.frame_id == kw["frame_not"]:
            continue
        if "role" in kw and e.role != kw["role"]:
            continue
        hits.append(e)
    return hits[nth] if len(hits) > nth else None


# ==========================================================================
# scenarios
#
# Each returns (expected_effect_if_target_were_still_valid, wrong_effects)
# and mutates the page between observation and action.
# ==========================================================================


def _classify(c, err, wrong_effects, right_effects):
    got = fx(c)
    bad = [e for e in got if e in wrong_effects]
    good = [e for e in got if e in right_effects]
    if bad:
        return WRONG_TARGET, f"fired {bad} (error={err})"
    if err:
        return REFUSED, f"{err} (no effect)"
    if good:
        return CORRECT, f"fired {good}"
    return NO_OP, f"no error, no effect; log={got}"


def scn_full_navigation(k, c, page_url="/p/rerender"):
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.navigate(c.url("/p/rerender"))  # same URL: a NEW document, identical content
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"ORIGINAL", "REPLACEMENT"}, set())


def scn_reload_same_url(k, c):
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.page_object().reload(wait_until="domcontentloaded")
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"ORIGINAL", "REPLACEMENT"}, set())


def scn_innerhtml_rerender(k, c):
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.click(find(obs, name="Rerender host").target)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"REPLACEMENT", "ORIGINAL"}, set())


def scn_identical_replacement(k, c):
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.click(find(obs, contains="identical node").target)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"REPLACEMENT", "ORIGINAL"}, set())


def scn_element_removed(k, c):
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.click(find(obs, name="Remove target").target)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"ORIGINAL", "REPLACEMENT"}, set())


def scn_sibling_reorder(k, c):
    """The node is untouched, only its position changes. A position-based
    resolver breaks here; an identity-based one must still succeed."""
    obs = k.observe()
    t = find(obs, name="Confirm").target
    k.click(find(obs, name="Reorder siblings").target)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"REPLACEMENT"}, {"ORIGINAL"})


def scn_spa_route_change(k, c):
    k.navigate(c.url("/p/spa"))
    obs = k.observe()
    t = find(obs, name="Continue").target
    k.click(find(obs, name="Orders").target)  # pushState; whole view replaced
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"Orders", "Home", "Settings"}, set())


def scn_manual_human_action(k, c):
    """A human touches the page outside the kernel. The kernel is not told."""
    obs = k.observe()
    t = find(obs, name="Confirm").target
    page = k.page_object()
    page.evaluate("() => document.getElementById('replace-identical').click()")
    time.sleep(0.2)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"REPLACEMENT", "ORIGINAL"}, set())


def scn_frame_reload(k, c):
    k.navigate(c.url("/p/frames"))
    time.sleep(0.6)
    obs = k.observe()
    el = find(obs, name="Confirm", frame_not=obs.main_frame_id)
    if el is None:
        return HARNESS, "no child-frame target"
    k.click(find(obs, contains="Reload same-origin").target)
    time.sleep(0.6)
    fx_reset(c)
    err = None
    try:
        k.click(el.target)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"CHILD", "TOP", "GRAND"}, set())


def scn_frame_replacement(k, c):
    k.navigate(c.url("/p/frames"))
    time.sleep(0.6)
    obs = k.observe()
    el = find(obs, name="Confirm", frame_not=obs.main_frame_id)
    if el is None:
        return HARNESS, "no child-frame target"
    k.click(find(obs, contains="Detach same-origin").target)
    time.sleep(0.3)
    k.click(find(obs, contains="Reattach identical").target)
    time.sleep(0.7)
    fx_reset(c)
    err = None
    try:
        k.click(el.target)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"CHILD", "TOP", "GRAND"}, set())


def scn_popup_then_old_target(k, c):
    k.navigate(c.url("/p/tabs"))
    obs = k.observe()
    t = find(obs, contains="window.open").target
    k.click(t)
    time.sleep(0.6)
    fx_reset(c)
    # The original page is unchanged, so the old target is legitimately still
    # valid. Over-invalidating here would be a cost, not a safety win.
    err = None
    try:
        k.click(find(obs, name="Same tab navigate").target)
    except KernelError as e:
        err = e.code.value
    got_url = k.page_object().url
    if err:
        return REFUSED, f"{err} (page was not mutated; this is over-invalidation)"
    return CORRECT, f"old target still worked on an unmutated page; url={got_url}"


def scn_tab_close(k, c):
    k.navigate(c.url("/p/rerender"))
    pid = k.new_tab(c.url("/p/rerender"))
    obs = k.observe(pid)
    t = find(obs, name="Confirm").target
    k.close_agent_tab(pid)
    time.sleep(0.3)
    fx_reset(c)
    err = None
    try:
        k.click(t)
    except KernelError as e:
        err = e.code.value
    return _classify(c, err, {"ORIGINAL", "REPLACEMENT"}, set())


def scn_tab_switch(k, c):
    """Switching tabs must not make a target resolve on the wrong page."""
    k.navigate(c.url("/p/rerender"))
    obs_a = k.observe()
    t_a = find(obs_a, name="Confirm").target
    pid = k.new_tab(c.url("/p/rerender"))
    k.switch_tab(pid)
    fx_reset(c)
    err = None
    try:
        k.click(t_a)
    except KernelError as e:
        err = e.code.value
    got = fx(c)
    # The target belongs to page A. Firing is correct ONLY if it fired on page A.
    if not got:
        return (REFUSED, err) if err else (NO_OP, "no effect")
    doc_entries = json.loads(
        urllib.request.urlopen(c.url("/api/pagefx/log"), timeout=10).read()
    )["entries"]
    docs = {e["doc"] for e in doc_entries if not e["name"].startswith("VALUE:")}
    if len(docs) == 1 and obs_a.document_token in docs:
        return CORRECT, "target resolved on its own page despite the active tab change"
    return WRONG_TARGET, f"effect fired in document {docs}, expected {obs_a.document_token}"


def scn_browser_reconnect(k, c, profile=None):
    """Handled by the runner: needs a kernel restart."""
    return HARNESS, "handled out of band"


SCENARIOS = [
    ("full-navigation-same-url", scn_full_navigation, "/p/rerender"),
    ("reload-same-url", scn_reload_same_url, "/p/rerender"),
    ("innerhtml-rerender", scn_innerhtml_rerender, "/p/rerender"),
    ("identical-node-replacement", scn_identical_replacement, "/p/rerender"),
    ("element-removed", scn_element_removed, "/p/rerender"),
    ("sibling-reorder-node-intact", scn_sibling_reorder, "/p/rerender"),
    ("spa-route-change", scn_spa_route_change, "/p/spa"),
    ("manual-human-interaction", scn_manual_human_action, "/p/rerender"),
    ("frame-reload", scn_frame_reload, "/p/frames"),
    ("frame-replacement", scn_frame_replacement, "/p/frames"),
    ("popup-opened-page-unchanged", scn_popup_then_old_target, "/p/tabs"),
    ("owning-tab-closed", scn_tab_close, "/p/rerender"),
    ("active-tab-switched", scn_tab_switch, "/p/rerender"),
]


def run_reconnect_case(cluster, policy) -> tuple[str, str]:
    """Kernel restart against the same persistent profile."""
    profile = tempfile.mkdtemp(prefix="bav2inv_")
    try:
        k = DirectPlaywrightKernel(profile, headless=True, policy=policy)
        k.start()
        k.navigate(cluster.url("/p/rerender"))
        obs = k.observe()
        t = find(obs, name="Confirm").target
        k.shutdown()

        k2 = DirectPlaywrightKernel(profile, headless=True, policy=policy)
        k2.start()
        k2.navigate(cluster.url("/p/rerender"))
        fx_reset(cluster)
        err = None
        try:
            k2.click(t)
        except KernelError as e:
            err = e.code.value
        except Exception as e:
            err = type(e).__name__
        res = _classify(cluster, err, {"ORIGINAL", "REPLACEMENT"}, set())
        k2.shutdown()
        return res
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument(
        "--policies",
        default=",".join(p.value for p in InvalidationPolicy),
    )
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    cluster = FixtureCluster(tempfile.mktemp(suffix=".sqlite")).start()
    rows = []
    try:
        for pol_name in args.policies.split(","):
            pol = InvalidationPolicy(pol_name.strip())
            print(f"\n=== policy: {pol.value} ===", flush=True)
            for rep in range(1, args.reps + 1):
                for name, fn, path in SCENARIOS:
                    profile = tempfile.mkdtemp(prefix="bav2inv_")
                    k = None
                    row = {"policy": pol.value, "rep": rep, "scenario": name}
                    try:
                        k = DirectPlaywrightKernel(profile, headless=True, policy=pol)
                        k.start()
                        k.navigate(cluster.url(path))
                        fx_reset(cluster)
                        status, detail = (
                            fn(k, cluster, path) if fn is scn_full_navigation
                            else fn(k, cluster)
                        )
                        row.update({"status": status, "detail": detail})
                    except Exception as e:
                        row.update(
                            {"status": HARNESS, "detail": f"{type(e).__name__}: {e}",
                             "traceback": traceback.format_exc()[-800:]}
                        )
                    finally:
                        if k:
                            try:
                                k.shutdown()
                            except Exception:
                                pass
                        shutil.rmtree(profile, ignore_errors=True)
                    rows.append(row)
                # reconnect scenario (needs its own lifecycle)
                try:
                    st, det = run_reconnect_case(cluster, pol)
                except Exception as e:
                    st, det = HARNESS, f"{type(e).__name__}: {e}"
                rows.append(
                    {"policy": pol.value, "rep": rep,
                     "scenario": "kernel-restart-reconnect", "status": st, "detail": det}
                )
                print(f"  rep {rep}/{args.reps} done", flush=True)
    finally:
        cluster.stop()

    summary = {}
    for pol in sorted({r["policy"] for r in rows}):
        sub = [r for r in rows if r["policy"] == pol]
        counts: dict[str, int] = {}
        for r in sub:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        wrong = [r for r in sub if r["status"] == WRONG_TARGET]
        summary[pol] = {
            "runs": len(sub),
            "counts": counts,
            "wrong_target_executions": len(wrong),
            "wrong_target_scenarios": sorted({r["scenario"] for r in wrong}),
            "harness_errors": sorted(
                {r["scenario"] for r in sub if r["status"] == HARNESS}
            ),
            "over_invalidated_scenarios": sorted(
                {r["scenario"] for r in sub
                 if r["status"] == REFUSED and r["scenario"] in
                 ("sibling-reorder-node-intact", "popup-opened-page-unchanged")}
            ),
        }

    payload = {
        "experiment": "E4_observation_invalidation",
        "question": "Can the kernel prevent actions against stale browser state?",
        "invariant": "zero wrong-target executions; stale targets may fail, never retarget",
        "environment": capture({"experiment": "E4_observation_invalidation"}),
        "reps": args.reps,
        "scenarios": [s[0] for s in SCENARIOS] + ["kernel-restart-reconnect"],
        "summary": summary,
        "raw": rows,
    }
    out = RESULTS / "experiment4_raw.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nraw -> {out}")


if __name__ == "__main__":
    main()
