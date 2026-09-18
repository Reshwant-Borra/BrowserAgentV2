# Overnight Research Ledger

This file is the continuity handoff between scheduled research runs.

## Rules
- Read this file before starting new research.
- Do not repeat a source/question unless prior evidence is inadequate or contradictory.
- Append meaningful findings rather than replacing history.
- Update the current architecture hypothesis and unresolved questions after every run.
- Record negative results and failed hypotheses.

## Current Architecture Hypothesis
Preserve BrowserAgentV2's reliability-first architecture and Phase 0 harness. Production direction is a **hybrid semantic-first, verifier-grounded ComputerAgent**: deterministic tools/APIs when available -> Playwright/CDP browser semantics -> platform accessibility -> visual grounding/coordinate fallback -> foreground/handoff. Authoritative goal/plan/policy/recovery state remains outside the model. Every state-changing action is an intent transaction and the plan advances only after a separately observed postcondition verifies success. Semantic targets are re-resolved after mutations rather than treated as durable object handles. Model specialization remains experimentally open: benchmark a minimal generalist baseline against optional grounding/critic specialists before freezing extra model layers.

## Evidence Entries

### 2026-09-18 00:xx ET — BrowserAgentV2 Phase 0 browser/AX campaigns
- **Question:** Which current mechanisms are reliable enough to keep?
- **Finding:** Existing measurement harness is a strong asset. Browser campaign ran 500 semantic trials with 500/500 verified postconditions, zero physical cursor movement and zero foreground-app changes. AX campaign ran 510 trials with 510/510 verified postconditions and explicit stale-element failure behavior. Most browser campaign safety classifications were conservative INCONCLUSIVE because the observer could not read Chrome focused-element state in that session, not because actions failed.
- **Evidence quality (1-5):** 5
- **Architecture impact:** KEEP ExperimentRunner/ActionSpec/MacObserver/classification/evidence discipline; keep semantic browser route; incorporate focus warm-up before rerunning safety claims.
- **Contradictions:** None material. The safety label remains deliberately weaker than the action-success evidence.
- **Follow-up:** rerun hardened focus-observation campaign; reproduce on Windows target.

### 2026-09-18 00:xx ET — macOS 8-application AX capability survey
- **Question:** Can macOS AX be the universal desktop/browser action layer?
- **Finding:** Generic AX discovery/read is broad, but verified mutation/action is not. Chrome AXPress returned API success while failing to fire a plain HTML button; Safari/Chrome AXValue writes were state/order-sensitive; VS Code custom-drawn surface exposed sparse semantics. Only controlled Cocoa fixture had clean verified action+mutation+background+occlusion coverage.
- **Evidence quality (1-5):** 5
- **Architecture impact:** browser semantics must precede AX; AX actions are capability-gated; API return success is never sufficient verification; visual fallback is required for semantic gaps.
- **Contradictions:** Pixel-only frontier agents demonstrate broader universality, but not better local reliability/background behavior.
- **Follow-up:** test representative safe native-app mutations on disposable fixtures; characterize Electron/custom UI visual fallback.

### 2026-09-18 00:xx ET — OpenAI CUA / OSWorld
- **Question:** Should BrowserAgentV2 copy a screenshot + virtual mouse/keyboard universal interface?
- **Finding:** Pixel/action-only interfaces are broad and frontier CUA reached meaningful benchmark performance, but OSWorld documents grounding, repetition, unexpected-window and cross-app failures. This proves a visual universal fallback is necessary, not that semantic routes should be discarded.
- **Evidence quality (1-5):** 3
- **Architecture impact:** retain vision/coordinates as fallback; do not optimize an 8B local system around frontier pixel-only assumptions.
- **Contradictions:** CUA's single universal interface is architecturally simpler, but relies on much stronger model capability and loses semantic/background advantages measured locally.
- **Follow-up:** grounding benchmark against semantic-first/hybrid route.

### 2026-09-18 00:xx ET — OpenComputer 2026
- **Question:** How should action/task success be verified?
- **Finding:** App-specific structured state verifiers aligned better with human adjudication than LLM-as-judge for fine-grained software state; framework records full trajectories and machine-checkable partial credit.
- **Evidence quality (1-5):** 3
- **Architecture impact:** strengthen Verifier into a first-class per-adapter/per-skill contract; deterministic/app-state predicates before visual/model judgment.
- **Contradictions:** App-specific verification can increase engineering cost.
- **Follow-up:** design generic predicate vocabulary plus skill-specific verifier hooks; fault-inject false API success.

### 2026-09-18 00:xx ET — Local CUA inference-time scaling study 2026
- **Question:** Will more context/steps/model decomposition solve local-agent reliability?
- **Finding:** More history/compute often shows diminishing returns; failure modes can shift to premature false success; longer horizons can extend wrong trajectories; two-stage decomposition can add planning/formatting overhead.
- **Evidence quality (1-5):** 3
- **Architecture impact:** bounded retries, verification and selective compute are more important than simply increasing context/steps. Do not freeze planner/executor/verifier multi-model split without measurement.
- **Contradictions:** Agent S2 and OS-Oracle show specialist grounding/critics can improve performance.
- **Follow-up:** benchmark minimal baseline vs optional grounder/critic under common fixtures.

### 2026-09-18 00:xx ET — Reliability / CUADebug / OSGuard research
- **Question:** What evaluation/recovery behavior is missing from current architecture?
- **Finding:** Same task/model can vary across repeated executions; failure diagnosis using before/after evidence improves re-execution over history-only continuation; nominal success can coexist with unsafe shortcuts unless safety invariants are checked.
- **Evidence quality (1-5):** 3
- **Architecture impact:** repeated-trial release metrics; compact before/action/after evidence; failure taxonomy before retry; verifier checks both desired effects and prohibited effects.
- **Contradictions:** Increased instrumentation/evaluation cost.
- **Follow-up:** convert these into BrowserAgentV2 regression/fault-injection fixtures.

## Decisions Recorded This Run
See `ARCHITECTURE_DECISIONS.md`:
- ADR-O1 hybrid semantic-first control, visual fallback — 94%
- ADR-O2 verification as first-class contract — 96%
- ADR-O3 re-resolve semantic targets after mutation — 95%
- ADR-O4 repeated-trial reliability metric — 92%
- ADR-O5 do not freeze multi-model architecture yet — 86%
- ADR-O6 safety invariants accompany success predicates — 93%

## Current Highest-Priority Unresolved Questions
Ranked by architecture impact × uncertainty × cheapness of validation:
1. **Grounding + unified target contract:** What minimum semantic target representation can bridge Playwright, AX/UIA and vision without inventing a brittle universal element abstraction? Need stale/duplicate-label/coordinate mapping tests.
2. **Verification contract:** Which generic postcondition predicates cover most browser/desktop skills, and when must verification be skill/app-specific? Need no-op-success and partial-success fault injection.
3. **Windows parity:** Does UIA support the same semantic-first/background assumptions on the target Windows machine, especially Electron/custom apps?
4. **Local model split:** Single generalist vs +GUI grounder vs +critic on M5 24 GB and RTX 4070 12 GB under one fixture set. Do not settle by reputation.
5. **Long-horizon state:** Minimal Goal/Plan/Event/Fact/Recovery representation that keeps prompt size flat from 200 to 1,000 actions without retrieval contamination.
6. **Crash reconciliation:** Prove unresolved ACTION_INTENT cannot cause duplicate external side effects across injected crash points.
7. **Visual fallback:** Measure current open GUI grounding candidates for accuracy, abstention, latency and memory on custom/canvas/Electron targets.
8. **Security:** Convert task-level prohibited effects and indirect prompt injection into policy/verifier invariants.

## Negative Results / Assumptions Rejected
- Raw AX cannot be assumed to be a reliable browser action mechanism merely because the API call returns success.
- Semantic object handles cannot be assumed durable across UI mutation.
- A pixel-only interface is not automatically the best architecture for a local universal agent simply because frontier CUAs use one.
- More context, more steps, or more model stages are not monotonic reliability improvements for local CUAs.
- One successful benchmark trajectory is not sufficient evidence of task reliability.

## Handoff
Run 1 completed the initial repository audit and an architecture-impact external research pass. New artifacts: `CURRENT_SYSTEM_AUDIT.md`, `RELATED_SYSTEMS.md`, `ARCHITECTURE_DECISIONS.md`. The next run should **not** redo the broad audit. Start with unresolved #1/#2: inspect current target/action schemas and adapter code, then research/compare semantic target representations, grounding confidence/abstention, and verifier contracts. If those become sufficiently concrete, move to current open-source computer-agent implementations and failure/issue evidence, especially systems with hybrid semantic/visual routing.
