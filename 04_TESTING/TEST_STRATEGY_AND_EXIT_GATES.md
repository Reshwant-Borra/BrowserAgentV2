# Test Strategy and Exit Gates

## Principle

BrowserAgentV2 is not allowed to become “more agentic” until the lower layer is proven independently. Every failure must be attributable to browser mechanics, grounding, model selection, verification, or task planning.

## Phase A — BrowserKernel tests with no LLM

Required fixtures:

1. normal text input and submit;
2. delayed hydration that resets early input;
3. disabled button that later becomes enabled;
4. overlay covering a target;
5. SPA navigation without full page load;
6. same-tab navigation;
7. popup/new-tab navigation;
8. duplicate accessible names;
9. iframe and nested iframe;
10. dialog/alert;
11. infinite/virtualized list;
12. page mutation that invalidates a target;
13. browser restart with persistent profile;
14. manual human interaction followed by resume.

### Primitive pass criteria

Each primitive should pass repeated runs, not one demo. Track at minimum:

- navigation success;
- click success;
- exact fill/value verification;
- key/Enter submission;
- select operation;
- scrolling;
- back navigation;
- popup/tab registration;
- stale-target rejection;
- pause/resume;
- browser restart/recovery.

Target for MVP acceptance: zero silent failures. Clean classified failure is acceptable; an operation reported as successful when its postcondition is false is not.

## Phase B — Playwright MCP adoption spike

Before choosing MCP as the first production adapter, repeatedly prove:

- snapshot refs map to the intended element;
- refs cannot be dangerously reused after state change;
- text entry survives typical dynamic pages;
- popup/tab behavior is observable;
- profile state persists;
- a manually completed login can be resumed from a fresh observation;
- MCP subprocess failure can be detected and recovered without corrupting task state.

If these fail fundamentally, use direct Playwright behind the same `BrowserKernel` interface.

## Phase C — Model action-selection evaluation

Build 50–100 frozen observation cases with known expected decisions.

Test Qwen native tool calling vs strict structured output.

Metrics:

- parse/schema validity;
- correct decision kind;
- correct action;
- correct target;
- unnecessary action rate;
- unsafe/high-impact action rate;
- average latency;
- sensitivity to observation size.

Do not pick the interface based on a few successful interactive examples.

## Phase D — Short autonomous tasks

Only after A–C pass:

- one-step extraction;
- simple search;
- filter/select;
- form fill;
- navigation + extraction;
- basic tab task.

Each run stores a complete trace.

## Phase E — Long-horizon controlled tasks

Test 10–30+ step tasks with intentional faults:

- stale target injected;
- page changed unexpectedly;
- transient browser disconnect;
- popup instead of same-tab navigation;
- manual login handoff;
- duplicate data across pages;
- one irrelevant prompt-injection-like page instruction.

Measure recovery, not just final success.

## Phase F — Diverse real tasks

Use multiple categories without changing architecture:

- travel/research comparison;
- multi-site fact collection;
- school portal assignment extraction;
- authenticated navigation;
- generic forms/search;
- long research with citations.

If a new task category requires a new core architectural branch, stop and determine whether a missing primitive exists instead.

## Failure injection matrix

Every major runtime policy should have a fixture:

```text
TARGET_STALE -> reject and re-observe
TARGET_NOT_ACTIONABLE -> bounded wait/re-observe
HYDRATION_RESET -> readiness wait then bounded retry
AUTH_REQUIRED -> WAITING_FOR_USER
CAPTCHA_REQUIRED -> WAITING_FOR_USER
POSTCONDITION_FAILED -> inspect/re-decide
AMBIGUOUS_SIDE_EFFECT -> never blind retry
MODEL_INVALID_DECISION -> validation feedback then bounded re-decision
RUNTIME_DISCONNECTED -> checkpoint restore + browser rediscovery
```

## Two-day exit gates

### Gate 1 — Browser runtime

Do not integrate Qwen until deterministic browser tests pass repeatedly.

### Gate 2 — Model interface

Do not run broad autonomous tasks until structured-decision evaluation is acceptable and invalid outputs cannot leak into browser execution.

### Gate 3 — State/recovery

A run must survive a process/browser restart from a checkpoint without pretending old browser refs are still valid.

### Gate 4 — Generality

At least five qualitatively different task types must run through the same architecture.

### Gate 5 — Debuggability

For every failure, we must be able to inspect:

```text
current goal/subgoal
observation
model decision
action result
verification
failure class
state transition
```

If that is not possible, the MVP is not ready even if demos sometimes succeed.
