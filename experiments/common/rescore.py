"""Re-grade a stored results file without calling the model again.

Every run preserves the model's decision for every case, so a change to the
metric definitions can be applied to results that already exist. That keeps the
scoring honest in both directions: metrics can be corrected after the fact, and
nobody has to re-run a model to benefit from the correction.

Usage:
    python -m experiments.common.rescore <results.json> [<results.json> ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.common.contracts import Decision
from experiments.common.grading import aggregate, grade


def rescore_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ds_path = _dataset_for(payload, path)
    obs_path = _observations_for(payload, path)
    cases = {c["case_id"]: c for c in json.loads(ds_path.read_text(encoding="utf-8"))["cases"]}
    lib = json.loads(obs_path.read_text(encoding="utf-8"))["observations"]

    for row in payload["raw_rows"]:
        c = cases.get(row["case_id"])
        if c is None:
            continue
        o = lib[c["obs_key"]]["observation"]
        d = row.get("decision")
        dec = Decision(**{k: v for k, v in d.items()}) if d else None
        row.update(
            grade(dec, c, {e["target"] for e in o["elements"]}, o.get("url", ""))
        )

    for iface in payload["summary"]:
        rows = [r for r in payload["raw_rows"] if r["interface"] == iface]
        payload["summary"][iface]["overall"] = aggregate(rows)
        payload["summary"][iface]["by_difficulty"] = {
            d: aggregate([r for r in rows if r["difficulty"] == d])
            for d in sorted({r["difficulty"] for r in rows})
        }
        payload["summary"][iface]["by_family"] = {
            f: aggregate([r for r in rows if r["family"] == f])
            for f in sorted({r["family"] for r in rows})
        }
    payload["rescored"] = True
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _dataset_for(payload, path):
    exp = Path(__file__).resolve().parents[1]
    if payload.get("dataset_version") == "adequacy_v1":
        return exp / "qwen_adequacy" / "adequacy_v1.json"
    return exp / "qwen_decision_interface" / "dataset_v1.json"


def _observations_for(payload, path):
    exp = Path(__file__).resolve().parents[1]
    if payload.get("dataset_version") == "adequacy_v1":
        return exp / "qwen_adequacy" / "adequacy_observations_v1.json"
    return exp / "qwen_decision_interface" / "observations_v1.json"


if __name__ == "__main__":
    for p in sys.argv[1:]:
        payload = rescore_file(Path(p))
        name = Path(p).name
        for iface, s in payload["summary"].items():
            o = s["overall"]
            print(
                f"{name:62s} {iface:13s} "
                f"end_to_end={o['end_to_end_usable_decision_pct']:6.2f}%  "
                f"schema={o['schema_valid_pct']:6.2f}%  "
                f"target={o['target_accuracy_pct']}  "
                f"halluc={o['n_hallucinated_target']}  "
                f"forbidden={o['n_forbidden_hit']}"
            )
