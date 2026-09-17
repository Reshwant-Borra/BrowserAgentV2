# ComputerAgent Product Definition

## Product

ComputerAgent is a **local-first, persistent computer-use agent** intended to work across ordinary consumer macOS and Windows machines, with Linux following as a later platform target.

The goal is not to give a local model unrestricted control of a mouse. The goal is to let a user delegate broad computer tasks while ComputerAgent chooses the safest and most reliable interaction mechanism available on that machine and application.

## Core experience

A user gives ComputerAgent a goal. ComputerAgent plans and executes the task while keeping durable state outside the model, verifying important state changes, and allowing the user to continue using the computer whenever a proven background-safe route exists.

The interaction hierarchy is:

1. Native API / connector / deterministic tool
2. Browser DOM/accessibility semantics
3. Desktop accessibility semantics (macOS AX / Windows UIA)
4. Parsed screenshot or visual grounding
5. Capability-gated isolated workspace/desktop for coordinate interaction
6. Human handoff when blocked, unsafe, ambiguous, or at an authentication/security boundary

## The “second cursor” promise

ComputerAgent should provide the **experience** of an independent agent cursor without promising a literal second arbitrary host pointer.

- Browser and semantic accessibility actions should avoid moving the user's physical cursor.
- Coordinate-heavy visual interaction should be isolated where hardware/platform support makes that practical.
- A cosmetic Agent Cursor can later visualize semantic actions.
- Generic host coordinate injection must not be the default execution mechanism.

## Local-first intelligence

ComputerAgent should adapt inference to measured hardware rather than require one model on every machine. Small local planners and on-demand visual specialists are preferred over keeping a huge model in the hot action loop.

Model/runtime choices remain Phase 0 benchmark questions. Current candidates from the research include Qwen3.5 small models, Qwen3-8B as a regression/control baseline, UI-TARS-1.5-7B for GUI grounding, Gemma edge-oriented comparators, llama.cpp as a primary embedded-runtime candidate, and MLX as an Apple Silicon comparator.

## Long-running tasks

A long task must not become a giant prompt. ComputerAgent owns durable GoalState, PlanState, EventStore, FactStore, ArtifactStore, RecoveryState, policy state, and retrieval. The model receives a bounded working context containing only the active goal constraints, current subgoal, current observation, relevant facts, recent changes, and unresolved verification/recovery information.

## Reliability promise

ComputerAgent should prefer a verified partial/handoff state over falsely claiming completion. State-changing operations are journaled, observed, verified, and reconciled. Ambiguous crashes/timeouts must not cause blind duplicate side effects.

## Security boundary

Untrusted webpage/application content cannot grant itself authority. Consequential actions are governed by deterministic policy. Login, MFA, CAPTCHA, secrets, TCC/UAC/security prompts, and similar boundaries use human handoff.

## Platforms

- **P0:** macOS and Windows
- **P1:** Linux

Background behavior is capability- and application-specific. ComputerAgent must not promise arbitrary invisible manipulation of every application.

## Product phases

- **Phase 0:** experimentally prove capabilities, model/runtime choices, non-interference, endurance, recovery, and safety.
- **Phase 1:** build the OS-independent ComputerAgent controller and production adapters around measured capabilities.
- **Phase 2:** build the polished consumer application, onboarding, Agent Cursor, model manager, installers, updates, and rollback.

## Current priority

Phase 0. Evidence first; product polish later.
