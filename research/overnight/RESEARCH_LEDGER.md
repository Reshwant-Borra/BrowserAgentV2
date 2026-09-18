# Overnight Research Ledger

This file is the continuity handoff between scheduled research runs.

## Rules
- Read this file before starting new research.
- Do not repeat a source/question unless prior evidence is inadequate or contradictory.
- Append meaningful findings rather than replacing history.
- Update the current architecture hypothesis and unresolved questions after every run.
- Record negative results and failed hypotheses.

## Current Architecture Hypothesis
Preserve BrowserAgentV2's reliability-first architecture and Phase 0 harness. Production direction is a **hybrid semantic-first, verifier-grounded ComputerAgent**: deterministic tools/APIs when available -> Playwright/CDP browser semantics -> platform accessibility -> visual grounding/coordinate fallback -> foreground/handoff. Authoritative Goal/Plan/Action/Policy/Recovery state remains outside the model in structured durable storage plus an append-only event journal. Model context is a bounded projection of current state, recent verified actions, unresolved errors and selected facts; retrieval memory is advisory only. Every state-changing action is a durable intent transaction with stable logical action ID. Plan advances only after separately observed postcondition verification. Crash recovery reconciles uncertain external effects before retry and never assumes generic exactly-once execution. Targets use route-neutral semantic intent (`TargetSpec`) resolved against a fresh observation into ephemeral candidates; backend handles/coordinates are never durable identity. Consequential actions get a pre-dispatch freshness gate. Verification uses typed predicates and explicit inconclusive/partial/unsafe outcomes. Model specialization remains experimentally open.

## Evidence Entries

### 2026-09-18 00:xx ET — BrowserAgentV2 Phase 0 browser/AX campaigns
- **Finding:** Existing measurement harness is a strong asset. Browser campaign ran 500 semantic trials with 500/500 verified postconditions, zero physical cursor movement and zero foreground-app changes. AX campaign ran 510 trials with 510/510 verified postconditions and explicit stale-element failure behavior.
- **Evidence quality:** 5
- **Impact:** keep ExperimentRunner/ActionSpec/observer/classification/evidence discipline and semantic browser route.

### 2026-09-18 00:xx ET — macOS AX capability survey
- **Finding:** Generic AX discovery/read is broad, but verified mutation/action is not. Chrome AXPress returned API success while failing to fire a plain HTML button; VS Code custom UI exposed sparse semantics.
- **Evidence quality:** 5
- **Impact:** browser semantics precede AX; actions capability-gated; API success never equals verified success; visual fallback required.

### 2026-09-18 00:xx ET — Hybrid control / verification research
- **Finding:** Pixel-only universality does not imply local reliability/background execution. Structured environment-state verification is stronger than trusting action API/model success. More history/compute is not monotonic reliability improvement.
- **Evidence quality:** 3-4
- **Impact:** hybrid route hierarchy, typed verifier, bounded retries/selective compute.

### 2026-09-18 00:5x ET — Target representation + freshness
- **Finding:** Do not unify backend identity. Use `TargetSpec` -> fresh resolution -> observation-local `TargetCandidate` -> opaque adapter-local `ExecutionRef`. Consequential actions need pre-dispatch state revalidation because post-action verification is too late for irreversible wrong-target effects.
- **Evidence quality:** 4-5
- **Impact:** reject durable UniversalElement; ambiguity is abstention; freshness gate.

### 2026-09-18 01:xx ET — Windows/UIA + visual fallback
- **Finding:** UIA is the correct Windows semantic route but does not imply background-safe action. Use capability-gated UIA with input/visual fallback. Dedicated GUI grounder remains optional; benchmark UI-TARS-2B first with ZonUI-3B and UGround-V1-2B challengers, optimizing wrong-target/abstention/latency rather than leaderboard score.
- **Evidence quality:** 3-4
- **Impact:** cross-platform semantic-first hierarchy survives; no permanent grounder yet.

### 2026-09-18 02:xx ET — Long-horizon state/context
- **Question:** How can 200-1,000 action tasks avoid prompt growth and retrieval contamination?
- **Finding:** Long-horizon research (LongSeeker, CAT, MAGE, Mem0) converges on selective/structured context management rather than append-only transcripts. MAGE specifically identifies semantic-retrieval mismatch with execution dependencies. For BrowserAgentV2, correctness-critical Goal/Plan/Action/Recovery state must therefore be structured and authoritative outside the model; the model receives a bounded projection. Retrieval memory is advisory and provenance/freshness-tagged.
- **Evidence quality:** 3-4, architecture reasoning 5
- **Impact:** add `GoalState`, versioned `PlanState`, `ActionState`, revocable `FactState`, `RecoveryState`, append-only EventLog, bounded working projection. Start SQLite + structured/FTS retrieval; no vector DB until benchmark justifies it.
- **Validation:** 200/500/1,000 action synthetic prompt-flatness/reconstruction benchmark. Target <15% active-token growth from 200 to 1,000 actions with >=99% required-fact recall.

### 2026-09-18 02:xx ET — Crash reconciliation / durable side effects
- **Question:** Can an unresolved ACTION_INTENT safely resume without duplicate external effects?
- **Finding:** No generic exactly-once guarantee exists across arbitrary external/UI effects. Crash after external commit but before local result persistence creates irreducible ambiguity unless the external system supports idempotency or state can be reconciled. Durable workflow systems use at-least-once activities and idempotency/reconciliation for this reason. Checkpoints alone do not close the commit/ack window.
- **Evidence quality:** 4
- **Impact:** stable logical `action_id`; persist intent before dispatch; use same idempotency key across retries; reconcile queryable state before retry; ambiguous irreversible non-idempotent actions become `OUTCOME_UNKNOWN/NEEDS_REVIEW`, never blind retry. Persist accepted model decisions rather than regenerating them during replay.
- **Validation:** fake external service with crash injection at every intent/dispatch/commit/result/verify boundary, >=1,000 randomized trials/action class.

## Decisions Recorded
See `ARCHITECTURE_DECISIONS.md`:
- ADR-O1 hybrid semantic-first control, visual fallback — 94%
- ADR-O2 verification as first-class typed contract — 97%
- ADR-O3 re-resolve semantic targets after mutation — 95%
- ADR-O4 repeated-trial reliability metric — 92%
- ADR-O5 do not freeze multi-model architecture yet — 86%
- ADR-O6 safety invariants accompany success predicates — 93%
- ADR-O7 no durable universal element — 95%
- ADR-O8 pre-dispatch freshness gate — 89%
- ADR-O9 structured authoritative execution state; retrieval advisory — 95%
- ADR-O10 durable intent + reconciliation; no generic exactly-once claim — 97%

## Current Highest-Priority Unresolved Questions
Ranked by architecture impact × uncertainty × cheapness of validation:
1. **Security/policy:** convert task-level prohibited effects and indirect prompt injection into deterministic policy/verifier invariants; define trust boundaries for UI/web content.
2. **Planning/state machine:** minimal replanning policy and failure taxonomy; when to retry, re-ground, switch route, replan, or hand off.
3. **Local model split:** single generalist vs +GUI grounder vs +critic on one common fixture set; include prompt/KV-cache behavior and constrained output reliability.
4. **Grounding experiment implementation:** duplicate-label, replacement, reflow, overlay, absent-target, cross-route agreement fixtures.
5. **Verifier coverage experiment:** implement small predicate vocabulary and measure custom-predicate pressure before expanding DSL.
6. **Crash experiment implementation:** fake external service + injected crash matrix from `CRASH_RECOVERY.md`.
7. **Prompt-flatness experiment:** synthetic long-run state projection benchmark from `LONG_HORIZON_STATE.md`.
8. **Windows hardware capability matrix:** reproduce semantic/background assumptions on target machine.

## Negative Results / Assumptions Rejected
- Raw AX/UIA availability cannot be assumed behaviorally reliable or background-safe.
- Semantic object handles cannot be durable across UI mutation.
- Pixel-only is not automatically best because frontier CUAs use it.
- More context, more steps, or more model stages are not monotonic reliability improvements.
- One successful benchmark trajectory is not reliability evidence.
- Durable cross-backend `UniversalElement` is wrong abstraction.
- Screenshot difference alone is not semantic success verification.
- Post-action verification alone is insufficient for high-risk actions.
- Full transcript is not long-horizon memory architecture.
- Vector/semantic retrieval must not be authoritative execution state.
- A rolling summary alone is insufficient for recovery/audit correctness.
- Checkpoint-after-step does not provide exactly-once external effects.
- After an ambiguous non-idempotent external commit window, automatic retry is unsafe.
- LLM nondeterminism must not be silently replayed as though it were deterministic history.

## Handoff
This pass resolved long-horizon state and crash semantics enough to proceed. New artifacts: `LONG_HORIZON_STATE.md`, `CRASH_RECOVERY.md`; ADR-O9/O10 added. Do **not** redo generic memory/vector-database or durable-workflow surveys. Next pass should focus on policy/security trust boundaries and the planner/recovery state machine, then move into local-model routing if those converge. The key remaining implementation proofs are now explicit experiments rather than broad research questions.
