# ComputerAgent Architecture Decision Ledger

This file records decisions that coding agents must not casually reverse. A decision may change when Phase 0 evidence disproves it; record the evidence and replacement explicitly.

## D-001 — Evolve BrowserAgentV2 rather than wholesale restart
**Status:** Accepted

Preserve useful reliability concepts: authoritative controller, durable event traces/state, independent verification, explicit handoff, provenance-bearing facts, loop detection, recovery/reconciliation, and refusal to blindly retry ambiguous state-changing actions.

## D-002 — ComputerAgent, not browser-only architecture
**Status:** Accepted

Broaden execution from BrowserKernel-only assumptions to an interaction fabric spanning native tools/APIs, browser semantics, desktop accessibility, visual grounding, isolation where supported, and human handoff.

## D-003 — No literal host “second mouse” as the core abstraction
**Status:** Accepted

Provide a second-cursor experience using cursorless semantic actions plus isolated coordinate interaction when supported. Generic host pointer injection is not the default.

## D-004 — Vision is an escalation path
**Status:** Accepted

Prefer deterministic/semantic representations when available. Screenshot/coordinate control exists for inaccessible/custom UI, not as the mandatory representation for every step.

## D-005 — Authoritative state lives outside the model
**Status:** Accepted

The model proposes decisions over bounded working context. Goal, plan, facts, events, artifacts, policy, verification, and recovery are application state.

## D-006 — Bounded context is a first-class requirement
**Status:** Accepted

Long task duration must not cause linear prompt growth. Retrieval and milestone state replace transcript accumulation.

## D-007 — State-changing actions use intent -> execute -> observe -> verify -> persist
**Status:** Accepted

On ambiguous restart, never blindly duplicate an external side effect.

## D-008 — Safety/policy is outside the model
**Status:** Accepted

Untrusted UI/web content cannot grant authority or rewrite user constraints. Consequential actions and authentication/security boundaries are governed by deterministic policy/handoff.

## D-009 — Hardware-adaptive inference
**Status:** Accepted

Probe physical resources and capabilities. Do not hard-code model selection by GPU name. Apple unified memory and laptop/desktop GPU differences require resource-aware profiles.

## D-010 — Model/runtime choice remains experimentally open
**Status:** Phase 0 gate

Do not commit to Qwen3-8B, UI-TARS, llama.cpp, Ollama, MLX, vLLM, or another candidate merely from reputation. Benchmark supported candidates under common fixtures and target hardware. Existing Qwen3-8B remains a useful control baseline.

## D-011 — Background safety is measured per route/action/app class
**Status:** Accepted

Use explicit capability metadata such as `BACKGROUND_PROVEN`, `BACKGROUND_BEST_EFFORT`, and `FOREGROUND_REQUIRED`. Never infer background safety from model confidence.

## D-012 — macOS and Windows are P0; Linux later
**Status:** Accepted

Cross-platform architecture begins immediately, but Linux is not required to block the first product validation.

## D-013 — Isolated desktop/workspace is capability-gated
**Status:** Accepted

Do not promise arbitrary local app/session duplication inside a VM or isolated environment. Use isolation where it is measured and practical; otherwise hand off or use a foreground-required route.

## D-014 — Repository Markdown is the development source of truth
**Status:** Accepted

`CLAUDE.md`, `PRODUCT.md`, `ARCHITECTURE.md`, `BUILD_SPEC.md`, `ROADMAP.md`, and this decision ledger provide operational context. Research PDFs remain supporting evidence.

## D-015 — Graphify is auxiliary developer memory only
**Status:** Accepted

Graphify may index repository documentation/code to improve Claude retrieval and cross-session navigation, but it is not authoritative state and is not required for ComputerAgent to build or run. Verify the exact Graphify implementation, license, setup, and security before installation. Keep it removable and do not commit secrets or generated private indexes.

## D-016 — Do not optimize architecture around example tasks
**Status:** Accepted

Examples are evaluation cases, not architecture specifications. New examples should become fixtures/benchmarks without causing ad-hoc core redesign unless they reveal a genuine general architectural gap.

---

## Decisions promoted from the overnight architecture red-team (`research/overnight-2026-09-18`)

The following were extracted from a 37-commit overnight research/red-team process on branch `research/overnight-2026-09-18` (`research/overnight/*.md`, especially `FINAL_ARCHITECTURE.md` and `ARCHITECTURE_DECISIONS.md`). That branch's own confidence figures are carried through below; they are the research process's self-assessed confidence, not proof. None of these decisions contradict D-001 through D-016 or measured Phase 0 evidence — they sharpen the existing routing/verification/state principles into concrete, testable contracts. See `docs/IMPLEMENTATION_PLAN.md` for the milestones (M1-M5) that validate each PLANNED item below.

## D-017 — No durable UniversalElement; TargetSpec -> TargetCandidate -> ExecutionRef
**Status:** Accepted (contract PLANNED, awaiting M1/Fixture A)

**Rationale:** Backend element identity is too ephemeral to unify across DOM/AX/UIA/vision — WebKit rebuilds AX nodes on mutation, a destroyed AX element correctly raises `kAXErrorInvalidUIElement` rather than returning stale content, and duplicate-labeled controls make role/name alone insufficient. A durable cross-route element would either paper over these incompatible lifetimes or silently misfire.
**Evidence/status:** Directly supported by `phase0/CAMPAIGN_REPORT.md` §D (stale-element fixture: 10/10 correct rejection) and `phase0/MAC_APP_CAPABILITY_REPORT.md` (WebKit AX node rebuild on mutation). Overnight research (ADR-O7, 95% confidence) converges on the same conclusion from external evidence (BrowserGym-style ephemeral IDs, ComponentBench, Agent S). Not yet implemented — this is the contract M1/Fixture A exists to falsify.
**Consequences:** `TargetSpec` stores only semantic intent (app/window hint, role, name, text hint, state constraints, relation, ordinal) — never a DOM/AX/UIA handle or coordinate. `TargetCandidate` is observation-local evidence with provenance/confidence. `ExecutionRef` is opaque, adapter-local, and valid only for the observation version that produced it. Resolution outcomes are `RESOLVED`/`AMBIGUOUS`/`ABSENT`/`STALE`/`UNSUPPORTED`; ambiguity and absence must abstain, never guess.

## D-018 — Independent, typed verification is mandatory before step advancement
**Status:** Accepted (elaborates D-007; predicate vocabulary PLANNED, awaiting M2/Fixture B)

**Rationale:** Adapter/API return success is not task success. A plan must not advance on an unverified claim.
**Evidence/status:** M2 gate PASSED on synthetic Fixture B (`computer_agent/M2_VERIFICATION_REPORT.md`, 0 false successes). Originally motivated by direct measurement — `phase0/MAC_APP_CAPABILITY_REPORT.md` §G: Chrome's `AXPress` on a plain HTML button returns AX success (error code 0) but never fires the page's click handler, while the identical mechanism works on Safari. This is a real, reproduced false-success case, not a hypothetical. Overnight research (ADR-O2, 97% confidence) independently converges on structured/environment-state verification over API-return or model self-judgment.
**Consequences:** Every state-changing adapter/skill carries a `VerificationSpec` with a small compositional predicate vocabulary (equality/inequality, existence/absence, membership/contains, numeric/range, count/delta, before->after transition, invariant-not-changed, AND/OR, bounded domain callback) evaluated against evidence independent of the action's own return value. Outcome vocabulary is `VERIFIED_SUCCESS` / `VERIFIED_FAILURE` / `INCONCLUSIVE` / `PARTIAL_SUCCESS` / `UNEXPECTED_SIDE_EFFECT`. `INCONCLUSIVE` must never silently become success anywhere in the pipeline.

## D-019 — SQLite WAL append-only event journal is the production durable state store
**Status:** Accepted (elaborates D-005/D-006; PLANNED, awaiting M3/Fixture C)

**Rationale:** Correctness-critical state needs transactional durability and crash-safe replay. Phase 0's JSONL evidence files are the right shape for experiment evidence but were never meant to be a transactional recovery journal.
**Evidence/status:** M3 gate PASSED on synthetic Fixture C incl. real SIGKILL (`computer_agent/M3_CONTROLLER_RECOVERY_REPORT.md`); SQLite WAL + synchronous=FULL, append-only events with deterministic UNIQUE event IDs, pure-fold materialization. Power-loss durability untested. Overnight research (ADR-O9/O15) argues from long-horizon-agent and durable-workflow literature; the specific choice of SQLite+WAL for a single-machine v1 (vs. e.g. a distributed workflow engine) is an engineering default pending evidence it's insufficient.
**Consequences:** Do not grow `phase0/harness/` (`ExperimentRunner`, JSONL persistence) into the production controller — it stays an independent measurement harness. Production state lives in a new `computer_agent/` package: append-only event journal (SQLite, WAL mode) plus deterministic materialized state, with a bounded finite event vocabulary (`ACTION_INTENT_PERSISTED`, `DISPATCH_STARTED`, `VERIFICATION_RECORDED`, etc.). Optional OpenTelemetry/JSONL exports are derived views; disabling them must never change recovery behavior.

## D-020 — No generic exactly-once claim for external/UI side effects
**Status:** Accepted (elaborates D-007; PLANNED, awaiting M3/Fixture C)

**Rationale:** A crash between "external effect committed" and "local result durably recorded" is an unavoidable ambiguity for non-transactional external systems (the same property distributed-workflow systems like Temporal document for at-least-once activity execution). Claiming exactly-once here would be false.
**Evidence/status:** Fault-injection tested in M3 (12 crash boundaries × 4 classes, 0 blind class-D retries, 0 duplicates) — `computer_agent/M3_CONTROLLER_RECOVERY_REPORT.md`. Argued from general distributed-systems literature (ADR-O10, 97% confidence) rather than BrowserAgentV2-specific evidence, but the underlying constraint is not model- or platform-specific.
**Consequences:** Recovery classifies every unresolved action into one of four classes: (A) idempotency-key capable -> retry/reconcile with the same logical `action_id`; (B) externally queryable -> query before retry; (C) naturally idempotent state-set -> verify current state, repeat only if still needed; (D) non-idempotent and non-queryable -> `OUTCOME_UNKNOWN`/`NEEDS_REVIEW`, **never** automatically retried. A stable logical `action_id` is persisted before dispatch in every case.

## D-021 — Deterministic capability gate; authority and information are separate channels
**Status:** Accepted (elaborates D-008; PLANNED, awaiting M5/Fixture D)

**Rationale:** A model that consumes attacker-controlled webpage/document/tool content cannot be the root of its own authorization, and a prompt-injection classifier has false negatives by construction — it can only be a defense-in-depth layer, never the authorization boundary.
**Evidence/status:** Not yet fixture-tested in this repository (M5 unimplemented). Overnight research (ADR-O11, 96% confidence) cites OWASP agent guidance and a disclosed 2026 Anthropic red-team case where model-layer intent defenses did not stop a user-delivered exfiltration prompt while environment-level filesystem/network boundaries would have. This is external evidence, not a BrowserAgentV2-specific measurement.
**Consequences:** Every consequential `ActionIntent` passes a non-LLM policy gate (`ALLOW`/`DENY`/`REQUIRE_CONFIRMATION`/`REQUIRE_REPLAN`) scoped to task-granted capabilities (allowed app/domain, filesystem prefixes, recipient set, action classes, confirmation requirement). Content from webpages, DOM, AX/UIA, screenshots, OCR, documents, tool output, model output, and retrieved memory is evidence only and can never widen scope, regardless of what it asks for.

## D-022 — One durable deterministic controller; models are bounded proposal functions only
**Status:** Accepted (direction; PLANNED for full implementation across M1-M6)

**Rationale:** Separate autonomous planner/executor/recovery/supervisor agents duplicate state, create conflicting authority, and add context-handoff surface without solving durability or recovery — the durable controller state machine already provides the specialization boundary these agents would exist to provide.
**Evidence/status:** Architecture synthesis (ADR-O12, 94% confidence) grounded in the failure evidence behind D-017 through D-021, not a separate direct measurement.
**Consequences:** The controller (`computer_agent/controller.py`) owns Goal/Plan/Step/Action/Recovery lifecycle, retry/route-switch budgets, target freshness requirements, verification requirements, the durable journal, crash reconciliation, and bounded model-context projection. Models may propose plans/replans, `TargetSpec`s, arguments, interpretations of ambiguous observations, and optional visual grounding candidates. Models may never authorize themselves, expand task scope, declare durable success, or own recovery state.

## D-023 — Model architecture starts with one replaceable multimodal ~8B generalist
**Status:** Accepted (elaborates D-010; UNVALIDATED — no hardware benchmark run yet, gated on M6)

**Rationale:** Because routing already prefers deterministic APIs, Playwright/CDP, and AX/UIA before any model-driven visual step, the local model does not need to be a primary pixel controller. An always-on planner+grounder+critic ensemble is unnecessary residency/latency cost until a measured semantic gap justifies it.
**Evidence/status:** Qwen3-VL-8B-Instruct is named as the **first benchmark candidate** (overnight ADR-O13: 88% confidence in the architecture, only 76% confidence in this specific model as the eventual choice) because it is the highest-information locally-deployable option (multimodal, computer-use/grounding/tool support, official 8B GGUF path) — this is a benchmark-selection rationale, not a measured result. No local model has been benchmarked on the target M5/RTX 4070 hardware in this repository. D-010's existing "experimentally open" status is unchanged; this decision only narrows which candidate gets benchmarked first.
**Consequences:** M6 benchmarks Qwen3-VL-8B-Instruct first on Apple Silicon M5 (24 GB) and RTX 4070 (12 GB). A 2-3B GUI grounder (UI-TARS-2B first) is added only if semantic-gap fixtures show a material verifier-confirmed improvement after accounting for latency/residency. A critic model is added only for measured verifier-inconclusive cases. No model choice may be promoted to fact before that benchmark runs.

## D-024 — Skills are versioned progressive-disclosure procedures, never auto-promoted from trajectories
**Status:** Accepted (direction; PLANNED, no target milestone before M9)

**Rationale:** A successful trajectory may contain an accidental workaround, a stale selector, or an unsafe authority assumption; auto-promoting it into trusted executable code would bypass the same verification/policy contracts every other action goes through.
**Evidence/status:** Architecture synthesis (ADR-O14, 93% confidence), citing Anthropic's Agent Skills and OpenHands' extension registries as external precedent for metadata-first progressive disclosure. Not yet implemented in this repository.
**Consequences:** A skill declares typed inputs, required capabilities, preconditions, a procedure/helpers entry point, a postcondition verifier (same contract as D-018), a safety-invariant set, an idempotency classification (same classes as D-020), and regression fixtures. Only compact metadata is normally visible to the model; full procedure detail loads on selection. Promotion of a successful trajectory into a trusted skill requires explicit review and regression tests — it is never automatic, and untrusted content can never create or promote a skill.

## D-025 — Developer Console is observational/debug UI, not authoritative state
**Status:** Accepted (direction; console may begin as early as M1)

**Rationale:** Visible execution state materially speeds up debugging and testing during M1-M9, but a console that becomes load-bearing for correctness would violate D-022 (controller owns state) and make the backend untestable headlessly.
**Evidence/status:** Direction, not measured — no console exists yet.
**Consequences:** The console visualizes backend-authoritative state (active task, current step, observation/version, `TargetSpec`/`TargetCandidate`s, resolution/freshness results, selected route, action intent, dispatch/verification results, recovery state, event timeline, abstention reasons) read-only. It is distinct from the Phase 2 consumer product UI (`docs/ROADMAP.md` Phase 2) and must never be required for the backend's headless test suite to pass.

## D-026 — Developer Console v0 is a stdlib HTTP server + one static HTML page
**Status:** Accepted (replaceable; dev tooling only)

**Rationale:** No UI technology was frozen. The smallest local option that runs on this Mac, needs no dependency/build step/cloud, and consumes structured backend output is Python's `http.server` serving a single vanilla-JS page that renders JSON generically. Anything heavier (a web framework, Electron/Tauri, a JS toolchain) would be product architecture ahead of M11.
**Evidence/status:** Implemented in `devconsole/` with M1/M2/M3 views; contract tests (`tests/devconsole/`) show every rendered verdict equals the backend's, no opaque handle leaks, and `computer_agent/` never imports the console. All M1-M3 gates run with the console absent.
**Consequences:** Views (`devconsole/views.py`) only serialize backend/harness results; the page never computes truth. The console imports the test fixtures to run trials — acceptable for a developer tool, and a reason it is not the product UI. It can be replaced wholesale without touching `computer_agent/`.
