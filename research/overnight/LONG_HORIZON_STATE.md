# Long-Horizon State and Context Architecture

## Decision
Use **authoritative structured execution state + append-only event journal + bounded working projection + optional retrieval memory**. Do not treat the model transcript, vector store, or semantic memory as authoritative task state.

**Confidence: 95%**

## Why
Long-horizon agent research increasingly converges on separating durable state from the active model context. LongSeeker/Context-ReAct uses explicit context operations to compress and discard resolved trajectory material. CAT separates stable task semantics, condensed long-term memory, and high-fidelity short-term interactions. MAGE argues semantic-similarity retrieval alone mismatches execution dependencies and instead maintains execution state around active branches/subgoals. Mem0 demonstrates that selective memory can dramatically reduce token/latency overhead versus full-history prompting, but its conversational-memory framing is not sufficient for action correctness.

BrowserAgentV2 should therefore keep correctness-critical state deterministic and queryable outside the LLM. The LLM receives a projection, not the database itself and not an ever-growing transcript.

## Minimal state model

### GoalState — authoritative
- `task_id`
- immutable normalized user objective
- explicit constraints/prohibited effects
- completion predicates
- status

### PlanState — authoritative
- ordered/subgoal DAG or compact ordered steps
- current subgoal/step
- dependencies
- per-step success predicates
- retry/recovery budget
- plan revision/version

### ActionState — authoritative
- stable logical `action_id`
- `step_id`
- action intent/tool/TargetSpec
- risk class
- preconditions/freshness evidence reference
- lifecycle status
- attempt IDs
- idempotency/reconciliation metadata
- verifier outcome/evidence references

### FactState — durable but revocable
Only facts that can affect future decisions:
- value
- source/provenance
- observed_at
- scope/resource
- confidence
- invalidation condition / TTL where appropriate

Do not store arbitrary model conclusions as facts without provenance.

### RecoveryState — authoritative
- unresolved action IDs
- last verified checkpoint
- pending reconciliation
- recovery budget
- last known application/window/resource fingerprints

### EventLog — append-only source of history
Events such as:
- GOAL_ACCEPTED
- PLAN_VERSIONED
- STEP_STARTED
- ACTION_INTENT_RECORDED
- ACTION_DISPATCHED
- ACTION_RESULT_OBSERVED
- ACTION_VERIFIED
- ACTION_OUTCOME_UNKNOWN
- FACT_ASSERTED / FACT_INVALIDATED
- STEP_VERIFIED
- PLAN_REVISED
- RECOVERY_STARTED / RECOVERY_RESOLVED

The event log is audit/recovery evidence. Normal model calls should not ingest it wholesale.

## Bounded working projection
Each model turn should be assembled from a fixed schema with explicit budgets:
1. stable goal + constraints + policy summary;
2. current plan and current step;
3. current environment observation / target candidates;
4. recent verified actions, typically last 3-8 relevant actions;
5. unresolved errors/recovery state;
6. selected facts required for the current step;
7. retrieved historical evidence only on demand.

The target property is that prompt size depends on current task complexity, not total action count. A 1,000-action run should not automatically expose 1,000 actions to the model.

## Compaction rule
Compact at semantic boundaries, especially after a subgoal is VERIFIED. A completed subgoal becomes a small structured summary containing:
- achieved postcondition;
- durable facts produced;
- resource IDs/handles that remain valid;
- relevant evidence refs;
- unresolved caveats.

Raw trajectory remains in the event/evidence store and is queryable, but leaves active context. Failed branches should not contaminate the active state projection unless needed for recovery or to avoid repeating a known failure.

## Retrieval memory
Retrieval is **advisory**, not authoritative. It may surface:
- prior successful recovery pattern;
- app capability observations;
- known user/project fact;
- prior failure on a similar target.

Retrieved memory must carry provenance and freshness. It cannot directly mark a step complete or override current observed state. This avoids semantic retrieval mixing stale/failed trajectories into execution state.

Start with SQLite structured tables + FTS5/metadata filtering. Do not add a vector DB until a benchmark demonstrates FTS/structured retrieval misses useful facts often enough to matter.

## Prompt-flatness experiment
Create synthetic 200/500/1,000-action tasks with the same current-step complexity. Measure active prompt tokens at fixed milestones.

Pass criteria:
- median prompt tokens after warm-up grow <15% from 200 to 1,000 actions;
- required-fact recall >=99% on deterministic fixtures;
- stale/invalidated fact injection <=0.5%;
- no failed-branch trace is included unless explicitly relevant;
- full state reconstructs from checkpoint + event log after injected crash.

Compare:
A. full transcript;
B. rolling summary only;
C. structured projection + recent window;
D. C + retrieval.

Expected winner: C or D. D remains optional unless it improves success enough to justify retrieval contamination risk.

## Rejected alternatives
### Full transcript
Rejected: token/latency growth, distraction, failure-history contamination.

### Vector memory as task state
Rejected: approximate retrieval cannot be the authority for whether an irreversible action occurred or a step completed.

### One giant mutable summary
Rejected: summary drift and loss are difficult to detect; cannot provide audit/reconciliation semantics.

### Persist chain-of-thought
Rejected: unnecessary for execution correctness. Persist decisions, tool inputs/outputs, evidence, summaries, and state transitions instead.

## Risks
- Projection can omit a fact needed later.
- Compaction can preserve an incorrect conclusion.
- Event log can grow large on disk even though prompt stays bounded.
- Planner revisions need explicit versioning to avoid mixing old/new step IDs.

## Cheapest validation
Implement only the state schemas + deterministic projection builder + synthetic long-run generator. No model required initially. Prove bounded token growth and exact reconstruction before integrating semantic retrieval.
