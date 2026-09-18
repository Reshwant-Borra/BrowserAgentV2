# Overnight Research Ledger

This file is the continuity handoff between scheduled research runs.

## Rules
- Read this file before starting new research.
- Do not repeat a source/question unless prior evidence is inadequate or contradictory.
- Append meaningful findings rather than replacing history.
- Update the current architecture hypothesis and unresolved questions after every run.
- Record negative results and failed hypotheses.

## Current Architecture Hypothesis
Preserve BrowserAgentV2's reliability-first Phase 0 harness. Production direction is a **hybrid semantic-first, verifier-grounded ComputerAgent**: deterministic tools/APIs when available -> Playwright/CDP browser semantics -> platform accessibility -> visual grounding/coordinate fallback -> foreground/handoff. A single durable deterministic controller owns Goal/Plan/Action/Policy/Recovery state, lifecycle, retry budgets and an append-only journal. Models are bounded proposal functions, not authorities. Untrusted observations supply information but cannot increase authority; consequential ActionIntents pass deterministic task-scoped capability/policy gates. Model context is a bounded projection of current durable state plus selected facts; retrieval memory is advisory. Every state-changing action is a durable intent transaction with stable logical action ID; crash recovery reconciles uncertain effects before retry and never claims generic exactly-once execution. Targets use semantic `TargetSpec` -> fresh observation-local candidate -> ephemeral backend ExecutionRef. Verification uses typed predicates/invariants and explicit inconclusive/unsafe outcomes. Start local evaluation with one replaceable multimodal ~8B generalist (Qwen3-VL-8B-Instruct first benchmark), specialist GUI grounder only on measured escalation, and critic only on verifier-inconclusive cases if justified. Reusable skills are versioned progressive-disclosure procedures under the controller, never autonomous sub-agents. Observability uses the durable event journal as source of truth plus optional correlated OpenTelemetry traces/metrics; telemetry is never recovery state.

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
- **Finding:** Long-horizon research converges on selective/structured context rather than append-only transcripts. Correctness-critical Goal/Plan/Action/Recovery state must be structured and authoritative outside model; retrieval is advisory/provenanced.
- **Evidence quality:** 3-4, architecture reasoning 5
- **Impact:** structured durable state + bounded working projection; start SQLite/FTS; no vector DB until benchmark.
- **Validation:** 200/500/1,000 action prompt-flatness/reconstruction benchmark.

### 2026-09-18 02:xx ET — Crash reconciliation / durable side effects
- **Finding:** No generic exactly-once guarantee exists across arbitrary external/UI effects. Crash after external commit but before local result persistence creates ambiguity unless external idempotency/reconciliation exists.
- **Evidence quality:** 4
- **Impact:** stable action_id; persist intent before dispatch; idempotency/reconcile before retry; ambiguous irreversible non-idempotent -> OUTCOME_UNKNOWN/NEEDS_REVIEW.
- **Validation:** injected crash matrix >=1,000 randomized trials/action class.

### 2026-09-18 03:xx ET — Security/policy trust boundary
- **Finding:** Separate authority from information. Web/DOM/AX/UIA/screenshot/OCR/document/tool/model content is untrusted evidence and cannot widen capability. Prompt-injection detection is defense-in-depth, not authorization.
- **Evidence quality:** 3-4 plus architecture reasoning
- **Impact:** deterministic ActionIntent capability/policy gate, provenance/data-flow controls, task-scoped authority, separate success/safety invariants.
- **Validation:** adversarial authority-expansion and sensitive-read/external-write fixtures.

### 2026-09-18 03:xx ET — Planner/recovery controller
- **Finding:** Separate autonomous planner/executor/recovery agents add state handoffs without solving durability. Use one durable deterministic controller with typed lifecycle/failure transitions; models propose only.
- **Evidence quality:** architecture synthesis grounded in prior direct failure evidence
- **Impact:** retry/re-ground/route-switch/replan/handoff are deterministic transitions with bounded budgets; replans version history.
- **Validation:** failure-class fault injection and state-machine invariant tests.

### 2026-09-18 05:xx ET — Local model/routing
- **Finding:** Qwen3-VL now has an official 8B Instruct model, local GGUF path, computer-use/grounding capability and tool interfaces. Because BrowserAgentV2 is semantic-first, the general model need not be the primary pixel controller. Start with one multimodal 8B generalist baseline; compare optional 2-3B GUI specialists only on semantic gaps. Keep critic probabilistic and on-demand. Use stable-prefix/bounded-state prompting and measure prompt/KV caching rather than expanding context.
- **Evidence quality:** 2-4; final hardware suitability unmeasured
- **Impact:** narrows v1 model architecture substantially; no always-on ensemble, learned router or mandatory critic. Qwen3-VL-8B is benchmark candidate, not permanent dependency.

### 2026-09-18 05:xx ET — Reusable skills
- **Finding:** Skills should be versioned packages with metadata, typed inputs, capability envelope, preconditions, procedure/helpers, verifier/invariants and regression fixtures. Controller executes; model can select but cannot widen authority. Successful traces are candidates, not automatically executable skills.
- **Evidence quality:** 2-4 plus architecture fit
- **Impact:** progressive disclosure reduces repeated reasoning while preserving bounded context and deterministic authority.

### 2026-09-18 06:xx ET — Validation/fault-injection convergence
- **Finding:** Architecture discovery is sufficiently mature to define falsification gates. The cheapest/highest-value implementation order is grounding freshness/abstention -> verifier false-success resistance -> crash reconciliation -> bounded-state reconstruction -> authority gate -> model/escalation -> skills -> Windows UIA -> cross-app endurance. Deterministic controller contracts should be proven before optimizing external benchmark score.
- **Evidence quality:** 5 for reuse of existing Phase 0 verification discipline; 3-4 external benchmark/failure evidence; architecture synthesis
- **Impact:** created `VALIDATION_PLAN.md` with explicit fixtures, metrics, pass gates and stop conditions. Critical controlled-fixture gates target zero wrong/stale dispatch, zero verifier false-success, no blind retry of ambiguous non-idempotent effects, exact deterministic state reconstruction at 1,000 actions, and zero authority expansion from untrusted content.

### 2026-09-18 06:xx ET — Observability contract
- **Finding:** Durable journal and operational telemetry have different jobs. Correctness/recovery events must never be sampled; OTel-compatible traces/metrics are a derived view and may be disabled without changing behavior. Raw prompts/screenshots/tool outputs are too sensitive/large for default trace attributes.
- **Evidence quality:** 4-5 architecture fit + OpenTelemetry primary documentation
- **Impact:** added `OBSERVABILITY.md`; canonical task/plan/step/action/attempt/observation/verification/model/skill IDs and finite event vocabulary. Start SQLite + artifact references + JSONL/optional OTel; no distributed tracing stack required for v1.

### 2026-09-18 07:xx ET — Falsification-first vertical slice
- **Finding:** Direct inspection of `phase0/harness/runner.py`, `persistence.py`, and the existing unit-test layout supports a clean boundary: keep Phase 0 as measurement substrate and create a separate production `computer_agent/` package. The smallest useful slice is model-free: typed TargetSpec/ObservationVersion, deterministic freshness/abstention, independent verifier, durable journal/controller, policy gate, and crash reconciliation fixtures.
- **Evidence quality:** 5 for repository fit; architecture synthesis for proposed package boundary.
- **Impact:** created `VERTICAL_SLICE_BUILD_SPEC.md` with exact files, invariants, fixtures, gates, and stop conditions; created `OPEN_QUESTIONS.md` classifying remaining uncertainty. Do not grow `ExperimentRunner` into production runtime and do not treat JSONL experiment evidence as the recovery journal.
- **Validation:** first engineering task is pure-Python mutable-UI fixture + grounding freshness gate, >=1,000 seeded trials, zero wrong/stale dispatch and abstention on ambiguity/absence.

## Decisions Recorded
See `ARCHITECTURE_DECISIONS.md`:
- ADR-O1 hybrid semantic-first control — 94%
- ADR-O2 typed independent verification — 97%
- ADR-O3 re-resolve targets after mutation — 95%
- ADR-O4 repeated-trial reliability metric — 92%
- ADR-O5 no frozen multi-model architecture — 88%
- ADR-O6 safety invariants with success predicates — 93%
- ADR-O7 no durable universal element — 95%
- ADR-O8 pre-dispatch freshness gate — 89%
- ADR-O9 structured authoritative execution state — 95%
- ADR-O10 durable intent + reconciliation — 97%
- ADR-O11 authority/information separation + deterministic capability gate — 96%
- ADR-O12 one durable deterministic controller — 94%
- ADR-O13 multimodal 8B generalist baseline + measured escalation — 88% architecture / 76% final Qwen3-VL choice
- ADR-O14 progressive-disclosure versioned skills — 93%
- ADR-O15 durable journal source of truth + derived OTel — 94%
- ADR-O16 falsify deterministic contracts before benchmark optimization — 96%

## Current Highest-Priority Unresolved Questions
1. **Grounding fixture implementation:** can the proposed TargetSpec/freshness/abstention contract achieve zero wrong/stale dispatch in seeded faults?
2. **Verifier vocabulary coverage:** can a small predicate vocabulary cover representative tasks without app-specific DSL explosion?
3. **Crash harness implementation:** prove recovery classifications with injected process death across every action boundary.
4. **Prompt-flatness implementation:** prove exact deterministic reconstruction and bounded projection at 200/500/1,000 actions.
5. **Model hardware benchmark:** Qwen3-VL-8B and optional visual specialists on actual M5 24 GB + RTX 4070 12 GB.
6. **Windows hardware capability matrix:** reproduce UIA assumptions on the target Windows machine.
7. **Skill fixture:** measure progressive disclosure with decoys and policy boundaries.
8. **External benchmark mapping:** select a small representative OSWorld/WindowsWorld/web subset only after controller contracts pass.

## Negative Results / Assumptions Rejected
- Raw AX/UIA availability cannot be assumed behaviorally reliable or background-safe.
- Semantic object handles cannot be durable across UI mutation.
- Pixel-only is not automatically best because frontier CUAs use it.
- More context, more steps, or more model stages are not monotonic reliability improvements.
- One successful benchmark trajectory is not reliability evidence.
- Durable cross-backend UniversalElement is wrong abstraction.
- Screenshot difference alone is not semantic success verification.
- Post-action verification alone is insufficient for high-risk actions.
- Full transcript is not long-horizon memory architecture.
- Vector/semantic retrieval must not be authoritative execution state.
- Rolling summary alone is insufficient for recovery/audit correctness.
- Checkpoint-after-step does not provide exactly-once external effects.
- Ambiguous non-idempotent external effects must not be blind-retried.
- LLM nondeterminism must not be silently replayed as deterministic history.
- Prompt-injection classifier cannot be root authorization boundary.
- Separate autonomous planner/executor/recovery agents are unnecessary in v1.
- Always-on planner+grounder+critic ensemble is premature.
- Maximum model context should not be treated as a memory target.
- Vector similarity must not directly activate executable skills.
- Successful trajectories must not auto-promote into trusted executable skills.
- OpenTelemetry/exported traces must not be used as recovery state.
- Raw transcript/full screenshot capture is not an acceptable default observability strategy.
- External benchmark score should not precede deterministic contract validation.
- Phase 0 `ExperimentRunner` should not be mutated into the production controller; preserve it as an independent measurement harness.
- Phase 0 JSONL result persistence is experiment evidence, not transactional recovery state.

## Handoff
Broad architecture research is saturated enough for final convergence. New artifacts: `VERTICAL_SLICE_BUILD_SPEC.md`, `OPEN_QUESTIONS.md`, and `RUN8_HANDOFF.md`. **Do not perform another broad survey in the final pass.** Review all evidence/ADRs for contradictions, red-team the coherent candidate architecture, and produce the required final architecture/build/report artifacts. Be explicit that V1-V8 are specified but not yet executed. The strongest remaining blockers are implementation-validation blockers, not currently known architecture-design blockers. The single next engineering task is Fixture A: implement the minimal TargetSpec/ObservationVersion/freshness contract and run >=1,000 seeded mutation trials before model integration.