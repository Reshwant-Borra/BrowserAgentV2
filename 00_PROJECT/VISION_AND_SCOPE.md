<!-- Source section: 00_PROJECT/VISION.md -->

# Vision

BrowserAgentV2 should become a **general local browser operator**, not a collection of task-specific automations.

The intended experience is that a user can give a goal such as:

- compare information across several websites;
- collect assignments from authenticated school portals;
- research a topic across many pages and preserve findings;
- fill normal forms and search interfaces;
- work through multi-page web workflows while asking the user for login/MFA when necessary.

The agent should not require a new architecture for each task category. The same observation model, action primitives, task state, verification layer, and human-handoff mechanism should compose across tasks.

## What “general” means

“General” does **not** mean that the model has unrestricted control over the browser. It means the task planner can combine a stable set of primitives in new ways.

The architecture should make it possible to add specialized integrations later (Calendar APIs, email connectors, structured site adapters, etc.) without changing the core browser loop.

## Reliability priority

For the first version, the priority order is:

1. Correctness
2. Recoverability/debuggability
3. Generality
4. Speed
5. Cost/token efficiency

This deliberately favors a slower system that can explain what it did over a faster system that sometimes clicks or types unpredictably.

## Design principle

The model is not the browser driver. It is the planner/controller.

The browser runtime owns:

- page and tab lifecycle;
- element resolution;
- click/fill/key semantics;
- waiting and timeouts;
- post-action verification;
- retries;
- browser-session persistence;
- screenshots/traces/logging;
- refusal to execute invalid or unsafe operations.

The model owns:

- interpreting the user goal;
- choosing the next subgoal;
- selecting an allowed action;
- interpreting extracted information;
- deciding whether the task is complete or needs replanning.

---

# Requirements

## Functional requirements

The MVP browser kernel must support navigation, compact structured observation, click, reliable fill, targeted keypress, option selection, scrolling, back navigation, agent-owned tab management, popup detection, text/fact extraction, dialog/blocked-state detection, human pause, and resume without losing task state.

The agent layer must support a user goal, current subgoal, gathered facts, completed/failed steps, bounded replanning, explicit completion/failure states, and saving/restoring a run.

## Reliability requirements

- No model-triggered reload/refresh in the MVP action schema.
- No blind action retry; retry requires a classified failure and fresh observation.
- No stale element-ref reuse after meaningful page mutation/navigation.
- No typing into the currently focused element unless the target is explicitly resolved.
- Every state-changing action emits before/after events and a verification result.
- Browser actions have bounded timeouts.
- Clean failure is preferable to an unverified guess.
- User tabs are never closed by cleanup logic unless explicitly requested.

## Model requirements

- Browser actions must be schema-validated.
- Invalid tool calls are rejected and re-prompted, never partially executed.
- The model receives compact task state and current observations, not raw history.
- Qwen3 8B through Ollama is the baseline local model.

## Human-in-the-loop requirements

Pause for password entry, MFA/2FA, CAPTCHA, ambiguous account selection, irreversible/high-impact final submission, and permissions/consent requiring user understanding. Checkpoint before handoff and re-observe from scratch on resume.

---

# Non-Goals for the Two-Day MVP

The first version should not attempt unrestricted JavaScript/code execution against arbitrary pages, a giant site-specific skill library, CAPTCHA solving, password/MFA secret storage, full desktop control, irreversible submissions without confirmation, vectorizing every browsing action, multi-agent delegation trees, self-modifying production code, automatic refresh as generic recovery, vision-first coordinate clicking, model fine-tuning, or passing an entire live-web benchmark before primitives are stable.

---

# Two-Day Target

The two-day objective is not “build Comet.” It is to prove a **small browser-agent kernel** stable enough to extend.

## Day 1 outcome: deterministic browser kernel

Without an LLM, repeatedly prove navigation, snapshot refs, click, fill with value verification, Enter/search submission, dynamic-page stability without arbitrary refresh, popup/tab registration, user-vs-agent tab ownership, page-change detection, classified failures, logging, and pause/resume.

## Day 2 outcome: constrained local agent loop

Only after Day 1 passes, connect Qwen3 8B and test one-step extraction, multi-step search/filtering, multi-page information gathering, a multi-tab task, authenticated workflow with manual login handoff, and a longer research task that accumulates facts across pages.

## Exit criteria

1. Primitive tests pass independently of the LLM.
2. A model mistake cannot cause undefined browser behavior; it can only choose an allowed action that may succeed or fail.
3. Failures produce an inspectable trace: observation → action → browser result → verification → next state.
4. The same kernel runs multiple qualitatively different tasks without architecture changes.
5. A failed long task can resume from task state instead of restarting.
