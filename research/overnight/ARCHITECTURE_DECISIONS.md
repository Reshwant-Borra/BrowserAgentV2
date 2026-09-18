# Overnight Architecture Decisions

These are provisional evidence-backed ADRs for the overnight mission. Confidence can move as later runs add experiments.

## ADR-O1 — Hybrid semantic-first control, visual fallback
**DECISION:** Use deterministic/native tools when available, Playwright/CDP for browser semantics, platform accessibility for desktop semantics, then visual grounding/coordinate input only for semantic gaps. Foreground physical input is a capability-gated last resort, not the universal default.
**CONFIDENCE:** 94%
**EVIDENCE:** BrowserAgentV2 browser campaign verified 500/500 semantic postconditions with zero cursor/foreground movement; macOS app survey found rich semantic AX read surfaces but real action gaps; OSWorld shows pixels/accessibility both fail; strong systems benefit from hybrid non-GUI tools.
**ALTERNATIVES:** pixel-only; AX-for-everything; bespoke app integrations.
**WHY REJECTED:** pixel-only discards deterministic semantics/background control; AX is not universal; bespoke integrations do not scale.
**RISKS:** route appears available but is behaviorally broken; visual fallback unbenchmarked.
**HOW TO VALIDATE:** capability/routing benchmark across semantic-first, visual-first, hybrid; custom/canvas/Electron/stale cases.

## ADR-O2 — Verification is a first-class contract
**DECISION:** Every state-changing skill/adapter must expose/construct a postcondition verifier independent of API return and model success claim. Prefer structured app state; probabilistic visual/model verification only when deterministic state is unavailable.
**CONFIDENCE:** 97%
**EVIDENCE:** Direct Chrome AXPress false-success; structured/environment-state verification research.
**ALTERNATIVES:** trust API/model; screenshot-difference only.
**WHY REJECTED:** no-op success and shared failure modes.
**RISKS:** arbitrary verifiers can become app-specific.
**HOW TO VALIDATE:** typed predicate fault injection; zero false success on controlled fixtures.

## ADR-O3 — Re-resolve semantic targets after mutation
**DECISION:** Persist semantic target description, not DOM/AX handles; re-resolve against fresh observation.
**CONFIDENCE:** 95%
**EVIDENCE:** BrowserAgentV2 observed WebKit AX node rebuilding and explicit stale AX behavior.
**ALTERNATIVES:** durable handles; coordinates.
**WHY REJECTED:** dynamic replacement/reflow.
**RISKS:** duplicate-label ambiguity.
**HOW TO VALIDATE:** replace/reorder duplicate controls; require correct re-grounding/abstention.

## ADR-O4 — Repeated-trial reliability is a release metric
**DECISION:** Evaluate task classes over repeated executions and report distributions/failure taxonomy.
**CONFIDENCE:** 92%
**EVIDENCE:** stochastic agent reliability research plus BrowserAgentV2 campaigns.
**ALTERNATIVES:** one canonical run/headline aggregate.
**WHY REJECTED:** hides variance/state leakage.
**RISKS:** evaluation cost.
**HOW TO VALIDATE:** repeated trials by task risk/length.

## ADR-O5 — Do not freeze a multi-model architecture yet
**DECISION:** Benchmark one general decision model plus optional grounder/critic escalation; add permanent specialists only when measured gains justify overhead.
**CONFIDENCE:** 88%
**EVIDENCE:** specialists can improve grounding while local-CUA research shows decomposition overhead/diminishing returns; no common local fixture benchmark yet.
**ALTERNATIVES:** always-on planner/executor/verifier; one end-to-end model forever.
**WHY REJECTED:** premature without hardware evidence.
**RISKS:** baseline underperforms; specialist routing fails.
**HOW TO VALIDATE:** common fixtures on M5 24 GB and RTX 4070 12 GB.

## ADR-O6 — Safety invariants accompany success predicates
**DECISION:** Consequential verification checks prohibited effects/invariants as well as desired state; policy authority remains deterministic.
**CONFIDENCE:** 93%
**EVIDENCE:** state-based safety benchmarks show goal success can coexist with unsafe shortcuts.
**ALTERNATIVES:** action guard only; success verifier only.
**WHY REJECTED:** misses unsafe success paths.
**RISKS:** incomplete invariant coverage.
**HOW TO VALIDATE:** adversarial fixtures where easiest route violates constraint.

## ADR-O7 — No durable universal element
**DECISION:** `TargetSpec` semantic intent -> fresh `TargetCandidate` with provenance/confidence -> opaque observation-local adapter `ExecutionRef`.
**CONFIDENCE:** 95%
**EVIDENCE:** direct staleness/rebuild evidence; GUI systems use observation-local IDs/separate grounding.
**ALTERNATIVES:** persistent UniversalElement; durable coordinates/handles.
**WHY REJECTED:** incompatible identity/lifetime semantics.
**RISKS:** ambiguous re-resolution.
**HOW TO VALIDATE:** duplicate/reorder/replacement/reflow/overlay/cross-route/canvas fixtures.

## ADR-O8 — Pre-dispatch freshness gate
**DECISION:** Consequential actions revalidate app/window/target immediately before dispatch.
**CONFIDENCE:** 89%
**EVIDENCE:** direct stale handles + GUI TOCTOU research.
**ALTERNATIVES:** observe once; postcondition-only.
**WHY REJECTED:** wrong irreversible action may happen before verification.
**RISKS:** latency/false abstention.
**HOW TO VALIDATE:** inject overlay/focus/window changes between grounding and dispatch.

## ADR-O9 — Structured authoritative execution state; retrieval advisory
**DECISION:** Goal/Plan/Action/Recovery state and append-only event journal live outside model. Model gets bounded structured projection plus selective facts. Retrieval never determines completion/effect truth.
**CONFIDENCE:** 95%
**EVIDENCE:** long-horizon context research and execution-dependency mismatch of semantic retrieval.
**ALTERNATIVES:** full transcript; rolling summary only; vector DB as task state.
**WHY REJECTED:** growth, drift, stale/approximate retrieval.
**RISKS:** omitted needed fact.
**HOW TO VALIDATE:** 200/500/1,000 action prompt-flatness/reconstruction benchmark.

## ADR-O10 — Durable action intent + reconciliation; no generic exactly-once UI claim
**DECISION:** Persist stable action ID/intent before dispatch; use idempotency keys or reconciliation; ambiguous irreversible non-idempotent effects become outcome unknown and are never blind-retried.
**CONFIDENCE:** 97%
**EVIDENCE:** distributed/durable workflow commit-ack window; arbitrary GUI effects cannot transact with local journal.
**ALTERNATIVES:** retry last step; checkpoint only; process-local exactly once.
**WHY REJECTED:** duplicate side effects.
**RISKS:** some effects require handoff/domain compensation.
**HOW TO VALIDATE:** injected crash matrix across action classes.

## ADR-O11 — Authority/information separation + deterministic capability gate
**DECISION:** Untrusted observations may provide information but never increase authority. Every consequential `ActionIntent` passes deterministic task-scoped capability/policy checks outside the model.
**CONFIDENCE:** 96%
**EVIDENCE:** OWASP agent guidance; containment/prompt-injection evidence; BrowserAgentV2 requires scope controls independent of model compliance.
**ALTERNATIVES:** injection detector as root defense; planner decides safety; ambient all-tool access.
**WHY REJECTED:** model consumes attacker-controlled content and detection has false negatives.
**RISKS:** initial capability schema can be too coarse/strict.
**HOW TO VALIDATE:** adversarial authority-expansion/data-flow fixtures independent of model compliance.

## ADR-O12 — One durable deterministic controller, models as bounded proposal functions
**DECISION:** Controller owns lifecycle, retries, route switches, policy, verification, persistence and handoff. Models propose plans/targets/arguments/replans only.
**CONFIDENCE:** 94%
**EVIDENCE:** durable state already supplies coordination boundaries; multi-agent hierarchy adds context handoffs/authority conflicts without solving recovery.
**ALTERNATIVES:** autonomous planner/executor/recovery/supervisor agents.
**WHY REJECTED:** duplicated state, conflicting authority, harder failure attribution.
**RISKS:** controller transition table may become complex.
**HOW TO VALIDATE:** fault injection by failure class; state-machine invariant violations target zero.

## ADR-O13 — Start local model evaluation with one multimodal 8B generalist
**DECISION:** Benchmark Qwen3-VL-8B-Instruct first as the general proposal model, with UI-TARS-2B/ZonUI-3B/UGround-V1-2B as visual-only escalation candidates and critic-on-inconclusive only. Model identity remains replaceable behind schema.
**CONFIDENCE:** 88% for architecture, 76% for Qwen3-VL-8B as final model.
**EVIDENCE:** official Qwen3-VL exposes computer-use/grounding/tool capability and 8B local checkpoints; specialist grounding benchmarks are strong but BrowserAgentV2 mostly acts through deterministic semantic routes.
**ALTERNATIVES:** text-only generalist + mandatory VLM; always-on ensemble; specialist as primary controller.
**WHY REJECTED:** unnecessary model residency/context/latency before measured need.
**RISKS:** Q4 visual/tool quality or target-hardware latency may be inadequate.
**HOW TO VALIDATE:** common fixture benchmark on both target machines including schema validity, abstention, wrong-target, p95 latency, memory and repeated variance.

## ADR-O14 — Skills are versioned progressive-disclosure procedures, not sub-agents
**DECISION:** Skills package metadata, typed inputs, capabilities, preconditions, procedure/helpers, verifier/invariants and regression fixtures. Only metadata is normally visible; details load on selection. Controller executes/composes them.
**CONFIDENCE:** 93%
**EVIDENCE:** Agent Skills and OpenHands converge on reusable on-demand procedural context; progressive disclosure directly fits bounded-context architecture.
**ALTERNATIVES:** one agent per skill; vector-retrieval-to-execution; full skill library in prompt; auto-promote successful traces.
**WHY REJECTED:** state/authority duplication, prompt growth, unsafe applicability and brittle trace reuse.
**RISKS:** manifest overdesign; skill trigger misses.
**HOW TO VALIDATE:** 10 real skills + 100 decoys; compare full injection vs metadata disclosure vs schema-filtered routing.

## ADR-O15 — Durable event journal is source of truth; OpenTelemetry is derived observability
**DECISION:** Persist a compact typed controller event journal for recovery/audit and correlate it with optional OpenTelemetry-compatible spans/metrics. OTel export, sampling, or failure must never affect behavior or recovery.
**CONFIDENCE:** 94%
**EVIDENCE:** Existing Phase 0 already benefits from structured evidence records; OpenTelemetry GenAI conventions cover agent/model/tool spans, tokens and latency while its guidance recommends bounded high-value attributes and opt-in handling for verbose/sensitive content.
**ALTERNATIVES:** raw transcript logs; OTel backend as recovery store; unstructured debug logging only.
**WHY REJECTED:** transcripts are large/ambiguous/sensitive; telemetry exporters are not transactional state; unstructured logs make deterministic fault diagnosis difficult.
**RISKS:** schema overgrowth; artifact storage volume; accidental sensitive capture.
**HOW TO VALIDATE:** failure-class trace reconstruction, OTel-disabled recovery equivalence, 1,000-action storage test, sensitive-string leak test.

## ADR-O16 — Falsify deterministic contracts before optimizing end-to-end agent score
**DECISION:** Build validation in this order: grounding freshness/abstention -> verifier false-success resistance -> crash reconciliation -> bounded-state reconstruction -> authority gate -> model/escalation -> skills -> Windows UIA -> cross-app endurance. Deterministic safety/correctness gates precede benchmark chasing.
**CONFIDENCE:** 96%
**EVIDENCE:** BrowserAgentV2's strongest evidence comes from controlled repeated campaigns; current cross-app GUI benchmarks remain weak enough that headline task success can hide wrong-action/recovery defects; direct Chrome AXPress false-success demonstrates why end-to-end completion alone is insufficient.
**ALTERNATIVES:** build full agent first and tune OSWorld/WebArena score; optimize model before controller contracts.
**WHY REJECTED:** failures become entangled and model capability can mask state/verification defects without fixing them.
**RISKS:** slower visible demo progress; deterministic fixture gates may be initially too strict.
**HOW TO VALIDATE:** execute `VALIDATION_PLAN.md`; architecture-changing failure must map to a specific contract and reproducible fixture before redesign.