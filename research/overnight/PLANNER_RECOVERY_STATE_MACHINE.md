# Planner and Recovery State Machine

## Decision
Use **one durable controller state machine**, not separate autonomous planner/executor/recovery agents. Models propose plans, targets, arguments and replans; deterministic controller code owns lifecycle, retry budgets, policy checks, route switching, verification, persistence and handoff.

## Minimal durable lifecycle
`READY -> RESOLVING -> ELIGIBILITY_CHECK -> INTENT_PERSISTED -> DISPATCHING -> OBSERVING -> VERIFYING -> COMMITTED`

Exceptional states:
`STALE_TARGET`, `AMBIGUOUS_TARGET`, `ACTION_FAILED`, `VERIFY_INCONCLUSIVE`, `OUTCOME_UNKNOWN`, `POLICY_BLOCKED`, `REPLAN_REQUIRED`, `NEEDS_REVIEW`, `CANCELLED`.

A crash is not a special model event. On restart, controller reconstructs state from checkpoint + journal and runs deterministic reconciliation based on the last durable lifecycle state.

## Control policy
### Retry same route
Only when failure is classified transient, action is safe to repeat/reconcile, target is still fresh, and retry budget remains. Never repeat simply because the model says 'try again'.

### Re-ground
Use when target is stale, missing, ambiguous after mutation, or observation changed enough to invalidate the execution reference. Re-resolve from the durable TargetSpec against a fresh observation.

### Switch route
Use when current route is capability-missing or behaviorally broken but another approved route can satisfy the same semantic action and verifier. Route switching does not change task intent or verification contract.

### Replan
Trigger when a verified precondition becomes false, expected environment structure changes materially, a required capability is unavailable, repeated classified failures exhaust local recovery, or the current plan can no longer establish the goal. Replanning creates a new `plan_version`; it never edits history.

### Handoff / stop
Required for ambiguous irreversible side effects, policy denial that needs authority expansion, repeated verifier inconclusiveness on consequential effects, safety-invariant conflict, or exhausted recovery budget.

## Failure taxonomy
1. `GROUNDING_STALE` — prior execution reference invalidated.
2. `GROUNDING_AMBIGUOUS` — multiple candidates without safe discriminator.
3. `CAPABILITY_UNAVAILABLE` — route cannot perform requested semantic action.
4. `DISPATCH_REJECTED` — adapter/tool refused before known effect.
5. `DISPATCH_TRANSIENT` — retryable infrastructure error with no effect evidence.
6. `POSTCONDITION_FALSE` — action ran but intended effect absent.
7. `VERIFY_INCONCLUSIVE` — insufficient evidence to classify effect.
8. `UNEXPECTED_SIDE_EFFECT` — invariant violation or unrelated consequential mutation.
9. `EXTERNAL_STATE_DRIFT` — environment changed outside agent control.
10. `POLICY_BLOCKED` — action exceeds capability/policy.
11. `OUTCOME_UNKNOWN` — crash/timeout leaves non-idempotent effect unresolved.
12. `MODEL_INVALID` — schema/constraint failure from model proposal.

Failure classes map to controller transitions; do not expose free-form model retry loops.

## Retry budgets
Budgets are hierarchical and deterministic: per action, per route, per step, and task-wide. The controller should favor information-gaining recovery over identical repetition. Suggested initial policy for measurement, not a permanent constant:
- same exact action/route: at most one automatic retry after a classified transient failure
- re-ground then retry: one attempt
- alternate approved route: one attempt
- then replan or handoff depending on risk

Low-risk/read-only actions can use larger budgets; irreversible/high-impact actions can have zero blind retries.

## Replanning contract
Planner input is a bounded state projection: goal, active plan version, verified completed steps, current step, current observation, relevant facts, classified failure, attempted recoveries, capabilities/policy, and invariants. Planner output is structured and schema-validated. It may propose a new suffix/plan but cannot mark previous actions successful, alter journal history, widen capabilities, or waive verification.

## Recovery after crash
- Before durable intent: no action is assumed dispatched; regenerate proposal if needed.
- Intent persisted, no dispatch evidence: reconcile adapter/tool state if possible; otherwise use action-class policy.
- Dispatch may have occurred: reconcile external state before retry.
- Observation persisted, verification incomplete: run verifier first; do not repeat action.
- Verified result persisted, plan commit missing: deterministically commit/advance from persisted evidence.
- Outcome unknown for irreversible non-idempotent effect: `NEEDS_REVIEW`.

## Why one controller
A multi-agent planner/executor/recovery hierarchy adds context handoffs, conflicting authority and failure attribution without solving durability. The durable state machine already provides specialization boundaries. Specialist models can still be invoked behind narrow proposal interfaces if benchmarks justify them.

## Metrics
- false-success rate
- duplicate-side-effect rate
- recovery success by failure class
- retries per successful action
- route switches per successful task
- unnecessary replans
- handoff precision/recall on injected ambiguity
- time/tokens from failure to recovery
- state-machine invariant violations (target zero)

## State-machine invariants
- plan never advances without verified success
- no action dispatch without persisted intent and policy eligibility
- no stale ExecutionRef survives observation-invalidating mutation
- no policy/capability widening from untrusted content
- no automatic retry of unresolved irreversible non-idempotent effect
- every committed action references evidence and verifier result
- every replan creates a new version and preserves prior history

## Confidence
**94%** for a single deterministic durable controller with model proposal interfaces. **87%** for the initial recovery transition table/retry budgets; fault injection should tune these.