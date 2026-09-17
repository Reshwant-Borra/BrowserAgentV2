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
Swappable inference contract. Model output is a proposed structured decision, not authority.

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

## Background-safety model

Background control is not a Boolean platform property. Capability metadata should classify actions/routes such as:

- `BACKGROUND_PROVEN`
- `BACKGROUND_BEST_EFFORT`
- `FOREGROUND_REQUIRED`

Only deterministic probes/test evidence can establish `BACKGROUND_PROVEN`.

## Memory/context architecture

Durable task knowledge lives outside the model. Initial retrieval should favor simple structured queries and SQLite/FTS-style indexing; embeddings/vector retrieval are optional later improvements if evidence shows they are needed.

Graphify, if configured for developer convenience, is repository retrieval tooling only and is not part of ComputerAgent's authoritative runtime memory architecture.

## Hardware-adaptive inference

Never use logic such as `if gpu_name == "RTX 4070": model = ...`. Desktop and laptop GPUs with similar names can have different memory, and Apple Silicon uses unified memory. Probe resources and calibrate.

## Architecture freeze rule

This architecture is the target direction, but detailed capability claims and model/runtime selections remain provisional until Phase 0 measurements satisfy the gates in `BUILD_SPEC.md`.
