# Overnight Research Ledger

This file is the continuity handoff between scheduled research runs.

## Rules
- Read this file before starting new research.
- Do not repeat a source/question unless prior evidence is inadequate or contradictory.
- Append meaningful findings rather than replacing history.
- Update the current architecture hypothesis and unresolved questions after every run.
- Record negative results and failed hypotheses.

## Current Architecture Hypothesis
Preserve BrowserAgentV2's reliability-first architecture and Phase 0 harness. Production direction is a **hybrid semantic-first, verifier-grounded ComputerAgent**: deterministic tools/APIs when available -> Playwright/CDP browser semantics -> platform accessibility -> visual grounding/coordinate fallback -> foreground/handoff. Authoritative goal/plan/policy/recovery state remains outside the model. Every state-changing action is an intent transaction and the plan advances only after a separately observed postcondition verifies success. Targets use route-neutral semantic intent (`TargetSpec`) resolved against a fresh observation into ephemeral candidates; backend handles/coordinates are never durable identity. Consequential actions get a pre-dispatch freshness gate. Verification uses typed predicates and explicit inconclusive/partial/unsafe outcomes. Model specialization remains experimentally open.

## Evidence Entries

### 2026-09-18 00:xx ET — BrowserAgentV2 Phase 0 browser/AX campaigns
- **Question:** Which current mechanisms are reliable enough to keep?
- **Finding:** Existing measurement harness is a strong asset. Browser campaign ran 500 semantic trials with 500/500 verified postconditions, zero physical cursor movement and zero foreground-app changes. AX campaign ran 510 trials with 510/510 verified postconditions and explicit stale-element failure behavior. Most browser campaign safety classifications were conservative INCONCLUSIVE because the observer could not read Chrome focused-element state in that session, not because actions failed.
- **Evidence quality (1-5):** 5
- **Architecture impact:** KEEP ExperimentRunner/ActionSpec/MacObserver/classification/evidence discipline; keep semantic browser route; incorporate focus warm-up before rerunning safety claims.
- **Follow-up:** reproduce on Windows target.

### 2026-09-18 00:xx ET — macOS 8-application AX capability survey
- **Question:** Can macOS AX be the universal desktop/browser action layer?
- **Finding:** Generic AX discovery/read is broad, but verified mutation/action is not. Chrome AXPress returned API success while failing to fire a plain HTML button; Safari/Chrome AXValue writes were state/order-sensitive; VS Code custom-drawn surface exposed sparse semantics. Only controlled Cocoa fixture had clean verified action+mutation+background+occlusion coverage.
- **Evidence quality (1-5):** 5
- **Architecture impact:** browser semantics must precede AX; AX actions are capability-gated; API return success is never sufficient verification; visual fallback is required for semantic gaps.

### 2026-09-18 00:xx ET — OpenAI CUA / OSWorld / hybrid systems
- **Question:** Should BrowserAgentV2 copy a screenshot + virtual mouse/keyboard universal interface?
- **Finding:** Pixel/action-only interfaces are broad, but public frontier-agent evolution and hybrid systems show semantics/tools and visual routes are complementary. Screenshot-only universality does not imply local reliability or background execution.
- **Evidence quality (1-5):** 3-4
- **Architecture impact:** retain vision/coordinates as fallback; do not discard semantic routes.

### 2026-09-18 00:xx ET — Verification/reliability research
- **Question:** How should action/task success be verified?
- **Finding:** Structured/environment-state verification is stronger than trusting API returns or the acting model. OpenComputer and Interactive Reward Agent support environment-state evidence; VeriGUI models action-effect verification/recovery; VeriSafe and ConflictGUI reinforce deterministic feasibility/intent checks and explicit refusal/termination when acting is unsupported or conflicting.
- **Evidence quality (1-5):** 3
- **Architecture impact:** typed verification predicates, independent evidence, explicit PARTIAL/INCONCLUSIVE/UNSAFE outcomes, safety invariants, bounded recovery.

### 2026-09-18 00:xx ET — Local CUA inference-time scaling
- **Question:** Will more context/steps/model decomposition solve local-agent reliability?
- **Finding:** More history/compute often shows diminishing returns; failures can shift to premature false success; longer horizons can extend wrong trajectories; two-stage decomposition can add planning/formatting overhead.
- **Evidence quality (1-5):** 3
- **Architecture impact:** bounded retries, verification and selective compute are more important than simply increasing context/steps. Do not freeze planner/executor/verifier multi-model split without measurement.

### 2026-09-18 00:5x ET — Target representation research
- **Question:** What minimum target representation can bridge Playwright, AX/UIA and vision without a brittle universal element?
- **Finding:** Do not unify backend identity. Use `TargetSpec` (planner-owned semantic intent) -> fresh adapter resolution -> `TargetCandidate` (observation-local evidence/provenance/confidence) -> opaque adapter-local `ExecutionRef`. BrowserGym/ComponentBench observation IDs are ephemeral; Agent S separates grounding from action; Tactile 2026 similarly exposes heterogeneous candidates with provenance/affordances/verification cues. Direct BrowserAgentV2 AX evidence already proves semantic object replacement/staleness.
- **Evidence quality (1-5):** 4-5
- **Architecture impact:** reject durable UniversalElement. Cross-route escalation re-resolves intent rather than translating handles. Ambiguity is a first-class abstention state.
- **Follow-up:** implement duplicate-label, replacement, reflow, overlay and cross-route-agreement fixtures before production abstraction freezes.

### 2026-09-18 00:5x ET — Pre-dispatch freshness / TOCTOU
- **Question:** Is post-action verification enough for consequential actions?
- **Finding:** No. A wrong target can produce irreversible effects before postcondition verification. 2026 GUI TOCTOU research formalizes the observation-to-action gap and motivates immediate pre-execution revalidation. This applies to benign popups/reflow as well as adversarial changes.
- **Evidence quality (1-5):** 3 plus direct stale-target evidence 5
- **Architecture impact:** consequential actions revalidate app/window/target state immediately before dispatch; observation age and unexpected transitions affect eligibility.

## Decisions Recorded
See `ARCHITECTURE_DECISIONS.md`:
- ADR-O1 hybrid semantic-first control, visual fallback — 94%
- ADR-O2 verification as first-class typed contract — 97%
- ADR-O3 re-resolve semantic targets after mutation — 95%
- ADR-O4 repeated-trial reliability metric — 92%
- ADR-O5 do not freeze multi-model architecture yet — 86%
- ADR-O6 safety invariants accompany success predicates — 93%
- ADR-O7 no durable universal element; ephemeral intent-to-candidate resolution — 95%
- ADR-O8 pre-dispatch freshness gate for consequential actions — 89%

## Current Highest-Priority Unresolved Questions
Ranked by architecture impact × uncertainty × cheapness of validation:
1. **Windows parity:** Does UIA support the same semantic-first/background assumptions on the target Windows machine, especially Electron/custom apps? Research source/implementation evidence first; hardware experiment later.
2. **Visual fallback:** Which current open GUI grounder/parser is the best local candidate on M5 24 GB and RTX 4070 12 GB? Need accuracy/abstention/latency/memory, not leaderboard reputation.
3. **Local model split:** Single generalist vs +GUI grounder vs +critic on one common fixture set.
4. **Long-horizon state:** Minimal Goal/Plan/Event/Fact/Recovery representation that keeps prompt size flat from 200 to 1,000 actions without retrieval contamination.
5. **Crash reconciliation:** Prove unresolved ACTION_INTENT cannot cause duplicate external side effects across injected crash points.
6. **Security:** Convert task-level prohibited effects and indirect prompt injection into policy/verifier invariants.
7. **Grounding experiment implementation:** Build the cheap fixture suite specified in `GROUNDING.md`; do not add a learned cross-source fusion layer first.
8. **Verifier coverage experiment:** Implement the small predicate vocabulary in `ACTION_VERIFICATION.md` and measure how many representative skills require custom predicates before expanding the DSL.

## Negative Results / Assumptions Rejected
- Raw AX cannot be assumed reliable because an API call returns success.
- Semantic object handles cannot be assumed durable across UI mutation.
- A pixel-only interface is not automatically best for a local universal agent because frontier CUAs use one.
- More context, more steps, or more model stages are not monotonic reliability improvements.
- One successful benchmark trajectory is not sufficient evidence of reliability.
- A durable cross-backend `UniversalElement` is the wrong abstraction; identity/lifetime semantics differ too much.
- Screenshot difference alone is not a semantic success verifier.
- Post-action verification alone is insufficient for high-risk actions when UI state can change between observation and dispatch.

## Handoff
Run 2 resolved the two highest-priority architecture questions enough to proceed. New artifacts: `GROUNDING.md` and `ACTION_VERIFICATION.md`; ADRs O7/O8 added and O2 strengthened. Do **not** redo target/verifier literature broadly. Next pass should attack Windows/UIA parity and current open-source hybrid/visual execution implementations, then narrow the local visual-grounder candidates. If that converges quickly, move to the local model split and benchmark design. The grounding/verifier abstractions should remain provisional until their fault-injection fixtures are implemented, but there is now enough evidence to avoid designing a universal element or model-judged success loop.