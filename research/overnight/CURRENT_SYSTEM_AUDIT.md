# Current System Audit — Run 1

## Scope
First-pass audit of BrowserAgentV2/ComputerAgent repository state before proposing new architecture. Evidence is primarily the repository's Phase 0 reports, architecture/build specification, decision ledger, and recent commit history.

## Executive finding
BrowserAgentV2 is no longer primarily a browser-agent implementation. The repository has already pivoted into a measurement-first ComputerAgent Phase 0 with a reusable macOS capability harness. The strongest existing assets are not a finished agent loop; they are the reliability invariants, measurement harness, evidence schema, macOS observation/classification code, and architecture decision discipline. Those should be preserved.

The current architecture direction is broadly sound, but it is still under-evidenced in five areas that block a production freeze: Windows UIA, model/runtime selection, visual grounding, long-horizon bounded context, and crash/side-effect reconciliation. The macOS evidence also argues against treating raw AX as a universal action mechanism.

## Component classification

| Component / concept | Verdict | Evidence / reason |
|---|---|---|
| Phase 0 ExperimentRunner / ActionSpec / MacObserver / classification pipeline | KEEP | Reused across multiple campaigns; exposed and caught real measurement defects; 1,010-trial campaign completed with independently verified postconditions. |
| Machine-readable evidence + human-readable reports | KEEP | Essential for falsifiable capability claims and regression conversion. |
| Cursor/foreground/focus non-interference measurement | KEEP + MODIFY | Core safety evidence. Chrome focus observation gap was discovered rather than hidden; warm-up work should be incorporated before future campaigns. |
| Browser semantic control via Playwright/CDP | KEEP | 500/500 campaign postconditions verified; zero physical cursor or foreground-app movement. Stronger route than browser-through-AX. |
| Raw browser control through macOS AX | DO NOT USE AS PRIMARY ROUTE | Chrome AXPress returned success without invoking a plain HTML button; browser AXValue writes were state/order sensitive. Browser semantics should precede AX. |
| Generic macOS AX discovery/read | KEEP | Finder, Calendar, System Settings, Safari, Chrome, VS Code and fixture exposed useful trees/read surfaces; custom-drawn areas remain sparse. |
| Generic macOS AX mutation/action | UNKNOWN / CAPABILITY-GATED | Only the Cocoa fixture has clean verified action+mutation+background+occlusion evidence. Real-app mutation is not broadly proven. |
| Bounded AX tree traversal/introspection helpers | KEEP | Reusable generic semantic observation primitive; must preserve node/depth bounds and avoid giant tree dumps. |
| Stale-element handling | KEEP + GENERALIZE | Genuine invalidated AX element returned kAXErrorInvalidUIElement rather than fabricated data; browser report also found stale references after DOM mutation. Production adapters should re-resolve targets around mutations. |
| Background-safety capability classification | KEEP | Evidence shows safety is route/action/app dependent, not a platform Boolean. |
| Vision as mandatory universal representation | REMOVE as default | Existing decisions correctly make vision an escalation route. Current repo evidence shows semantics are faster and often richer when available. |
| Host physical mouse/keyboard as default execution | REMOVE as default | Conflicts with non-interference goal and loses semantic verification. Retain only foreground-required fallback with explicit policy. |
| Goal/Plan/Event/Fact/Artifact/Recovery state outside model | KEEP concept; implementation still to validate | Required for bounded context and crash reconciliation; not yet proven by 200–1,000 action benchmark in this repo. |
| Intent -> execute -> observe -> verify -> persist invariant | KEEP | Strong architectural invariant for duplicate-side-effect prevention; needs fault-injection proof. |
| Independent Verifier | KEEP / STRENGTHEN | External 2026 evidence increasingly favors structured/app-state verification over model self-claims. |
| One generalist model for planning+grounding+verification | UNKNOWN / likely MODIFY | Recent CUA research supports specialist grounding/critics in some settings, while local inference research warns that decomposition can add overhead. Must benchmark before splitting. |
| Qwen3-8B as fixed production model | DO NOT FREEZE | Keep only as baseline. Hardware-specific benchmark gate remains correct. |
| SQLite/FTS + structured state before embeddings | KEEP as initial hypothesis | Simpler and measurable; embeddings should be added only if retrieval benchmark shows need. |
| Graphify as runtime memory | REMOVE / already rejected | Repository decision correctly keeps it developer-only and removable. |
| Existing Phase 0 tests and historical failure conversion | KEEP / EXPAND | Known failures should become regression fixtures before headline benchmark chasing. |

## What the current evidence actually proves

### Browser semantics
The browser campaign executed 500 trials across backgrounded, occluded, multi-tab, multi-window and popup conditions with 500/500 verified postconditions, zero cursor movement and zero foreground-app changes. Most trials were conservatively classified INCONCLUSIVE only because Chrome's focused-element signal was unavailable to the observer in that session. This is strong evidence for semantic browser execution and for the measurement harness, but not permission to claim universal background safety without fixing/re-running the focus sensor path.

### macOS accessibility
The AX campaign executed 510 trials with 510/510 verified postconditions. A deliberately stale AX element failed explicitly rather than returning stale content. A later eight-application capability survey found useful AX discovery/read surfaces across representative native, browser and Electron apps, but only the controlled Cocoa fixture had fully verified semantic mutation/action. Chrome's AXPress could report success while producing no page effect, and browser AXValue writes were ordering-sensitive. Therefore an AX API success code is not a sufficient postcondition.

### Custom/Electron UI
VS Code exposed a shallow/sparse actionable tree in the bounded survey, consistent with custom-drawn/Monaco regions being semantically weak. This validates the need for a visual fallback, but does not prove a particular visual grounding model.

## Architectural implications already supported
1. Keep the routing hierarchy API/tool -> browser semantics -> desktop accessibility -> visual grounding -> foreground/isolated fallback -> human handoff.
2. Capability routing must be based on measured route/app/action metadata, not model confidence.
3. Targets must be re-resolved after mutations; do not retain opaque DOM/AX handles across arbitrary state changes.
4. API return success is not action success. Verify an external postcondition.
5. The production agent should own reliability/state/policy while adapters remain replaceable commodity mechanisms.
6. The first production vertical slice should build on the measured harness instead of bypassing it.

## Critical gaps before architecture freeze
1. Windows UIA has no equivalent evidence yet.
2. Visual grounding route has no measured accuracy/latency/abstention data.
3. Model/runtime choice remains unbenchmarked under common fixtures on both target hardware classes.
4. Long-horizon state/context has not passed the 200–1,000 action flat-context gate.
5. Crash reconciliation invariant has not been fault-injection proven.
6. Security/prompt-injection policy has not been exercised end-to-end.
7. Browser/macOS background campaigns need focus-observation hardening incorporated and rerun where needed.

## Provisional current architecture hypothesis
Preserve the existing reliability-first architecture, but make it explicitly **hybrid-semantic with verifier-grounded execution** rather than a vision-first imitation of human input. The agent should choose the richest proven semantic route for each target, use vision only for semantic gaps, persist intent/state outside the model, and refuse to advance a plan until a separately observed postcondition verifies the action. Model specialization is not yet frozen; benchmark a minimal single-model baseline against selective grounding/critic specialists before adding permanent model layers.
