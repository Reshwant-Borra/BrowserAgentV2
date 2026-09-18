"""M2 adversarial campaign: Fixture B deceptive executions judged by
`computer_agent.verification.verify`, graded by an independent oracle.

Trial flow (mirrors the production order): independent pre-dispatch
observation -> (possibly lying) executor runs -> verifier polls the
independent observation channel. The executor's claim is recorded for
reporting only; it is never passed to the verifier.

Oracle independence: `_oracle_expected` is a second, separately written
implementation of each intent's intended effect, applied to the *unmasked*
true pre-dispatch state. A verdict of VERIFIED_SUCCESS is a **false
success** unless the true state at the verifier's last observation equals
exactly that expected state (intended effect present, applied once, and
nothing else changed). The oracle never calls `verification.py` or the
fixture's own `apply_intent`/`SPEC_BUILDERS`.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from computer_agent.verification import VerificationOutcome, verify

from .fixtures.fixture_b import CASE_NAMES, MAX_OBSERVATIONS, build_case, spec_for

O = VerificationOutcome


def _oracle_expected(before: dict, intent: dict) -> dict:
    state = copy.deepcopy(before)
    kind = intent["kind"]
    if kind == "update_fields":
        for f, v in intent["fields"].items():
            state["records"][intent["record"]][f] = v
    elif kind == "increment":
        state["records"][intent["record"]][intent["field"]] = (
            before["records"][intent["record"]][intent["field"]] + intent["by"]
        )
    elif kind == "create_record":
        state["records"][intent["key"]] = copy.deepcopy(intent["fields"])
    elif kind == "send_message":
        state["outbox"] = [*before["outbox"], copy.deepcopy(intent["message"])]
    return state


@dataclass
class M2Trial:
    case: str
    seed: int
    behavior: str
    intent: dict
    executor_claim_ok: bool
    executor_claim_message: str
    verdict: str
    reason: str
    observations_used: int
    history: list[str]
    truly_established: bool
    false_success: bool
    false_failure: bool
    executor_lied: bool


def run_trial(case: str, seed: int, capture: dict | None = None) -> M2Trial:
    setup = build_case(case, seed)
    svc = setup.service
    spec = spec_for(setup.intent)

    before_obs = svc.observe()  # independent pre-dispatch observation
    truth_before = copy.deepcopy(svc.truth_at_tick[svc.tick])
    claim = setup.run_behavior()
    result, observations = verify(spec, before_obs, svc.observe, max_observations=MAX_OBSERVATIONS)

    truth_final = svc.truth_at_tick[svc.tick]  # true state at the verifier's last observation
    established = truth_final == _oracle_expected(truth_before, setup.intent)
    verdict = result.outcome

    if capture is not None:
        capture.update(spec=spec, before=before_obs, observations=observations, result=result,
                       truth_before=truth_before, truth_final=truth_final, claim=claim)

    return M2Trial(
        case=case, seed=seed, behavior=setup.behavior, intent=setup.intent,
        executor_claim_ok=claim.ok, executor_claim_message=claim.message,
        verdict=verdict.value, reason=result.reason, observations_used=result.observations_used,
        history=[h.value for h in result.history],
        truly_established=established,
        false_success=verdict == O.VERIFIED_SUCCESS and not established,
        false_failure=verdict == O.VERIFIED_FAILURE and established,
        executor_lied=claim.ok != established,
    )


@dataclass
class M2Report:
    total_trials: int
    by_verdict: dict[str, int]
    by_case_verdict: dict[str, dict[str, int]]
    false_success_seeds: list[tuple[str, int]]
    false_failure_seeds: list[tuple[str, int]]
    executor_lies: int
    executor_lies_caught: int  # lie present and verdict was not VERIFIED_SUCCESS-when-false
    truly_established: int
    verified_success_when_established: int
    by_behavior_verdict: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def false_success_count(self) -> int:
        return len(self.false_success_seeds)


def run_campaign(n: int, base_seed: int = 0, evidence_dir: Path | None = None) -> M2Report:
    by_verdict: Counter = Counter()
    by_case: dict[str, Counter] = {c: Counter() for c in CASE_NAMES}
    by_behavior: dict[str, Counter] = {}
    fs, ff = [], []
    lies = caught = established = success_when_established = 0
    fh = None
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        fh = (evidence_dir / f"m2_campaign-seed{base_seed}-n{n}.jsonl").open("w")
    try:
        for i in range(n):
            case, seed = CASE_NAMES[i % len(CASE_NAMES)], base_seed + i
            t = run_trial(case, seed)
            by_verdict[t.verdict] += 1
            by_case[case][t.verdict] += 1
            by_behavior.setdefault(t.behavior, Counter())[t.verdict] += 1
            if t.false_success:
                fs.append((case, seed))
            if t.false_failure:
                ff.append((case, seed))
            if t.executor_lied:
                lies += 1
                caught += not t.false_success
            established += t.truly_established
            success_when_established += t.truly_established and t.verdict == O.VERIFIED_SUCCESS.value
            if fh:
                fh.write(json.dumps(asdict(t)) + "\n")
    finally:
        if fh:
            fh.close()
    report = M2Report(
        total_trials=n, by_verdict=dict(by_verdict), by_case_verdict={k: dict(v) for k, v in by_case.items()},
        false_success_seeds=fs, false_failure_seeds=ff, executor_lies=lies, executor_lies_caught=caught,
        truly_established=established, verified_success_when_established=success_when_established,
        by_behavior_verdict={k: dict(v) for k, v in by_behavior.items()},
    )
    if evidence_dir is not None:
        (evidence_dir / f"m2_campaign-seed{base_seed}-n{n}-summary.json").write_text(
            json.dumps(asdict(report), indent=2))
    return report


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run the M2 verification campaign")
    ap.add_argument("-n", type=int, default=2200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--evidence", type=Path, default=Path("computer_agent/results"))
    args = ap.parse_args()
    r = run_campaign(args.n, args.seed, args.evidence)
    print(json.dumps({"trials": r.total_trials, "by_verdict": r.by_verdict,
                      "false_success": r.false_success_count, "false_failure": len(r.false_failure_seeds),
                      "executor_lies": r.executor_lies, "lies_caught": r.executor_lies_caught}, indent=2))
