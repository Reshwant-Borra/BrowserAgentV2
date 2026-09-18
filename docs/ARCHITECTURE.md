# ComputerAgent Architecture

## Architectural principle

**Own the reliability architecture; reuse commodity mechanisms.**

ComputerAgent owns task semantics, authoritative state, policy, context construction, routing, verification, reconciliation, recovery, and user handoff. It should reuse/adapt mature mechanisms for browsers, accessibility, inference, screenshots/grounding, and isolation rather than replacing them.

## Top-level flow

```text
User Goal
   |
TaskController
   |
Goal / Policy / Plan / Durable State
   |
Bounded Context Builder
   |
Local Model Adapter
   |
Strict Decision Schema + Validator
   |
PolicyEngine
   |
InteractionRouter
   |
   +--> API / connector
   +--> BrowserAdapter (Playwright/CDP)
   +--> MacAccessibilityAdapter (AX)
   +--> WindowsUIAAdapter
   +--> VisionAdapter
   +--> IsolatedDesktopProvider (capability-gated)
   +--> Human Handoff
   |
Observe state change
   |
Verifier
   |
Persist / reconcile / continue
```

## Core components

### TaskController
Owns task lifecycle, run/resume/reconcile behavior, and advancement of PlanState.

### GoalState
Stores user goal, immutable constraints, approvals, prohibited effects, and other requirements that must not disappear from context.

### PlanState
Stores hierarchical milestones, dependencies, active subgoal, and completion status.

### EventStore
Durable append-oriented record of observations, action intents, action results, policy decisions, verification results, failures, and recovery transitions.

### FactStore
Structured facts with provenance/confidence. Retrieved selectively for the active subgoal.

### ArtifactStore
References screenshots, downloads, snapshots, files, and other large artifacts rather than injecting them repeatedly into model context.

### RecoveryState
Tracks unresolved intents, ambiguous effects, checkpoints, and reconciliation information.

### ContextBuilder
Builds a bounded decision context from authoritative state. Prompt size should remain approximately flat as task duration grows.

### PolicyEngine
Authorizes intent independent of model confidence and detects handoff/confirmation boundaries.

### HardwareProfiler
Measures OS, architecture, physical/available memory, GPU/vendor/model, dedicated or unified memory characteristics, accelerator backend, battery/thermal state where useful, virtualization availability, screen-capture capability, and accessibility capability.

### InferenceProfileManager
Maps measured hardware and benchmark/calibration evidence to planner model, quantization, vision model, runtime, context budget, image budget, cache policy, and model residency policy.

### ModelAdapter
Swappable inference contract. Model output is a proposed structured decision, not authority. Model, plan, and target proposals never self-authorize, expand task scope, declare durable success, or become recovery state — the controller retains all of that (D-022).

Model strategy starts with one replaceable multimodal ~8B-class generalist rather than an always-on planner+grounder+critic ensemble; Qwen3-VL-8B-Instruct is the first benchmark candidate, not a frozen dependency (D-023, unvalidated until `docs/IMPLEMENTATION_PLAN.md` M6 runs on target hardware). A GUI-specialist grounder or a critic model are added only behind measured, verifier-confirmed escalation gates.

### InteractionRouter
Selects the execution mechanism from deterministic capability state and action requirements.

Routing preference:

```text
API/tool
  -> browser semantics
  -> desktop accessibility
  -> visual grounding
  -> isolated workspace/desktop if supported
  -> human handoff
```

### BrowserAdapter
Playwright-first browser semantics. Agent-managed browser/profile is the default P0 route; arbitrary existing-browser CDP attachment is secondary and separately tested.

### MacAccessibilityAdapter
AXUIElement inspection/actions plus explicit measurement of focus/window changes and stale elements.

### WindowsUIAAdapter
UI Automation semantic patterns for inspection, invoke, value changes, scrolling, waiting, etc. Physical input is not equivalent to semantic UIA execution.

### VisionAdapter
Grounds or parses screenshots only when semantics are insufficient. Must support abstention/uncertainty rather than always returning a coordinate.

### IsolatedDesktopProvider
Optional/capability-gated coordinate workspace. It is not a universal fallback and must not be assumed to contain all host apps, sessions, files, or authentication state.

### PermissionBroker
Models Accessibility/Screen Recording permissions on macOS, Windows security boundaries, and explicit human handoff requirements.

### Verifier
Independently checks action postconditions from observed state rather than accepting model claims of success.

## Target resolution contract (PLANNED — see `docs/IMPLEMENTATION_PLAN.md` M1)

ComputerAgent does not build a durable `UniversalElement` that pretends DOM/AX/UIA/vision identities share a lifetime (D-017). Backend element identity is too ephemeral: WebKit rebuilds AX nodes on mutation, and duplicate-labeled controls make role/name alone insufficient to disambiguate.

```text
Goal/subgoal
  -> TargetSpec (semantic intent, route-neutral; no backend handle)
  -> fresh observation
  -> adapter resolver
  -> ranked TargetCandidate(s) (observation-local, with provenance + confidence)
  -> ResolutionResult: RESOLVED | AMBIGUOUS | ABSENT/NOT_FOUND | STALE | UNSUPPORTED
  -> opaque adapter-local ExecutionRef, valid only for that observation version
  -> immediate pre-dispatch freshness check
  -> execute
  -> fresh observation
  -> independent verification
```

Ambiguous or absent resolution must abstain, never guess among tied candidates. This contract is specified but unimplemented; M1's Fixture A (>=1,000 seeded UI-mutation trials) is the falsification test.

## Verification contract (PLANNED — see `docs/IMPLEMENTATION_PLAN.md` M2)

Every state-changing adapter/skill carries a typed `VerificationSpec`, independent of the action's own return value (D-018). This is not optional polish: `phase0/MAC_APP_CAPABILITY_REPORT.md` §G directly measured Chrome's `AXPress` returning AX success while never firing a plain HTML button's click handler.

Predicate vocabulary (small, compositional, expand only on measured coverage gaps): equality/inequality, existence/absence, membership/contains, numeric/range, count/delta, before->after transition, invariant-not-changed, AND/OR, bounded domain-specific callback.

Outcome vocabulary: `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, `INCONCLUSIVE`, `PARTIAL_SUCCESS`, `UNEXPECTED_SIDE_EFFECT`. `INCONCLUSIVE` must never silently become success.

## State-changing transaction invariant

```text
1. Decide intended action
2. Policy-check
3. Persist ACTION_INTENT
4. Execute exactly once
5. Observe resulting state
6. Verify postcondition
7. Persist outcome
8. Advance PlanState only after verification
```

On restart with an unresolved intent:

- if effect is proven to have happened: record success; do not retry;
- if proven not to have happened: retry only if policy permits;
- if ambiguous: reconcile or hand off.

### Recovery classification (PLANNED — see `docs/IMPLEMENTATION_PLAN.md` M3)

There is no generic exactly-once guarantee for arbitrary external/UI effects (D-020). Every unresolved action is classified into exactly one of:

- **A. idempotency-key capable** — retry/reconcile with the same logical `action_id`.
- **B. externally queryable effect** — query the effect before retrying.
- **C. naturally idempotent state-set** — verify current state, repeat only if still needed.
- **D. non-idempotent and non-queryable** — `OUTCOME_UNKNOWN`/`NEEDS_REVIEW`; **never** automatically retried.

Production durable state (D-019) is a SQLite append-only event journal in WAL mode plus deterministic materialized state, built as a new `computer_agent/` package. `phase0/harness/` stays an independent measurement harness and does not become the production controller or recovery journal.

## Security and authority boundary (PLANNED — see `docs/IMPLEMENTATION_PLAN.md` M5)

Authority and information are separate channels (D-021, elaborates D-008). Authority comes only from the original user task, deterministic local policy, pre-granted capabilities, and durable authoritative state. Content from webpages, DOM, AX/UIA, screenshots, OCR, documents, tool output, model output, and retrieved memory is evidence only and can never widen scope — no matter what it asks for.

Every consequential `ActionIntent` passes a non-LLM policy gate (`ALLOW` / `DENY` / `REQUIRE_CONFIRMATION` / `REQUIRE_REPLAN`) scoped to task-granted capabilities. Prompt-injection detection is defense-in-depth only, never the authorization boundary.

## Background-safety model

Background control is not a Boolean platform property. Capability metadata should classify actions/routes such as:

- `BACKGROUND_PROVEN`
- `BACKGROUND_BEST_EFFORT`
- `FOREGROUND_REQUIRED`

Only deterministic probes/test evidence can establish `BACKGROUND_PROVEN`.

## Memory/context architecture

Durable task knowledge lives outside the model. Initial retrieval should favor simple structured queries and SQLite/FTS-style indexing; embeddings/vector retrieval are optional later improvements if evidence shows they are needed.

Graphify, if configured for developer convenience, is repository retrieval tooling only and is not part of ComputerAgent's authoritative runtime memory architecture.

Long-horizon task memory follows the same rule at the task level: `GoalState`/`PlanState`/`ActionState`/`RecoveryState` and the event journal are authoritative; the model receives a bounded working projection (current goal/constraints, current plan/step, current observation, a handful of recent verified actions, unresolved failures, and selected facts), not the full transcript. Retrieval over facts/history is advisory and can never mark a step complete or override observed state (`docs/IMPLEMENTATION_PLAN.md` M4).

## Skills (PLANNED — see `docs/IMPLEMENTATION_PLAN.md` M9)

Reusable procedures are versioned, progressive-disclosure packages under controller authority, not autonomous sub-agents (D-024). Each declares typed inputs, required capabilities, preconditions, a verifier (same contract as Verification, above), safety invariants, an idempotency classification (same classes as Recovery, above), and regression fixtures. A successful trajectory is at most a candidate for a skill — promotion is never automatic.

## Developer Console

A Developer/Test Console may begin as early as M1 once `TargetSpec`/`TargetCandidate`/resolution types exist. It is strictly observational: it visualizes controller-authoritative state (task/step/observation, target resolution, freshness, route, dispatch, verification, recovery, event timeline, abstention reasons) and is never part of the correctness contract (D-025). The backend must remain fully testable headlessly without it. This is a separate artifact from the Phase 2 consumer product UI.

## Hardware-adaptive inference

Never use logic such as `if gpu_name == "RTX 4070": model = ...`. Desktop and laptop GPUs with similar names can have different memory, and Apple Silicon uses unified memory. Probe resources and calibrate.

## Architecture freeze rule

This architecture is the target direction, but detailed capability claims and model/runtime selections remain provisional until Phase 0 measurements satisfy the gates in `BUILD_SPEC.md`.
