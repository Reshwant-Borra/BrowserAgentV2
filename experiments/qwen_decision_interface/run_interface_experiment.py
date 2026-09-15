"""Experiment 2 — which decision interface should BrowserAgentV2 use?

    A. strict structured JSON   (Ollama `format` = JSON Schema)
    B. native Qwen tool calling (Ollama `tools`)

Held identical across both arms: model, quantization, context size, inference
options, seed, hardware, goal text, observation text, policy text, and the
canonical Decision they are both mapped onto. The only difference is the output
mechanism and the minimal paragraph describing it.

Reproduce:
    python -m experiments.qwen_decision_interface.capture_observations
    python -m experiments.qwen_decision_interface.build_dataset
    python -m experiments.qwen_decision_interface.run_interface_experiment --split dev
    python -m experiments.qwen_decision_interface.run_interface_experiment --split eval
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.context_builder import build_user_message, system_prompt
from experiments.common.envinfo import capture, capture_model
from experiments.common.grading import aggregate, grade
from experiments.common.model_adapter import NATIVE_TOOLS, STRICT_JSON, OllamaAdapter

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load(split: str, dataset: Path, obs_file: Path):
    ds = json.loads(dataset.read_text(encoding="utf-8"))
    lib = json.loads(obs_file.read_text(encoding="utf-8"))["observations"]
    cases = [c for c in ds["cases"] if split == "all" or c["split"] == split]
    return ds, lib, cases


def run_arm(adapter: OllamaAdapter, interface: str, cases, lib, reps: int):
    rows, raws = [], []
    sysmsg = system_prompt(interface)
    for rep in range(1, reps + 1):
        for i, c in enumerate(cases, 1):
            o = lib[c["obs_key"]]["observation"]
            user = build_user_message(
                goal=c["goal"],
                subgoal=c["subgoal"],
                obs=o,
                success_criteria=c.get("success_criteria"),
                facts=c.get("facts"),
                previous=c.get("previous"),
            )
            call = adapter.decide(interface, sysmsg, user)
            g = grade(
                call.decision,
                c,
                valid_targets={e["target"] for e in o["elements"]},
                page_url=o.get("url", ""),
            )
            row = {
                "interface": interface,
                "rep": rep,
                "case_id": c["case_id"],
                "family": c["family"],
                "difficulty": c["difficulty"],
                "split": c.get("split"),
                "latency_ms": round(call.latency_ms, 1),
                "prompt_tokens": call.prompt_tokens,
                "completion_tokens": call.completion_tokens,
                "n_tool_calls": call.n_tool_calls,
                "multiple_action_violation": call.n_tool_calls > 1,
                "error": call.error,
                "decision": call.decision.to_json() if call.decision else None,
                **g,
            }
            rows.append(row)
            raws.append(
                {
                    "interface": interface, "rep": rep, "case_id": c["case_id"],
                    "raw_response": call.raw_response, "error": call.error,
                }
            )
            if i % 20 == 0 or i == len(cases):
                print(f"  [{interface}] rep{rep} {i}/{len(cases)}", flush=True)
    return rows, raws


def latency_stats(rows):
    v = sorted(r["latency_ms"] for r in rows)
    if not v:
        return {}
    return {
        "median_ms": round(statistics.median(v), 1),
        "p95_ms": round(v[max(0, int(len(v) * 0.95) - 1)], 1),
        "mean_ms": round(statistics.fmean(v), 1),
        "min_ms": round(v[0], 1),
        "max_ms": round(v[-1], 1),
    }


def token_stats(rows):
    p = [r["prompt_tokens"] for r in rows if r["prompt_tokens"]]
    c = [r["completion_tokens"] for r in rows if r["completion_tokens"]]
    return {
        "prompt_tokens_median": round(statistics.median(p), 1) if p else None,
        "completion_tokens_median": round(statistics.median(c), 1) if c else None,
        "completion_tokens_mean": round(statistics.fmean(c), 1) if c else None,
        "total_prompt_tokens": sum(p),
        "total_completion_tokens": sum(c),
    }


def consistency(rows, reps):
    """Fraction of cases whose decision is byte-identical across repeats."""
    if reps < 2:
        return None
    by_case: dict[str, list] = {}
    for r in rows:
        by_case.setdefault(r["case_id"], []).append(json.dumps(r["decision"], sort_keys=True))
    stable = sum(1 for v in by_case.values() if len(set(v)) == 1 and len(v) == reps)
    complete = sum(1 for v in by_case.values() if len(v) == reps)
    return {
        "n_cases": complete,
        "identical_across_reps_pct": round(100.0 * stable / max(1, complete), 2),
    }


def by_family(rows):
    out = {}
    for fam in sorted({r["family"] for r in rows}):
        out[fam] = aggregate([r for r in rows if r["family"] == fam])
    return out


def by_difficulty(rows):
    return {
        d: aggregate([r for r in rows if r["difficulty"] == d])
        for d in sorted({r["difficulty"] for r in rows})
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="eval", choices=["dev", "eval", "all"])
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--dataset", default=str(HERE / "dataset_v1.json"))
    ap.add_argument("--observations", default=str(HERE / "observations_v1.json"))
    ap.add_argument("--interfaces", default=f"{STRICT_JSON},{NATIVE_TOOLS}")
    ap.add_argument("--tag", default="")
    ap.add_argument("--experiment", default="E2_qwen_decision_interface")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    ds, lib, cases = load(args.split, Path(args.dataset), Path(args.observations))
    print(f"{len(cases)} cases in split={args.split}, reps={args.reps}")

    adapter = OllamaAdapter(
        model=args.model, num_ctx=args.num_ctx, think=args.think, temperature=0.0, seed=7
    )
    t0 = time.time()
    adapter.warmup()
    print(f"warmup {time.time()-t0:.1f}s")

    env = capture({"experiment": args.experiment})
    env["model"] = capture_model(args.model)
    env["inference_options"] = {**adapter.options, "think": adapter.think}

    all_rows, all_raw, summary = [], [], {}
    for iface in args.interfaces.split(","):
        iface = iface.strip()
        print(f"\n=== interface: {iface} ===", flush=True)
        rows, raws = run_arm(adapter, iface, cases, lib, args.reps)
        all_rows += rows
        all_raw += raws
        summary[iface] = {
            "overall": aggregate(rows),
            "latency": latency_stats(rows),
            "tokens": token_stats(rows),
            "consistency": consistency(rows, args.reps),
            "multiple_action_violations": sum(
                1 for r in rows if r["multiple_action_violation"]
            ),
            "by_difficulty": by_difficulty(rows),
            "by_family": by_family(rows),
            "error_kinds": _error_kinds(rows),
        }

    payload = {
        "experiment": args.experiment,
        "split": args.split,
        "reps": args.reps,
        "dataset_version": ds["version"],
        "dataset_sha256": ds["content_sha256"],
        "observations_sha256": ds["observations_sha256"],
        "n_cases": len(cases),
        "environment": env,
        "summary": summary,
        "raw_rows": all_rows,
        "raw_model_outputs": all_raw,
    }
    tag = f"_{args.tag}" if args.tag else ""
    out = RESULTS / f"{args.experiment}_{args.split}{tag}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===")
    for iface, s in summary.items():
        print(f"\n-- {iface}")
        print(json.dumps(s["overall"], indent=1))
        print("latency:", json.dumps(s["latency"]))
        print("tokens:", json.dumps(s["tokens"]))
        print("consistency:", json.dumps(s["consistency"]))
        print("multi-action violations:", s["multiple_action_violations"])
        print("errors:", json.dumps(s["error_kinds"]))
    print(f"\nraw -> {out}")


def _error_kinds(rows):
    kinds: dict[str, int] = {}
    for r in rows:
        if r.get("error"):
            k = str(r["error"]).split(":")[0]
            kinds[k] = kinds.get(k, 0) + 1
    return dict(sorted(kinds.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
