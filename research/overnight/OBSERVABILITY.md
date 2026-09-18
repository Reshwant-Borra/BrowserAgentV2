# BrowserAgentV2 Observability Contract

## Decision
Observability is part of the controller correctness contract, not a dashboard added later. Persist a compact structured event journal as the authoritative audit/recovery record; emit correlated OpenTelemetry-compatible traces/metrics as a derived operational view. Do not make OTel the recovery database.

**Confidence: 94%.**

## Why
BrowserAgentV2 must diagnose failures across grounding, policy, dispatch, verification, recovery, model proposal and route fallback. Existing Phase 0 evidence already records before/after state, action mechanism, latency, postcondition result, interference classification and evidence references. Production should preserve that discipline while adding durable controller correlation.

OpenTelemetry's current GenAI conventions expose model, token, duration and agent/tool-call spans, which makes OTel a useful interoperability layer. Its own guidance also recommends recording only attributes with clear diagnostic value and treating verbose/sensitive content as opt-in. Therefore BrowserAgentV2 should emit compact identifiers and summaries by default, with large artifacts referenced by content-addressed IDs rather than copied into every event.

## Canonical IDs
Every record should carry the applicable subset:
- `task_id`
- `plan_id`, `plan_version`
- `step_id`
- stable logical `action_id`
- `attempt_id`
- `observation_id` / observation version
- `target_resolution_id`
- `verification_id`
- `model_call_id`
- `skill_id`, `skill_version`
- `trace_id`, `span_id`

IDs must allow one action to have multiple attempts without pretending they are multiple logical effects.

## Event types
Keep the vocabulary finite and typed:
- `task.created`, `task.completed`, `task.blocked`
- `plan.proposed`, `plan.committed`, `plan.revised`
- `observation.captured`
- `target.resolve_started`, `target.resolved`, `target.ambiguous`, `target.stale`
- `policy.allowed`, `policy.blocked`
- `action.intent_persisted`, `action.dispatch_started`, `action.dispatch_returned`
- `verification.started`, `verification.success`, `verification.failure`, `verification.inconclusive`
- `action.committed`, `action.outcome_unknown`
- `recovery.started`, `recovery.reconciled`, `recovery.handoff`
- `route.switched`
- `model.proposal_started`, `model.proposal_completed`, `model.schema_invalid`
- `skill.selected`, `skill.loaded`, `skill.rejected`
- `safety.invariant_violation`

## Minimum action trace
For every consequential action, reconstruct this chain without model prose:
`intent persisted -> policy decision -> target resolution/freshness -> dispatch -> observation -> verification -> commit/recovery transition`.

If the chain cannot be reconstructed from durable records, the observability schema is insufficient.

## Fields worth storing by default
- timestamps and monotonic duration
- controller state before/after
- action type and mechanism/route
- target semantic summary + candidate count + provenance, not raw secret-bearing page text
- policy rule/capability decision code
- expected postcondition predicate IDs
- verification outcome/evidence IDs
- retry/re-ground/route-switch reason code
- model identity/quantization/backend, schema validity, input/output token counts, latency
- skill/version
- failure taxonomy code
- environment/app/browser version
- artifact references for screenshots/DOM/AX/UIA snapshots when enabled

## Large/sensitive data
Raw prompts, page text, screenshots, OCR, DOM/AX trees, credentials and tool outputs can contain secrets or untrusted content. Default trace events should store hashes/references plus bounded redacted summaries. Full artifacts should be opt-in for controlled experiments, encrypted or local, and subject to retention limits. Never require raw model chain-of-thought for correctness or recovery.

## Metrics
Release dashboards should derive at least:
- verifier-confirmed task/action success
- wrong-target dispatch
- safe abstention
- stale-target catches
- verifier false-success/false-failure/inconclusive
- policy blocks and invariant violations
- route-switch rate
- retries per action
- recovery/reconciliation success
- duplicate side-effect count
- `OUTCOME_UNKNOWN` count
- model schema-invalid rate
- model/token/latency distributions
- prompt projection size by trajectory length
- action/verification p50/p95 latency
- failure taxonomy distribution

## Storage architecture
Start simple:
1. SQLite append-only logical event table + normalized current-state tables/indices for recovery.
2. Artifact directory/content-addressed store for screenshots and bulky evidence.
3. Optional OpenTelemetry exporter translating controller/model/tool operations into spans and metrics.
4. JSONL export for experiment analysis/regression fixtures.

Do not add Elasticsearch, a vector database, or a distributed tracing backend to v1 unless local evidence volume makes SQLite/artifact files inadequate.

## Sampling
Correctness/recovery journal events are never sampled. High-volume diagnostic artifacts may be sampled or retained only around failures. Operational OTel traces can use sampling, but sampling must not affect controller state or auditability.

## Validation
1. Generate every controller failure class and assert a deterministic root-cause query can identify transition, route, action ID and verification evidence.
2. Crash at each action boundary and prove recovery uses journal state, not OTel delivery.
3. Disable OTel exporter entirely; behavior/recovery must remain identical.
4. Run 1,000-action synthetic task and measure event/artifact growth.
5. Inject sensitive strings into observations and assert default trace/event export does not contain them verbatim.

## Rejected alternatives
- **Raw transcript as trace:** too large, privacy-sensitive, and semantically ambiguous.
- **OTel as source of truth:** exporters/sampling are operational telemetry, not a transactional recovery log.
- **Log every object field:** unnecessary volume and secret exposure.
- **No structured tracing until production:** makes fault-injection evidence difficult to interpret and encourages unverifiable debugging anecdotes.