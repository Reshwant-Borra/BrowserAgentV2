# Final BrowserAgentV2 Architecture

## Verdict
The architecture is ready to begin falsification-first implementation. It is **not production-validated**. V1-V8 remain unexecuted.

## One coherent architecture
BrowserAgentV2 should be a **durable deterministic computer-agent controller with semantic-first control, independent verification, bounded model proposals, and capability-gated visual fallback**.

Control route order:
1. deterministic app/API/tool integration when explicitly available and authorized
2. Playwright/CDP browser semantics
3. platform accessibility semantics: macOS AX / Windows UIA
4. visual grounding + virtual input for semantic gaps
5. capability-gated foreground physical input
6. safe abstention / human handoff

Route availability is measured per app/action/capability. No route is trusted because an API call returned success.

## Runtime ownership
### Deterministic controller owns
- Goal/Plan/Step/Action/Recovery lifecycle
- capability/policy enforcement
- retry and route-switch budgets
- target freshness requirements
- verification requirements
- durable event journal
- crash reconciliation
- bounded model-context projection
- skill loading/execution boundaries

### Models may propose
- plans/replans
- semantic `TargetSpec`s
- arguments
- interpretation of ambiguous observations
- optional visual grounding candidates

Models never authorize themselves, declare durable success, widen scope, or become recovery state.

## Consequential action transaction
`read durable state -> fresh observation -> resolve TargetSpec -> reject ambiguity/absence -> deterministic policy gate -> persist logical intent -> pre-dispatch freshness check -> persist dispatch start -> dispatch -> independently observe -> evaluate success predicates + safety invariants -> persist verification -> commit outcome -> advance step`

Any consequential action without this lifecycle is outside the production contract.

## Target model
Do not build a durable UniversalElement.

`TargetSpec` is semantic intent only. A fresh observation produces observation-local `TargetCandidate`s. A selected candidate yields an opaque backend `ExecutionRef` valid only for that observation/version. Mutation, stale version, target ambiguity, focus/window changes, or identity mismatch cause re-resolution/abstention.

## Verification model
Every state-changing adapter/skill supplies a `VerificationSpec`. Prefer structured environment/app state over screenshot similarity or model self-judgment. Initial predicates: equality/inequality, existence/absence, contains/membership, numeric/range, count/delta, before->after transition, invariant-not-changed, AND/OR, bounded domain callback.

Outcomes include `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, `INCONCLUSIVE`, `PARTIAL_SUCCESS`, `UNEXPECTED_SIDE_EFFECT`, plus controller-level stale/ambiguous/policy/outcome-unknown states. `INCONCLUSIVE` never silently becomes success.

## Durable state and memory
Correctness-critical Goal/Plan/Action/Recovery state lives outside the model. Use a local SQLite append-only event journal (WAL) plus deterministic materialized state. Facts are provenanced/revocable. Model context is a bounded projection of current goal, current plan/step, relevant recent verified actions, unresolved failures, current observation and selected facts. Start with SQLite/FTS; retrieval is advisory and cannot override authoritative state. No vector DB until measured need.

## Crash semantics
Persist a stable logical `action_id` before dispatch. There is no generic exactly-once guarantee for arbitrary external/UI effects.
- idempotency-key capable: reconcile/retry with same logical ID
- externally queryable: query effect before retry
- naturally idempotent state-set: verify state then repeat only if needed
- non-idempotent + non-queryable: `OUTCOME_UNKNOWN/NEEDS_REVIEW`; never blind retry

## Security boundary
Authority comes only from original task scope, deterministic local policy, pre-granted capabilities and durable state. Web/DOM/AX/UIA/screenshot/OCR/document/tool/model/retrieved content is information, not authority. Every consequential `ActionIntent` passes deterministic task-scoped capability and data-flow checks. Prompt-injection detection is defense-in-depth only.

## Local model architecture
Begin evaluation with one replaceable multimodal ~8B generalist behind typed schemas; Qwen3-VL-8B-Instruct is the first benchmark candidate, not a permanent dependency. Add a 2-3B GUI grounder only if semantic-gap fixtures show material verifier-confirmed improvement after latency/residency cost. Add a critic only for measured verifier-inconclusive cases. Stable-prefix/prompt caching is performance-only and never state.

## Skills
Skills are versioned progressive-disclosure procedures, not sub-agents. Each contains compact metadata, typed inputs, capability envelope, preconditions, procedure/helpers, postcondition verifier, safety invariants, idempotency classification and regression fixtures. Successful traces may propose a skill but never auto-promote to trusted executable code.

## Observability
The SQLite journal is recovery/audit truth. Optional JSONL/OpenTelemetry traces are derived. Correlate task/plan/step/action/attempt/observation/verification/model/skill IDs. Telemetry can fail or be disabled without changing behavior. Raw prompts/screenshots/tool outputs are opt-in artifacts, not default trace attributes.

## Existing code disposition
KEEP: Phase 0 ExperimentRunner/ActionSpec verification discipline, evidence/reporting, observer/classification patterns, browser Playwright/CDP route, bounded AX discovery, stale-element behavior, repeated-trial campaigns, historical failure fixtures.

MODIFY/GENERALIZE: non-interference observation, route capability matrix, stale-target handling, production outcome vocabulary.

DO NOT GROW INTO PRODUCTION: Phase 0 ExperimentRunner and JSONL persistence. Create separate `computer_agent/` production package.

REMOVE/DEFER: browser-through-AX as primary route, vision-first default, physical input default, Graphify runtime memory, durable UniversalElement, autonomous planner/executor/recovery agents, always-on model ensemble, vector DB, mandatory GUI specialist, mandatory critic.

## Production package boundary
`computer_agent/types.py`
`computer_agent/state.py`
`computer_agent/journal.py`
`computer_agent/grounding.py`
`computer_agent/verification.py`
`computer_agent/policy.py`
`computer_agent/controller.py`
`computer_agent/recovery.py`

Model, skills, visual specialist, Windows UIA, telemetry exporters and benchmark adapters are added only after deterministic contracts survive their gates.

## Overall confidence
Architecture: **92%** that this is the correct implementation direction.
Production reliability: **not yet established**. The remaining high-impact uncertainty is empirical: grounding freshness, verifier false-success resistance, crash reconciliation, bounded-state reconstruction, hardware model performance and Windows UIA capability.