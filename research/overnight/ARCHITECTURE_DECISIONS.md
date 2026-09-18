# Overnight Architecture Decisions

These are provisional evidence-backed ADRs for the overnight mission. Confidence can move as later runs add experiments.

## ADR-O1 — Hybrid semantic-first control, visual fallback
**DECISION:** Use deterministic/native tools when available, Playwright/CDP for browser semantics, platform accessibility for desktop semantics, then visual grounding/coordinate input only for semantic gaps. Foreground physical input is a capability-gated last resort, not the universal default.

**CONFIDENCE:** 94%

**EVIDENCE:** BrowserAgentV2 browser campaign verified 500/500 semantic postconditions with zero cursor/foreground movement; macOS app survey found rich semantic AX read surfaces in many apps but real action gaps in browser-through-AX and sparse VS Code custom UI; OSWorld shows both pixels and accessibility can fail/mislead; UI-TARS-2 and OSWorld-MCP show strong systems benefit from hybrid non-GUI tools.

**ALTERNATIVES:** pixel-only virtual mouse/keyboard; AX-for-everything on macOS; app-specific bespoke integrations.

**WHY REJECTED:** pixel-only throws away deterministic semantics/background control and is poorly matched to small local models; AX is not universal and browser AX mutations/actions already failed; bespoke integrations do not scale.

**RISKS:** router may choose a semantically available but behaviorally broken route; visual fallback remains unbenchmarked.

**HOW TO VALIDATE:** capability matrix + routing benchmark where identical tasks are attempted semantic-first, visual-first, and hybrid; include custom/canvas/Electron cases and stale targets.

## ADR-O2 — Verification is a first-class contract, not a model reflection step
**DECISION:** Every state-changing skill/adapter must expose or construct a postcondition verifier independent of the action's API return and model's success claim. Prefer structured/app-state verification; use visual/LLM verification only when deterministic state is unavailable, with uncertainty/handoff.

**CONFIDENCE:** 97%

**EVIDENCE:** BrowserAgentV2 directly observed Chrome AXPress return success without producing the intended page effect. OpenComputer and Interactive Reward Agent support structured/environment-state verification over trajectory-only judging. VeriGUI explicitly models action-effect verification and recovery. Local CUA inference research reports failures shifting toward premature false success when more history/compute is supplied.

**ALTERNATIVES:** trust action API success; let acting model decide success; screenshot-difference-only verifier.

**WHY REJECTED:** API success can be a no-op; self-verification shares failure modes with action generation; pixel deltas are neither necessary nor sufficient for semantic success.

**RISKS:** writing verifiers for arbitrary tasks can become app-specific complexity.

**HOW TO VALIDATE:** implement the small predicate contract in ACTION_VERIFICATION.md; inject no-op-success, partial-success, stale-state, verifier-unavailable, unrelated-visual-change and wrong-target faults; require zero false success on controlled fixtures.

## ADR-O3 — Re-resolve semantic targets after mutation
**DECISION:** Do not treat DOM/AX object handles as durable identity across arbitrary UI mutations. Store a semantic target description/fingerprint and re-resolve against a fresh observation before consequential actions or verification.

**CONFIDENCE:** 95%

**EVIDENCE:** BrowserAgentV2 macOS survey observed WebKit rebuilding an accessibility node after text mutation; stale AX fixture correctly produced invalid-element errors. Historical browser work also encountered stale/tab-binding issues.

**ALTERNATIVES:** hold element handles for the whole subtask; raw coordinate persistence.

**WHY REJECTED:** both are vulnerable to dynamic UI replacement/reflow.

**RISKS:** re-resolution can choose the wrong duplicate-label target.

**HOW TO VALIDATE:** fixtures that replace/reorder duplicate controls between observe and act; require stale detection and correct re-grounding/abstention.

## ADR-O4 — Repeated-trial reliability is a release metric
**DECISION:** Evaluate task classes over repeated executions and report success distribution/failure taxonomy, not only single-run success.

**CONFIDENCE:** 92%

**EVIDENCE:** 2026 reliability study shows same task/model can vary across repeated runs and explicitly recommends repeated execution; BrowserAgentV2's own campaign methodology already benefits from repetition and caught state-leakage/harness defects.

**ALTERNATIVES:** one canonical trajectory per task; only aggregate benchmark headline score.

**WHY REJECTED:** hides stochastic/ordering/environment sensitivity.

**RISKS:** evaluation cost.

**HOW TO VALIDATE:** minimum repeated-trial counts by task risk/length; track Wilson intervals or equivalent uncertainty and failure-family frequencies.

## ADR-O5 — Do not freeze a multi-model architecture yet
**DECISION:** Start model benchmarking with the smallest viable architecture: one general decision model baseline plus optional specialist grounder and optional critic escalation. Add permanent specialists only if they improve accepted-action accuracy/reliability enough to justify latency/memory/formatting overhead.

**CONFIDENCE:** 86%

**EVIDENCE:** Agent S2 and OS-Oracle show specialist grounding/critic value; 2026 local-CUA inference study finds two-stage decomposition can introduce planning/formatting overhead and more compute has diminishing returns. BrowserAgentV2 has no common-fixture local benchmark yet.

**ALTERNATIVES:** always-on planner/executor/verifier trio; one end-to-end model forever.

**WHY REJECTED:** both extremes are premature without target-hardware evidence.

**RISKS:** a simple baseline may underperform enough to slow early experiments; specialist routing itself can fail.

**HOW TO VALIDATE:** common fixture benchmark on M5 24 GB and RTX 4070 12 GB comparing single-model, +grounder, +critic, and both; measure accepted-action accuracy, false-success rate, p95 latency, memory and stability.

## ADR-O6 — Safety invariants accompany success predicates
**DECISION:** Verification for consequential tasks must check prohibited effects/invariants as well as desired success state; policy authority remains deterministic and outside untrusted UI/model content.

**CONFIDENCE:** 93%

**EVIDENCE:** OSGuard demonstrates nominal task success can coexist with unsafe shortcuts and evaluates explicit state-based safety invariants. VeriSafe and ConflictGUI independently reinforce pre-action feasibility/intent checks and the need to terminate rather than blindly execute when evidence conflicts.

**ALTERNATIVES:** action-level guard only; success verifier only.

**WHY REJECTED:** neither catches an agent reaching the goal while violating constraints.

**RISKS:** invariant coverage can be incomplete.

**HOW TO VALIDATE:** adversarial fixtures where the easiest route violates a constraint but a safe route remains available; require safe completion or handoff.

## ADR-O7 — No durable universal element; use ephemeral intent-to-candidate resolution
**DECISION:** Represent targets as route-neutral `TargetSpec` semantic intent, resolve against each fresh observation into `TargetCandidate` objects with provenance/confidence, and keep DOM/AX/UIA handles or coordinates as opaque adapter-local `ExecutionRef`s that expire with observation/mutation.

**CONFIDENCE:** 95%

**EVIDENCE:** Direct BrowserAgentV2 evidence shows AX node rebuilding/staleness and browser dynamic-state risk. BrowserGym/ComponentBench use observation-local IDs. Agent S separates grounding from action. Tactile 2026 represents heterogeneous semantic/OCR/visual target candidates with provenance, affordances and verification cues. Visual coordinates inherently lack durable identity.

**ALTERNATIVES:** one persistent `UniversalElement` wrapping every backend; durable coordinates; backend handles persisted across steps.

**WHY REJECTED:** they hide incompatible identity/lifetime semantics and create dangerous semantic rebinding after UI mutation.

**RISKS:** re-resolution may be ambiguous; cross-source fusion could become complex.

**HOW TO VALIDATE:** duplicate-label/reorder, DOM replacement, AX replacement, window-reflow, overlay-hijack, cross-route-agreement and canvas fixtures. Correct behavior is resolution or explicit abstention, never arbitrary best-score action.

## ADR-O8 — Pre-dispatch freshness gate for consequential actions
**DECISION:** For consequential actions, revalidate app/window/target state immediately before dispatch; observation age and unexpected UI transitions are part of action eligibility. Do not rely solely on post-action verification.

**CONFIDENCE:** 89%

**EVIDENCE:** BrowserAgentV2 already proves semantic handles can stale. 2026 desktop GUI TOCTOU work formalizes observation-to-action state changes and demonstrates action redirection attacks, motivating pre-execution UI state verification. This also protects against benign reflow/popups, not only adversaries.

**ALTERNATIVES:** observe once then act regardless of delay; postcondition-only detection.

**WHY REJECTED:** postcondition verification can detect a wrong action only after side effects occur; stale coordinates can hit a different control.

**RISKS:** extra observation latency may itself increase drift; overly sensitive screenshot checks can false-abstain.

**HOW TO VALIDATE:** benign overlay/focus/window-move injection between grounding and dispatch at varied delays; measure unsafe-dispatch rate and false-abstention cost.