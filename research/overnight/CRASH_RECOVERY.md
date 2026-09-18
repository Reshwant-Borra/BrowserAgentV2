# Crash Recovery and Side-Effect Reconciliation

## Core decision
Treat external actions as **durable intent transactions**, but do not claim generic exactly-once execution. Use stable logical action IDs, write-ahead intent, explicit outcome classes, tool-native idempotency where available, state reconciliation where queryable, and human/policy escalation for irreversible non-idempotent ambiguous outcomes.

**Confidence: 97%**

This is stricter than a normal checkpoint/retry loop.

## Fundamental crash window
There is an unavoidable ambiguity for a non-transactional external side effect:

1. BrowserAgentV2 durably records ACTION_INTENT.
2. It dispatches an external operation.
3. External system commits the operation.
4. Agent crashes before durably recording the result.

After restart, local state alone cannot distinguish "operation never happened" from "operation happened but acknowledgement was lost." Retrying blindly can duplicate the effect. Checkpointing does not remove this ambiguity.

Durable-workflow systems such as Temporal therefore use at-least-once activity execution by default and recommend idempotent activities. This is a distributed-systems property, not an LLM-specific problem.

## Action lifecycle
Use a durable state machine:

`PROPOSED -> INTENT_RECORDED -> DISPATCHING -> {OBSERVED_RESULT | OUTCOME_UNKNOWN} -> {VERIFIED_SUCCESS | VERIFIED_FAILURE | RECONCILED | NEEDS_REVIEW}`

Never interpret process death during DISPATCHING as failure.

### Required write ordering
For any state-changing action:
1. create stable logical `action_id` and persist intent;
2. persist policy/approval/freshness decision;
3. dispatch using `action_id` as idempotency key when supported;
4. persist returned result/evidence;
5. independently observe and verify postcondition;
6. persist final outcome;
7. only then advance PlanState.

Attempt IDs are telemetry. `action_id` identifies the logical effect and remains stable across retry/reconciliation.

## Recovery classification
On startup, query all nonterminal ActionStates.

### Case A — no dispatch recorded
Safe to resume dispatch after revalidating preconditions.

### Case B — dispatched, tool supports idempotency key
Retry/query using the same logical action ID. Never generate a new key for a retry.

### Case C — dispatched, external state is queryable
Reconcile before retry. Observe the resource and evaluate the intended postcondition. Examples are state-setting operations where the desired final value can be read back.

### Case D — dispatched, effect is naturally idempotent
Re-execute only after proving preconditions still permit it. "Set X to Y" is usually easier than "increment X".

### Case E — dispatched, irreversible/non-idempotent and outcome cannot be queried
Do **not** automatically retry. Mark `OUTCOME_UNKNOWN` / `NEEDS_REVIEW` or use a domain-specific compensation/reconciliation mechanism. Reliability requires admitting uncertainty.

## UI-specific reconciliation
GUI actions often lack API idempotency keys. Therefore prefer **state-setting and verifiable operations** over blind event replay.

Examples of safer semantics:
- "ensure checkbox is checked" rather than "click checkbox";
- "ensure field value equals V" rather than "type V";
- "navigate to URL U" rather than replaying Back/Forward blindly.

For potentially consequential UI submit actions, recovery should inspect the resulting application/resource state before clicking again. A button still being visible is not sufficient proof the prior submit failed.

## Journal + checkpoint
Use both:
- append-only EventLog for ordered evidence/audit/replay;
- periodic materialized checkpoint of Goal/Plan/Action/Fact/Recovery state for fast startup.

Recovery loads latest valid checkpoint, replays later events, then reconciles unresolved actions against the external world. The event log is authoritative for what BrowserAgentV2 knows; external observation is authoritative for what the environment currently contains.

SQLite WAL is sufficient for v1. Do not add Temporal or another workflow service until BrowserAgentV2 proves it needs distributed workers/durable timers at a scale that justifies the operational dependency.

## Nondeterminism
Do not replay an LLM call and assume it reproduces the same decision. Persist the accepted structured model output (plan revision/action proposal) as an event. Recovery reuses accepted decisions until current evidence invalidates them, in which case it records an explicit revision rather than silently regenerating history.

## Crash-injection experiment
Build a deterministic fake external service with:
- queryable resource state;
- optional idempotency-key support;
- non-idempotent increment endpoint;
- configurable acknowledgement loss.

Inject process death at every boundary:
1. before intent commit;
2. after intent commit/before dispatch;
3. during dispatch before external commit;
4. after external commit/before response;
5. after response/before local result commit;
6. after result commit/before verification;
7. after verification/before plan advancement.

Run >=1,000 randomized trials per action class.

### Required invariants
- no idempotency-capable logical action produces >1 external effect;
- no unresolved non-idempotent ambiguous action is automatically repeated;
- plan never advances without VERIFIED_SUCCESS or an explicit policy-approved equivalent;
- restart reconstructs the same accepted plan/action IDs;
- all ambiguity becomes an explicit state, never guessed success/failure.

## ADR
### Decision
Implement local durable intent/event semantics in BrowserAgentV2 before adding a distributed workflow engine.

### Confidence
94%.

### Alternatives rejected
- retry last step after crash: unsafe duplicate window;
- checkpoint only after each step: still unsafe between external commit and checkpoint;
- generic exactly-once claim: impossible without cooperation/transaction/idempotency at side-effect boundary;
- adopt Temporal immediately: correct concepts but unnecessary service complexity for a single-machine v1.

### Main risk
Some third-party UI actions cannot be reconciled automatically. The architecture must surface `OUTCOME_UNKNOWN` rather than conceal this limitation.

### Cheapest validation
Implement the fake-service crash matrix before touching real consequential integrations. If the state machine cannot survive that fixture, it is not ready for real side effects.
