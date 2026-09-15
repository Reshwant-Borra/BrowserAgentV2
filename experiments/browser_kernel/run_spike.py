"""Experiment 1 runner — BrowserKernel adoption spike.

Reproduce:
    cd experiments && npm install
    python -m experiments.browser_kernel.run_spike --passes 3

Each case gets a FRESH kernel instance and a fresh browser profile so no case
can contaminate another. Ground truth comes from the fixture server's effect
log, never from the kernel under test.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.envinfo import capture
from experiments.common.fixture_server import FixtureCluster
from experiments.common.kernel_direct import DirectPlaywrightKernel
from experiments.common.kernel_mcp import MCPKernel, UNSAFE_TOOLS
from experiments.browser_kernel.spike_cases import (
    ALL_CASES, Ctx, PASS, FAIL_SAFE, FAIL_UNSAFE, UNSUPPORTED, HARNESS_ERROR,
)

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


class TimedKernel:
    """Transparent latency recorder around any BrowserKernel."""

    TIMED = {
        "observe", "navigate", "back", "click", "type_text", "select", "press",
        "read_value", "list_pages", "new_tab", "switch_tab", "close_agent_tab",
        "handle_dialog",
    }

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "timings", {})

    def __getattr__(self, item):
        inner = object.__getattribute__(self, "_inner")
        attr = getattr(inner, item)
        if item not in TimedKernel.TIMED or not callable(attr):
            return attr

        def wrapped(*a, **kw):
            t0 = time.perf_counter()
            try:
                return attr(*a, **kw)
            finally:
                dt = (time.perf_counter() - t0) * 1000
                object.__getattribute__(self, "timings").setdefault(item, []).append(dt)

        return wrapped


def make_kernel(which: str, profile_dir: str):
    if which == "direct_playwright":
        return DirectPlaywrightKernel(profile_dir, headless=True)
    if which == "playwright_mcp":
        return MCPKernel(user_data_dir=profile_dir, headless=True, cwd="experiments")
    raise ValueError(which)


def run_candidate(which: str, cluster: FixtureCluster, passes: int, only: str | None):
    rows = []
    all_timings: dict[str, list[float]] = {}
    startup_ms = []
    cases = [(n, f) for n, f in ALL_CASES if not only or only.upper() in n.upper()]

    for p in range(1, passes + 1):
        for name, fn in cases:
            profile = tempfile.mkdtemp(prefix="bav2prof_")
            kernel = None
            t_start = time.perf_counter()
            row = {"candidate": which, "pass": p, "case": name}
            try:
                kernel = TimedKernel(make_kernel(which, profile))
                kernel.start()
                startup_ms.append((time.perf_counter() - t_start) * 1000)
                ctx = Ctx(kernel, cluster)
                t0 = time.perf_counter()
                # Some browser APIs (evaluate behind a modal dialog) have no
                # timeout of their own. Dump a stack instead of stalling silently.
                faulthandler.dump_traceback_later(120, exit=False)
                try:
                    res = fn(ctx)
                finally:
                    faulthandler.cancel_dump_traceback_later()
                row.update(res)
                row["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            except Exception as e:
                row.update(
                    {
                        "status": HARNESS_ERROR,
                        "detail": f"{type(e).__name__}: {e}",
                        "traceback": traceback.format_exc()[-1200:],
                    }
                )
            finally:
                if kernel is not None:
                    for k, v in getattr(kernel, "timings", {}).items():
                        all_timings.setdefault(k, []).extend(v)
                    try:
                        kernel.shutdown()
                    except Exception:
                        pass
                shutil.rmtree(profile, ignore_errors=True)
            rows.append(row)
            print(
                f"  [{which}] pass{p} {name:34s} {row['status']:14s} "
                f"{str(row.get('detail',''))[:96]}",
                flush=True,
            )
    lat = {
        op: {
            "n": len(v),
            "median_ms": round(statistics.median(v), 1),
            "p95_ms": round(sorted(v)[max(0, int(len(v) * 0.95) - 1)], 1),
            "mean_ms": round(statistics.fmean(v), 1),
        }
        for op, v in sorted(all_timings.items())
    }
    if startup_ms:
        lat["_kernel_start"] = {
            "n": len(startup_ms),
            "median_ms": round(statistics.median(startup_ms), 1),
            "p95_ms": round(sorted(startup_ms)[max(0, int(len(startup_ms) * 0.95) - 1)], 1),
            "mean_ms": round(statistics.fmean(startup_ms), 1),
        }
    return rows, lat


def summarize(rows):
    out = {}
    for cand in sorted({r["candidate"] for r in rows}):
        sub = [r for r in rows if r["candidate"] == cand]
        counts = {}
        for r in sub:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        graded = [r for r in sub if r["status"] != HARNESS_ERROR]
        out[cand] = {
            "total_runs": len(sub),
            "counts": counts,
            "pass_rate_excl_harness": round(
                100 * counts.get(PASS, 0) / max(1, len(graded)), 1
            ),
            "unsafe_cases": sorted({r["case"] for r in sub if r["status"] == FAIL_UNSAFE}),
            "unsupported_cases": sorted({r["case"] for r in sub if r["status"] == UNSUPPORTED}),
            "failsafe_cases": sorted({r["case"] for r in sub if r["status"] == FAIL_SAFE}),
            "harness_error_cases": sorted(
                {r["case"] for r in sub if r["status"] == HARNESS_ERROR}
            ),
        }
        # Consistency: a case that does not return the same status on every pass
        # is a non-determinism finding in its own right.
        by_case = {}
        for r in sub:
            by_case.setdefault(r["case"], set()).add(r["status"])
        out[cand]["inconsistent_cases"] = sorted(
            c for c, s in by_case.items() if len(s) > 1
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--candidates", default="direct_playwright,playwright_mcp")
    ap.add_argument("--only", default=None, help="substring filter on case id")
    ap.add_argument("--out", default=str(RESULTS / "experiment1_raw.json"))
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    env = capture({"experiment": "E1_browser_kernel_spike"})
    print(json.dumps({k: env[k] for k in ("playwright", "chromium_version", "playwright_mcp")}, indent=1))

    db = tempfile.mktemp(suffix=".sqlite")
    cluster = FixtureCluster(db).start()
    all_rows, lats = [], {}
    try:
        for cand in args.candidates.split(","):
            cand = cand.strip()
            if not cand:
                continue
            print(f"\n=== candidate: {cand} ===", flush=True)
            rows, lat = run_candidate(cand, cluster, args.passes, args.only)
            all_rows += rows
            lats[cand] = lat
    finally:
        cluster.stop()

    payload = {
        "experiment": "E1_browser_kernel_spike",
        "question": "Which runtime should implement BrowserKernel: Playwright MCP or direct Playwright?",
        "environment": env,
        "passes": args.passes,
        "mcp_unsafe_tools_present_on_server": sorted(UNSAFE_TOOLS),
        "raw": all_rows,
        "latency_ms": lats,
        "summary": summarize(all_rows),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))
    print(f"\nraw results -> {args.out}")


if __name__ == "__main__":
    main()
