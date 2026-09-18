# Action Verification Contract

## Core conclusion

BrowserAgentV2's Phase 0 runner already contains the correct architectural seed: `execute()` and `verify()` are logically separate, and a successful API call never counts as task success by itself. Production ComputerAgent should preserve this principle but generalize it from a per-experiment callback into a typed verification contract shared by adapters and skills.

Verification is not "ask the model whether that worked." It is evidence collection against explicit predicates.

## Transaction shape

Every state-changing action should follow:

```text
1. resolve target from fresh observation
2. check preconditions + policy
3. persist ACTION_INTENT
4. pre-dispatch freshness/revalidation for consequential actions
5. execute once
6. capture fresh independent evidence
7. evaluate success predicates
8. evaluate prohibited-effect invariants
9. classify outcome/failure
10. persist ACTION_RESULT
11. advance plan only on verified success
```

For reversible, low-risk UI actions some steps can be cheap, but the logical contract remains the same.

## Predicate vocabulary

A small generic predicate set should cover a large fraction of tasks while allowing skill-specific extensions.

### Generic structured predicates

- `exists(target_spec)` / `not_exists(target_spec)`
- `state_equals(target_spec, key, value)`
- `text_equals/contains(target_spec, text)`
- `value_equals(target_spec, value)`
- `selected(target_spec, bool)`
- `enabled(target_spec, bool)`
- `focused(target_spec)`
- `url_matches(pattern)`
- `window_exists(app, title_hint)`
- `window_count_delta(...)`
- `file_exists(path)` / `file_hash_or_size_matches(...)` when task policy permits filesystem verification
- `record_exists(adapter, query)` for structured application/API state
- `count_equals/count_delta(query, n)`

### Visual predicates

Use only when semantic/environment state is unavailable or when visual appearance is itself the goal:

- region contains/does-not-contain expected text/visual state;
- target-region changed as expected;
- dialog/banner disappeared/appeared;
- bounded visual comparator with calibrated uncertainty.

A generic screenshot delta alone is **not** a success predicate: animations, cursors and unrelated notifications can create deltas while the intended state remains unchanged.

### Safety invariants

Each consequential skill may also define `must_remain_true` predicates. Verification succeeds only if desired effects hold **and** prohibited effects are absent. This catches "goal reached by unsafe shortcut" trajectories.

## Evidence-source ordering

Prefer verification evidence in this order when applicable:

1. authoritative app/API/system state independent of action route;
2. fresh semantic state (DOM/CDP/AX/UIA) independent of action return;
3. filesystem/database state when explicitly in scope;
4. OCR/visual state;
5. model judgment as uncertain last resort.

Independence matters. If Playwright click returns success, querying the resulting application state is evidence; re-reading the click return value is not.

## Outcome model

Do not collapse every failure into `False`.

```text
VERIFIED_SUCCESS
VERIFIED_FAILURE        expected state definitely absent/wrong
INCONCLUSIVE            evidence unavailable/ambiguous
STALE_TARGET
PRECONDITION_FAILED
POLICY_BLOCKED
UNSUPPORTED
EXECUTION_ERROR
PARTIAL_SUCCESS
UNEXPECTED_SIDE_EFFECT
```

The recovery policy should depend on this classification. Blindly repeating an action after `INCONCLUSIVE` or `PARTIAL_SUCCESS` can duplicate side effects.

## Retry policy

- `STALE_TARGET` -> fresh observe + re-resolve, then retry within bounded budget.
- `VERIFIED_FAILURE` with reversible/no-op action -> diagnose and consider alternate route.
- `INCONCLUSIVE` after consequential action -> **do not repeat by default**; inspect authoritative state or hand off.
- `PARTIAL_SUCCESS` -> reconcile state and execute only missing sub-effects.
- `UNEXPECTED_SIDE_EFFECT` -> stop/recover/handoff according to risk.
- `EXECUTION_ERROR` -> retry only if error class is known transient and action side effect is known not to have occurred.

## Why this contract is supported by current evidence

### Direct BrowserAgentV2 evidence

`phase0/harness/runner.py` explicitly separates `ActionSpec.execute` and `ActionSpec.verify`; only independently observed postconditions determine success. The macOS app survey then found exactly the failure this design is meant to catch: Chrome AXPress could return success without firing the page action.

### External evidence

- Interactive Reward Agent (July 2026) uses propose-then-verify against post-execution environment state and reports 86.9% accuracy on GUI-RewardBench, outperforming evaluator baselines. Architectural lesson: verification often needs system/app evidence beyond screenshots.
- VeriGUI (April 2026) explicitly models action effects and recovery under noisy UI environments; its premise is that unverified actions accumulate failures.
- VeriSafe Agent (2025) reports strong gains from deterministic logic-based pre-action verification of user-intent alignment, reinforcing deterministic policy checks before dispatch.
- ConflictGUI (September 2026) finds execution-biased overcompliance under infeasible/conflicting instructions and improves behavior with feasibility verification before action. Architectural lesson: `cannot/should-not act` must be a first-class result.
- Tactile (July 2026) separates heterogeneous target evidence, executable affordances and verification cues, supporting verifiable action objects rather than anonymous clicks.

## Fault-injection suite required before production architecture freeze

### F1 — false API success
Executor returns success but fixture performs no mutation. Expected: `VERIFIED_FAILURE`, no plan advance.

### F2 — partial success
Action changes one of two required fields. Expected: `PARTIAL_SUCCESS`; recovery acts only on missing field.

### F3 — stale target
Replace target between observation and dispatch. Expected: pre-dispatch revalidation stops or resolver refreshes before action.

### F4 — wrong duplicate
Two same-label controls; target order changes. Expected: `AMBIGUOUS` or correct relational target; never arbitrary action.

### F5 — verifier unavailable
Structured state read fails after consequential action. Expected: `INCONCLUSIVE`, no blind duplicate retry.

### F6 — unrelated visual change
Notification/animation changes screenshot but action is no-op. Expected: visual delta cannot produce success.

### F7 — unsafe shortcut
Desired goal state is achieved while a prohibited state also changes. Expected: `UNEXPECTED_SIDE_EFFECT`, not success.

### F8 — delayed effect
Mutation becomes visible after bounded latency. Expected: verifier supports bounded polling/backoff before declaring failure, without re-executing action.

## Production interface sketch

```python
@dataclass(frozen=True)
class VerificationSpec:
    preconditions: tuple[Predicate, ...]
    success: tuple[Predicate, ...]
    invariants: tuple[Predicate, ...]
    evidence_preferences: tuple[str, ...]
    timeout_ms: int
    poll_interval_ms: int
    risk: str

@dataclass(frozen=True)
class VerificationResult:
    outcome: VerificationOutcome
    predicate_results: tuple[PredicateResult, ...]
    evidence_refs: tuple[str, ...]
    confidence: float
    retry_safe: bool
    diagnosis: str | None
```

Adapters expose observation/evidence primitives; skills define domain-specific predicates only when generic ones cannot express the task. This avoids building one custom verifier class per application.

## Provisional decision

**DECISION:** Typed predicate verification + independent evidence + explicit inconclusive/partial outcomes; deterministic/app state first, visual/model verification last.

**CONFIDENCE:** 97%

**Risk:** generic predicates may not cover enough real tasks. Measure coverage before expanding the DSL. Do not build a large formal language speculatively.

## Sources

- BrowserAgentV2 `phase0/harness/runner.py` and macOS capability survey (direct evidence).
- Interactive Reward Agent: GUI Task Evaluation via Environment-State Verification, arXiv:2607.25904.
- VeriGUI / Don't Act Blindly: Robust GUI Automation via Action-Effect Verification and Self-Correction, arXiv:2604.05477.
- Safeguarding Mobile GUI Agent via Logic-based Action Verification, arXiv:2503.18492.
- Do GUI Agents Know When Not to Act?, arXiv:2609.03438.
- Tactile: Giving Computer-Using Agents Hands and Feet, arXiv:2607.14443.
