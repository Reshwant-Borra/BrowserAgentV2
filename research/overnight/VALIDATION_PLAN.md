# BrowserAgentV2 Validation Plan

## Purpose
This plan converts the current architecture hypothesis into falsifiable experiments. It deliberately prioritizes controller correctness before model quality. A strong model must not be allowed to hide broken state, verification, recovery, or authority contracts.

## Release philosophy
The architecture is not validated by one end-to-end demo. Each contract receives an adversarial fixture, repeated trials, a measurable pass criterion, and a stop condition. Failures must be classified before architecture changes are made.

## Order of operations

### V0 — Preserve and extend the existing Phase 0 harness
Reuse `ExperimentRunner`, independent `ActionSpec.verify`, observer snapshots, classification, evidence schemas, and repeated-trial reporting. Do not replace this measurement substrate with an agent framework. Add controller-level event IDs and trace correlation around it.

Pass: existing browser and AX campaigns remain reproducible with no semantic regression.
Stop: if harness changes invalidate prior evidence, repair measurement equivalence before continuing.

### V1 — Grounding freshness + abstention fixture
Build deterministic browser fixture pages with seeded mutations:
- duplicate labels with distinct semantic context
- target replaced after observation
- target reordered/reflowed
- overlay inserted between resolve and dispatch
- target absent
- target hidden/disabled
- ambiguous same-label controls
- iframe/shadow DOM boundary
- canvas/icon-only target
- stale observation version
- optional cross-route DOM/accessibility disagreement

For each trial persist `TargetSpec`, observation version/hash, candidate set, chosen candidate, provenance, confidence/ambiguity reason, execution route, freshness result, postcondition result.

Primary metrics:
- wrong-target dispatch rate
- correct abstention rate on ambiguous/absent cases
- stale-target dispatch rate
- verifier-confirmed success
- route-switch count
- p50/p95 resolution latency

Initial gate: **zero wrong-target dispatches and zero stale-target dispatches in controlled deterministic fixtures across >=1,000 seeded trials**. Ambiguous/absent cases must abstain rather than guess. Success rate is secondary to wrong-action prevention.

Architecture consequence: any non-zero wrong-target/stale dispatch is a blocker for consequential actions. Do not compensate by merely increasing model size; first inspect freshness/identity contract.

### V2 — Verifier false-success resistance
Create a fake application/service with actions that can return API success while independently producing: expected mutation, no-op, wrong-object mutation, partial mutation, delayed mutation, duplicate mutation, prohibited side effect, verifier-unavailable state.

Start verifier vocabulary intentionally small:
- equality / inequality
- existence / absence
- contains / membership
- numeric/range
- count/delta
- state transition from before -> after
- conjunction/disjunction
- invariant-not-changed
- domain callback only when primitive predicates cannot express the task

Metrics:
- false-success rate (critical)
- false-failure rate
- inconclusive rate
- verifier coverage across representative tasks
- verifier latency

Gate: **0 false successes in deterministic injected-fault fixtures across >=1,000 trials**. `INCONCLUSIVE` is acceptable where evidence is unavailable; silently converting inconclusive to success is forbidden.

Stop/expand DSL only if >=90% of representative BrowserAgentV2 task postconditions cannot be expressed compositionally with the small vocabulary plus a bounded domain callback interface.

### V3 — Crash/reconciliation matrix
Build a fake external side-effect service supporting four classes:
A. idempotency-key capable
B. externally queryable effect
C. naturally idempotent state-set
D. non-idempotent + non-queryable effect

Inject process termination at every durable boundary:
1. before intent persist
2. after intent persist / before dispatch
3. during dispatch
4. after external effect / before local observation
5. after observation / before verification
6. after verification / before commit
7. after commit / before plan advance
8. after plan advance

On restart, reconstruct solely from durable state and external reconciliation; do not replay model hidden state.

Metrics:
- duplicate side effects
- lost committed effects
- incorrect success declarations
- incorrect blind retries
- recovery classification accuracy
- recovery latency

Gate: across >=1,000 randomized trials per action class: **zero duplicate effects for A-C when reconciliation/idempotency makes that achievable; zero blind retry for ambiguous class D; zero incorrect VERIFIED_SUCCESS**. Class D ambiguity must terminate as `OUTCOME_UNKNOWN/NEEDS_REVIEW`.

### V4 — Bounded-context / prompt-flatness benchmark
Generate synthetic tasks of 200, 500 and 1,000 actions with known Goal/Plan/Action/Fact/Recovery truth. Include irrelevant old events, superseded facts, failures, replans and recovery events.

Compare:
1. full transcript
2. rolling summary
3. structured bounded projection (proposed)
4. structured projection + advisory FTS retrieval

Measure:
- prompt tokens by action index
- p95 projection size
- exact reconstruction of current step/status
- stale/superseded fact errors
- recovery-decision correctness
- model latency when a model is included

Gate for proposed architecture: active correctness-critical projection remains bounded as trajectory grows; 1,000-action state reconstruction has **100% exact correctness on deterministic fields**. Retrieval may improve recall but must never override authoritative state.

### V5 — Local model + escalation benchmark
Run identical proposal/grounding fixtures on Apple Silicon 24 GB and RTX 4070 12 GB.

Baseline: Qwen3-VL-8B-Instruct at a practical local quantization. Challengers only where needed: UI-TARS-2B, ZonUI-3B, UGround-V1-2B. Do not benchmark a permanent critic until verifier-inconclusive cases show a measurable need.

Measure separately:
- typed-schema validity
- semantic TargetSpec selection
- correct abstention
- wrong-target rate
- visual grounding accuracy on semantic-gap cases
- verifier-confirmed task success
- p50/p95 first-token and total latency
- RAM/VRAM peak
- cold start
- repeated-run variance
- cache hit/miss latency

Decision rule: keep one generalist if it satisfies proposal quality/latency gates. Add a visual specialist only if it yields a material verifier-confirmed improvement on semantic-gap tasks after accounting for residency/latency. Model identity remains replaceable.

### V6 — Skill progressive-disclosure fixture
Create 10 real skills and 100 plausible decoys with overlapping names/descriptions. Compare:
1. inject all skill bodies
2. expose metadata only, then load selected skill
3. deterministic schema/capability filter -> metadata selection -> load selected skill

Inject malicious or over-broad candidate metadata to verify it cannot widen capability.

Metrics:
- correct skill selection
- false activation
- prompt tokens
- selection latency
- capability-policy violations
- regression success after skill version change

Gate: no capability widening; context growth sublinear to skill-body corpus size; schema-filtered progressive disclosure should match or exceed full-injection selection reliability while materially reducing prompt size.

### V7 — Security/authority-expansion fixture
Create untrusted browser/document/tool observations containing instructions that request:
- new recipients/domains
- filesystem paths outside task scope
- new tools/capabilities
- verifier bypass
- credential/secrets disclosure
- disabling safety checks

The model may repeat/propose these requests; deterministic policy must reject them unless independently authorized by original task scope.

Gate: **zero authority expansion from untrusted content in deterministic policy tests**. Injection classifiers are measured separately and never counted as the authorization boundary.

### V8 — Windows UIA hardware matrix
On the target Windows machine, reproduce the macOS capability discipline across representative Win32, WPF/WinUI, Electron, Chrome/Edge and custom-rendered surfaces. Measure discovery/read, invoke/value patterns, background/occluded behavior, focus/cursor interference, stale/rebuild behavior and independently verified mutation.

Gate: UIA remains a capability-gated semantic route, not a universal promise. Any app/action pair that cannot be independently verified is marked unsupported and escalates rather than assumed functional.

### V9 — Cross-app endurance + fault campaign
Only after V1-V8 contracts pass, run short/medium/long and cross-app tasks with injected popups, focus changes, slow operations, app/browser restarts, expired sessions, stale targets, malformed model output and user interruption.

Lengths: atomic, 5-20 actions, 20-100 actions, 150+, then 500+ synthetic endurance.

Report distributions, not one-run demos: task success, safe abstention, wrong action, recovery success, duplicate effects, model calls, route switches, tokens, latency and failure taxonomy.

Use external benchmarks only as complementary evidence. WindowsWorld's 2026 result that leading agents remain below 21% on multi-app workflows is a warning that single-app success is not sufficient evidence for universal-agent reliability.

## Minimum architecture gates before implementation expansion
1. Zero wrong/stale dispatch in deterministic grounding fault fixtures.
2. Zero verifier false-success in deterministic fault fixtures.
3. Crash matrix preserves side-effect safety semantics; ambiguity is surfaced, never guessed.
4. 1,000-action deterministic state reconstruction is exact while active projection stays bounded.
5. Deterministic policy blocks authority expansion regardless of model behavior.
6. Model baseline meets schema/latency/memory requirements on both target machines or is replaced behind the same interface.
7. Windows semantic route is measured on real target hardware.

## Implementation sequence implied by the tests
`controller schemas/event journal` -> `grounding fixture + TargetSpec resolver contract` -> `verifier predicates` -> `durable action transaction/recovery` -> `bounded state projector` -> `policy/capability gate` -> `model proposal adapter` -> `skill loader` -> `Windows UIA adapter` -> `endurance/cross-app campaign`.

This order intentionally proves deterministic contracts before adding more model autonomy.