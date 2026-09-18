# BrowserAgentV2 Falsification-First Vertical Slice

## Purpose
This is the smallest production-shaped slice that can falsify the core architecture before model integration, Windows work, or broad end-to-end benchmarking. It deliberately reuses the existing Phase 0 evidence discipline instead of replacing it.

## Hypothesis
A durable deterministic controller can prevent stale/wrong dispatch, reject false action success, and reconstruct/reconcile state after crashes without depending on model hidden state.

If this hypothesis fails in controlled fixtures, stop and repair the contract before adding models, skills, visual specialists, Windows UIA, or external benchmarks.

## Existing code to reuse
- `phase0/harness/runner.py`: preserve the separation between action execution and independently observable verification. Do not force production controller semantics into `ExperimentRunner`; use it as the measurement oracle around new fixtures.
- `phase0/harness/persistence.py`: preserve JSONL evidence/reporting for experiment outputs. Do not make it the production recovery journal.
- `phase0/harness/classification.py`: reuse the discipline of finite typed outcomes; production action outcomes need a separate vocabulary.
- existing fixture/campaign patterns under `phase0/experiments/*` and tests under `tests/phase0/*`.

## New package boundary
Create `computer_agent/` rather than growing `phase0/` into production runtime code.

### `computer_agent/types.py`
Minimal immutable/value types:
- `TaskId`, `PlanId`, `StepId`, `ActionId`, `AttemptId`, `ObservationId`, `VerificationId`
- `ObservationVersion`
- `TargetSpec`: semantic intent only; no backend handle
- `TargetCandidate`: observation-local candidate + provenance + ambiguity evidence
- `ExecutionRef`: opaque adapter-local reference valid only for a specific observation version
- `ActionIntent`: logical action, target spec, arguments, capability request, risk/idempotency class
- `VerificationSpec`: typed predicates + safety invariants

Do not add a UniversalElement, agent-to-agent message schema, vector-memory type, or model-specific fields.

### `computer_agent/state.py`
Authoritative state only:
- `GoalState`
- versioned `PlanState`
- `StepState`
- `ActionState`
- `RecoveryState`
- provenanced/revocable `FactState`

State transitions are deterministic and validate invariants. No transcript is authoritative state.

### `computer_agent/journal.py`
SQLite-backed append-only event journal with transactionally durable events. Start with one local DB and WAL mode. Required event identity: `event_id`, `task_id`, optional plan/step/action/attempt IDs, event type, timestamp, schema version, compact payload.

Initial finite event vocabulary:
`TASK_CREATED`, `PLAN_COMMITTED`, `STEP_READY`, `TARGET_RESOLVED`, `TARGET_REJECTED`, `ACTION_INTENT_PERSISTED`, `POLICY_ALLOWED`, `POLICY_BLOCKED`, `DISPATCH_STARTED`, `OBSERVATION_RECORDED`, `VERIFICATION_RECORDED`, `ACTION_COMMITTED`, `ACTION_FAILED`, `OUTCOME_UNKNOWN`, `REPLAN_COMMITTED`, `TASK_COMPLETED`, `TASK_HALTED`.

The journal is recovery truth. OTel/JSONL exports are derived and may be deleted without affecting recovery.

### `computer_agent/grounding.py`
Interfaces only plus deterministic fake implementation for V1:
- `Resolver.resolve(TargetSpec, Observation) -> ResolutionResult`
- resolution can be `RESOLVED`, `AMBIGUOUS`, `ABSENT`, `STALE`, `UNSUPPORTED`
- resolved candidate is bound to `ObservationVersion`
- `freshness_check(candidate, current_observation)` must run immediately before consequential dispatch
- any identity/version mismatch abstains; never guess among tied candidates

### `computer_agent/verification.py`
Small compositional predicate vocabulary:
- equality / inequality
- existence / absence
- membership / contains
- numeric/range
- count/delta
- before->after transition
- invariant-not-changed
- AND / OR
- bounded domain callback only when primitives cannot express the condition

Result vocabulary:
`VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, `INCONCLUSIVE`, `PARTIAL_SUCCESS`, `UNEXPECTED_SIDE_EFFECT`.

No model may convert `INCONCLUSIVE` into success.

### `computer_agent/policy.py`
Deterministic capability gate. It receives original task authority + `ActionIntent`; observations/model text are evidence only and cannot widen scope. First fixture capabilities: allowed target app/domain, allowed filesystem prefix, allowed recipient set, allowed action classes, confirmation-required flag.

### `computer_agent/controller.py`
One durable controller. No autonomous planner/executor/recovery sub-agents.

Minimal consequential-action path:
1. read durable current state
2. obtain fresh observation
3. resolve `TargetSpec`
4. reject ambiguity/absence
5. run deterministic policy gate
6. persist `ACTION_INTENT_PERSISTED`
7. run pre-dispatch freshness check
8. persist `DISPATCH_STARTED`
9. adapter dispatch
10. independently observe
11. evaluate success predicates + safety invariants
12. persist verification
13. commit action outcome
14. only then advance step

Recovery starts from journal + external observation, never model hidden state.

### `computer_agent/recovery.py`
Classify unresolved persisted actions:
- idempotency-key capable -> retry/reconcile with same logical `action_id`
- externally queryable effect -> query before retry
- naturally idempotent state-set -> verify current state, then repeat only if needed
- non-idempotent + non-queryable -> `OUTCOME_UNKNOWN` / `NEEDS_REVIEW`; no automatic retry

## Falsification fixtures

### Fixture A — mutable UI graph
Pure-Python deterministic fake UI with observation version and stable semantic fixture IDs hidden from the controller. Seeded mutations include duplicate labels, replacement, reorder, overlay, hide/disable, absent target, same-label ambiguity, and mutation between resolve and dispatch.

The controller must never receive the fixture's hidden ground-truth ID through `TargetSpec`; that would make the test circular.

### Fixture B — deceptive action service
Dispatch can return success while configured to perform expected mutation, no-op, wrong-object mutation, partial mutation, delayed mutation, duplicate mutation, or prohibited collateral mutation. Verifier reads independently observable service state.

### Fixture C — crashable side-effect service
Implements the four recovery classes from `VALIDATION_PLAN.md`. Expose deterministic kill hooks at every persistence/dispatch/verify/commit boundary. Restart controller from a new process/object with only durable journal and external service state.

### Fixture D — authority-injection observation
Observation text/labels request expanded recipient/domain/path/tool/verifier permissions. The model layer is not needed: feed those requested intents directly into policy tests. If deterministic policy can be tricked by observation provenance, architecture fails regardless of model quality.

## Exact first test files
- `tests/computer_agent/test_grounding_freshness.py`
- `tests/computer_agent/test_verifier_faults.py`
- `tests/computer_agent/test_journal_replay.py`
- `tests/computer_agent/test_crash_reconciliation.py`
- `tests/computer_agent/test_policy_authority.py`
- `tests/computer_agent/test_controller_invariants.py`

Use seeded/property-style loops without adding a dependency initially. Record failing seed in assertion/report so every discovered failure becomes a fixed regression case.

## Non-negotiable invariants
1. No dispatch without a persisted logical intent.
2. No consequential dispatch using a candidate that fails freshness.
3. Ambiguity/absence/staleness never silently becomes a guessed target.
4. API/adapter return success never equals task success.
5. Step advancement requires committed verifier evidence.
6. Safety-invariant violation cannot produce `VERIFIED_SUCCESS`.
7. Untrusted observation cannot increase capability.
8. Recovery never blindly retries ambiguous non-idempotent/non-queryable effects.
9. Replay of the durable journal reconstructs the same deterministic controller state.
10. Disabling telemetry cannot change any of the above.

## First runnable campaign
Implement only Fixture A + grounding interfaces + controller freshness gate first. Run >=1,000 deterministic seeded trials distributed across mutation classes. Gate: zero wrong-target and zero stale-target dispatches; ambiguous/absent cases abstain. Do not optimize success rate until wrong-action rate is zero in the controlled fixture.

Then add Fixture B and require zero false-success verifier classifications across >=1,000 injected trials. Only after A/B pass should SQLite crash reconciliation be implemented, because otherwise recovery testing is built on an untrusted action-success definition.

## Stop conditions
- Any wrong/stale dispatch: stop expansion; inspect target identity/freshness contract.
- Any verifier false-success: stop expansion; inspect observation independence/predicate semantics.
- Any blind retry of class-D ambiguous side effect: stop expansion; inspect journal/recovery transition.
- If controller implementation requires model-specific state to replay correctly, architecture has violated its own durable-state contract.
- If the small verifier vocabulary cannot express >=90% of representative postconditions even with bounded domain callbacks, revisit verifier design before app-specific DSL proliferation.

## What not to build in this slice
No LLM runtime, Qwen integration, visual grounder, vector DB, embeddings, skill learning, multi-agent framework, OpenTelemetry backend, Windows UIA, benchmark adapter, GUI dashboard, or automatic skill induction. They cannot increase confidence in the deterministic contracts this slice is intended to falsify.

## Definition of success
This slice succeeds when the controlled campaigns show that the controller can (a) refuse stale/ambiguous targets, (b) distinguish dispatch success from semantic success, (c) durably explain every consequential action, and (d) recover without unsafe duplicate side effects. At that point model and platform adapters become replaceable quality/performance layers rather than correctness foundations.