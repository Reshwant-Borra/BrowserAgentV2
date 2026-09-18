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

**EVIDENCE:** BrowserAgentV2 macOS survey observed WebKit rebuilding an accessibility node after text mutation; stale AX fixture correctly produced invalid-element errors.

**ALTERNATIVES:** hold element handles for the whole subtask; raw coordinate persistence.

**WHY REJECTED:** both are vulnerable to dynamic UI replacement/reflow.

**RISKS:** re-resolution can choose the wrong duplicate-label target.

**HOW TO VALIDATE:** fixtures that replace/reorder duplicate controls between observe and act; require stale detection and correct re-grounding/abstention.

## ADR-O4 — Repeated-trial reliability is a release metric
**DECISION:** Evaluate task classes over repeated executions and report success distribution/failure taxonomy, not only single-run success.

**CONFIDENCE:** 92%

**EVIDENCE:** 2026 reliability work shows same task/model can vary across repeated runs; BrowserAgentV2's campaign methodology already caught state-leakage/harness defects.

**ALTERNATIVES:** one canonical trajectory per task; only aggregate benchmark headline score.

**WHY REJECTED:** hides stochastic/ordering/environment sensitivity.

**RISKS:** evaluation cost.

**HOW TO VALIDATE:** repeated trials by task risk/length; track uncertainty and failure-family frequencies.

## ADR-O5 — Do not freeze a multi-model architecture yet
**DECISION:** Start model benchmarking with one general decision model baseline plus optional specialist grounder and optional critic escalation. Add permanent specialists only if measured gains justify latency/memory/formatting overhead.

**CONFIDENCE:** 86%

**EVIDENCE:** specialist grounding/critic systems show potential value, while local-CUA inference work shows decomposition overhead and diminishing returns. BrowserAgentV2 has no common-fixture local benchmark yet.

**ALTERNATIVES:** always-on planner/executor/verifier trio; one end-to-end model forever.

**WHY REJECTED:** both extremes are premature without target-hardware evidence.

**RISKS:** simple baseline may underperform; specialist routing can fail.

**HOW TO VALIDATE:** common fixture benchmark on M5 24 GB and RTX 4070 12 GB comparing single-model, +grounder, +critic, and both.

## ADR-O6 — Safety invariants accompany success predicates
**DECISION:** Verification for consequential tasks must check prohibited effects/invariants as well as desired success state; policy authority remains deterministic and outside untrusted UI/model content.

**CONFIDENCE:** 93%

**EVIDENCE:** state-based safety benchmarks show nominal task success can coexist with unsafe shortcuts; verification research reinforces pre-action feasibility/intent checks.

**ALTERNATIVES:** action-level guard only; success verifier only.

**WHY REJECTED:** neither catches an agent reaching the goal while violating constraints.

**RISKS:** invariant coverage can be incomplete.

**HOW TO VALIDATE:** adversarial fixtures where easiest route violates a constraint; require safe completion or handoff.

## ADR-O7 — No durable universal element; use ephemeral intent-to-candidate resolution
**DECISION:** Represent targets as route-neutral `TargetSpec` semantic intent, resolve against each fresh observation into `TargetCandidate` objects with provenance/confidence, and keep DOM/AX/UIA handles or coordinates as opaque adapter-local `ExecutionRef`s that expire with observation/mutation.

**CONFIDENCE:** 95%

**EVIDENCE:** Direct BrowserAgentV2 evidence shows AX node rebuilding/staleness and browser dynamic-state risk. Browser/GUI agent systems use observation-local IDs or separate grounding from action. Visual coordinates inherently lack durable identity.

**ALTERNATIVES:** one persistent `UniversalElement`; durable coordinates; backend handles persisted across steps.

**WHY REJECTED:** hide incompatible identity/lifetime semantics and create dangerous semantic rebinding.

**RISKS:** re-resolution may be ambiguous.

**HOW TO VALIDATE:** duplicate-label/reorder, replacement, reflow, overlay, cross-route-agreement and canvas fixtures.

## ADR-O8 — Pre-dispatch freshness gate for consequential actions
**DECISION:** For consequential actions, revalidate app/window/target state immediately before dispatch; observation age and unexpected UI transitions are part of action eligibility.

**CONFIDENCE:** 89%

**EVIDENCE:** BrowserAgentV2 proves semantic handles can stale; GUI TOCTOU research formalizes observation-to-action state changes.

**ALTERNATIVES:** observe once then act regardless of delay; postcondition-only detection.

**WHY REJECTED:** wrong action may be irreversible before verification.

**RISKS:** extra observation latency and false abstention.

**HOW TO VALIDATE:** inject benign overlay/focus/window changes between grounding and dispatch.

## ADR-O9 — Structured authoritative execution state; retrieval memory is advisory
**DECISION:** Keep Goal/Plan/Action/Recovery state and an append-only event journal outside the model. Build each model turn from a bounded structured projection plus a short recent window and only selectively retrieved facts. Semantic/vector memory never determines whether a step completed or an external effect occurred.

**CONFIDENCE:** 95%

**EVIDENCE:** Long-horizon context research (LongSeeker, CAT, MAGE, Mem0) consistently finds that append-only full context is inefficient and that selective/structured context management improves long-horizon behavior. MAGE specifically argues semantic retrieval mismatches execution-state dependencies. BrowserAgentV2 correctness additionally requires exact action/verification state, which approximate retrieval cannot supply.

**ALTERNATIVES:** full transcript; rolling summary as sole memory; vector DB as task state.

**WHY REJECTED:** context grows with horizon; summaries drift; similarity retrieval can mix stale/failed traces and is not transactional.

**RISKS:** projection may omit a future-needed fact; compaction can preserve an incorrect fact.

**HOW TO VALIDATE:** 200/500/1,000-action synthetic runs with constant current-step complexity; require <15% active-prompt growth from 200 to 1,000 actions, >=99% required-fact recall, <=0.5% stale fact injection, and exact checkpoint+event reconstruction.

## ADR-O10 — Durable action intent + reconciliation; never claim generic exactly-once UI effects
**DECISION:** Persist a stable logical action ID and intent before dispatch. Use tool-native idempotency keys when available; otherwise reconcile queryable state before retry. If an irreversible non-idempotent action may have committed but cannot be queried, mark outcome unknown and do not automatically repeat it. Plan advances only after verified success.

**CONFIDENCE:** 97%

**EVIDENCE:** Durable workflow systems expose at-least-once side-effect execution and require idempotency/reconciliation because a crash can occur after external commit but before local acknowledgement. Checkpointing alone cannot close this distributed commit window. GUI actions usually lack transactional participation, making explicit ambiguity handling mandatory.

**ALTERNATIVES:** retry last step after restart; checkpoint after each step only; assume process-local exactly-once.

**WHY REJECTED:** all can duplicate an external side effect in the commit/ack crash window.

**RISKS:** some UI effects cannot be automatically reconciled, requiring handoff or domain-specific compensation.

**HOW TO VALIDATE:** fake external service with idempotent/queryable/non-idempotent operations; inject crashes before/after every intent/dispatch/commit/result/verify boundary for >=1,000 randomized trials per class; require zero duplicate idempotency-capable effects and zero automatic retries of ambiguous non-idempotent effects.
