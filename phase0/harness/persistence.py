"""Persistence and aggregation for experiment results.

Results are written as JSON Lines (one `ExperimentObservation` per line)
so runs of hundreds of trials can be appended and streamed without
loading everything into memory. Aggregation never drops failed/error
trials from the denominator.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Iterable, Iterator, List

from phase0.schemas.evidence import ExperimentObservation, InterferenceClassification, SchemaValidationError


class ResultWriter:
    """Appends `ExperimentObservation`s to a JSONL file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, observation: ExperimentObservation) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(observation.to_dict(), sort_keys=True))
            f.write("\n")


def read_results(path: Path) -> Iterator[ExperimentObservation]:
    """Reads a JSONL results file, raising `SchemaValidationError` on the
    first malformed line (fail loudly rather than silently skip)."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SchemaValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            yield ExperimentObservation.from_dict(raw)


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def summarize(observations: Iterable[ExperimentObservation]) -> dict:
    """Compact aggregate summary. Includes every trial passed in,
    including failed/error trials."""
    observations = list(observations)
    trials = len(observations)

    classification_counts = {c.value: 0 for c in InterferenceClassification}
    for obs in observations:
        classification_counts[obs.classification.value] += 1

    successful_actions = sum(1 for o in observations if o.action_outcome.value == "success")
    verified_postconditions = sum(1 for o in observations if o.postcondition_success is True)
    errors = sum(1 for o in observations if o.action_outcome.value == "error")

    latencies = sorted(o.action_latency_ms for o in observations if o.action_latency_ms is not None)

    def rate(count: int) -> float:
        return (count / trials) if trials else 0.0

    return {
        "trials": trials,
        "successful_actions": successful_actions,
        "verified_postconditions": verified_postconditions,
        "error_count": errors,
        "classification_counts": classification_counts,
        "cursor_interference_count": classification_counts[InterferenceClassification.CURSOR_INTERFERENCE.value],
        "cursor_interference_rate": rate(classification_counts[InterferenceClassification.CURSOR_INTERFERENCE.value]),
        "foreground_interference_count": classification_counts[InterferenceClassification.FOREGROUND_INTERFERENCE.value],
        "foreground_interference_rate": rate(
            classification_counts[InterferenceClassification.FOREGROUND_INTERFERENCE.value]
        ),
        "focus_interference_count": classification_counts[InterferenceClassification.FOCUS_INTERFERENCE.value],
        "focus_interference_rate": rate(classification_counts[InterferenceClassification.FOCUS_INTERFERENCE.value]),
        "multiple_interference_count": classification_counts[InterferenceClassification.MULTIPLE_INTERFERENCE.value],
        "background_safe_count": classification_counts[InterferenceClassification.BACKGROUND_SAFE.value],
        "background_safe_rate": rate(classification_counts[InterferenceClassification.BACKGROUND_SAFE.value]),
        "inconclusive_count": classification_counts[InterferenceClassification.INCONCLUSIVE.value],
        "unsupported_count": classification_counts[InterferenceClassification.UNSUPPORTED.value],
        "latency_ms": {
            "median": statistics.median(latencies) if latencies else None,
            "p95": _percentile(latencies, 0.95) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "n": len(latencies),
        },
    }


def write_summary(summary: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
