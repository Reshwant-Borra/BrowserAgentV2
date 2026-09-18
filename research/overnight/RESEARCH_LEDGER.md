# Overnight Research Ledger

This file is the continuity handoff between scheduled research runs.

## Rules
- Read this file before starting new research.
- Do not repeat a source/question unless prior evidence is inadequate or contradictory.
- Append meaningful findings rather than replacing history.
- Update the current architecture hypothesis and unresolved questions after every run.
- Record negative results and failed hypotheses.

## Current Architecture Hypothesis
Preserve BrowserAgentV2's reliability-first Phase 0 harness. Production direction is a **hybrid semantic-first, verifier-grounded ComputerAgent**: deterministic tools/APIs when available -> Playwright/CDP browser semantics -> platform accessibility -> visual grounding/coordinate fallback -> foreground/handoff. A single durable deterministic controller owns Goal/Plan/Action/Policy/Recovery state, lifecycle, retry budgets and an append-only journal. Models are bounded proposal functions, not authorities. Untrusted observations supply information but cannot increase authority; consequential ActionIntents pass deterministic task-scoped capability/policy gates. Model context is a bounded projection of current durable state plus selected facts; retrieval memory is advisory. Every state-changing action is a durable intent transaction with stable logical action ID; crash recovery reconciles uncertain effects before retry and never claims generic exactly-once execution. Targets use semantic `TargetSpec` -> fresh observation-local candidate -> ephemeral backend ExecutionRef. Verification uses typed predicates/invariants and explicit inconclusive/unsafe outcomes. Start local evaluation with one replaceable multimodal ~8B generalist (Qwen3-VL-8B-Instruct first benchmark), specialist GUI grounder only on measured escalation, and critic only on verifier-inconclusive cases if justified. Reusable skills are versioned progressive-disclosure procedures under the controller, never autonomous sub-agents.

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
- **Question:** What is the smallest local model architecture worth building for M5 24 GB and RTX 4070 12 GB?
- **Finding:** Qwen3-VL now has an official 8B Instruct model, local GGUF path, computer-use/grounding capability and tool interfaces. Because BrowserAgentV2 is semantic-first, the general model need not be the primary pixel controller. Start with one multimodal 8B generalist baseline; compare optional 2-3B GUI specialists only on semantic gaps. Keep critic probabilistic and on-demand. Use stable-prefix/bounded-state prompting and measure prompt/KV caching rather than expanding context.
- **Evidence quality:** 2-4; final hardware suitability unmeasured
- **Impact:** narrows v1 model architecture substantially; no always-on ensemble, learned router or mandatory critic. Qwen3-VL-8B is benchmark candidate, not permanent dependency.
- **Validation:** common fixtures on both machines measuring schema validity, wrong-target/abstention, verifier-confirmed success, p95 latency, RAM/VRAM and repeated variance.

### 2026-09-18 05:xx ET — Reusable skills
- **Question:** How should repeated workflows be encoded without prompt growth or sub-agent complexity?
- **Finding:** Agent Skills/OpenHands converge on progressive disclosure of reusable procedural knowledge. For BrowserAgentV2, skills should be versioned packages with metadata, typed inputs, capability envelope, preconditions, procedure/helpers, verifier/invariants and regression fixtures. Controller executes; model can select but cannot widen authority. Successful traces are candidates, not automatically executable skills.
- **Evidence quality:** 2-4 plus architecture fit
- **Impact:** skills reduce repeated reasoning while preserving bounded context and deterministic authority; reject one-agent-per-skill and vector-retrieval-to-execution.
- **Validation:** 10 real skills + 100 decoys comparing full injection vs metadata progressive disclosure vs schema-filtered routing.

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

## Current Highest-Priority Unresolved Questions
Ranked by architecture impact × uncertainty × cheapness of validation:
1. **Experiment specs + implementation order:** turn architecture claims into one executable validation matrix before more broad research.
2. **Grounding fault fixture:** duplicate-label, replacement, reflow, overlay, absent/ambiguous target, cross-route agreement.
3. **Verifier vocabulary coverage:** measure how many real tasks fit a small predicate vocabulary before expanding DSL.
4. **Crash matrix:** fake external service + crash injection from durable intent through commit/verify.
5. **Prompt-flatness:** 200/500/1,000-action synthetic state projection/reconstruction benchmark.
6. **Model fixture harness:** Qwen3-VL-8B baseline vs optional grounders on target hardware; schema/abstention/wrong-target/latency/memory.
7. **Skill routing fixture:** 10 real + 100 decoy skills; progressive disclosure/context growth.
8. **Windows hardware capability matrix:** reproduce UIA semantic/background assumptions on target Windows machine.
9. **Observability schema:** ensure traces make every controller transition/model proposal/verification/fallback diagnosable without excessive storage.

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

## Handoff
Architecture discovery is now close to saturation. New artifacts: `LOCAL_MODEL_OPTIMIZATION.md`, `SKILL_SYSTEM.md`; ADR-O11 through O14 are now recorded alongside prior ADRs. Do **not** redo broad model/skill surveys next. The next pass should convert the remaining assumptions into a concrete BrowserAgentV2 validation/fault-injection plan and, where connector limitations allow, prototype the cheapest harness pieces. Highest value is proving or falsifying the controller contracts: grounding freshness/abstention, verifier false-success resistance, crash reconciliation, prompt-flatness, model structured-output/visual escalation, and skill progressive disclosure. Windows hardware remains an explicit external validation blocker rather than a reason to redesign the architecture.