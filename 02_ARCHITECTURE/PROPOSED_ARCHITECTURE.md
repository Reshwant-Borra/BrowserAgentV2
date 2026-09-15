# Proposed BrowserAgentV2 Architecture

**Status:** provisional; architecture freeze depends on open decision gates and deterministic spikes.

## Goal

Build the smallest general architecture that can reliably compose browser tasks without adding a new subsystem every time a new example is introduced.

## High-level system

```text
User Goal
   |
   v
TaskController <-------------------------- Human Takeover / Approval
   |
   +--> StateStore / CheckpointStore
   |
   +--> ContextBuilder
   |       |
   |       v
   |    ModelAdapter (Qwen/Ollama)
   |       |
   |       v
   +--> Decision Schema + Policy Validator
   |       |
   |       v
   +--> BrowserKernel interface
   |       |
   |       +--> Playwright MCP Adapter (first candidate)
   |       +--> Direct Playwright Adapter (fallback candidate)
   |
   +--> Verifier / Progress Detector
   |
   +--> FactStore / Provenance
   |
   +--> EventTrace / Artifacts
   |
   +-------------------------------> next controller step
```

## 1. TaskController

The controller is the only component that advances the run state. It executes a simple state machine rather than recursively invoking agents.

Suggested states:

```text
NEW
RUNNING
WAITING_FOR_USER
WAITING_FOR_CONFIRMATION
REPLANNING
COMPLETED
FAILED
CANCELLED
```

A controller step should:

1. load task state;
2. obtain current browser observation;
3. build bounded context;
4. ask model for one `Decision`;
5. validate decision and policy;
6. execute permitted operation;
7. verify outcome;
8. update state/facts/trace;
9. choose next runtime state.

## 2. BrowserKernel

The model never talks directly to Playwright, MCP, or CDP. It talks indirectly through decisions interpreted by the controller.

Kernel responsibilities:

- own browser process/session;
- maintain page/tab registry;
- create observations;
- resolve current targets;
- reject stale targets;
- perform deterministic interactions;
- wait using browser-native semantics;
- expose classified errors;
- support pause/resume/reconnect;
- never close user-owned tabs by accident.

## 3. Observation model

Each observation is immutable and versioned.

Conceptual shape:

```json
{
  "observation_id": "obs_0042",
  "active_page": {"id":"p3","url":"...","title":"..."},
  "tabs": [],
  "status": {"dialog":null,"blocked":false,"loading":false},
  "changes": [],
  "elements": [
    {"target":"p3:obs_0042:e17","role":"textbox","name":"Search","value":""}
  ],
  "text_blocks": []
}
```

A target from an older incompatible observation is rejected.

## 4. ModelAdapter

Qwen/Ollama is behind an adapter. Model output is strictly schema-validated. The rest of the architecture should not change if the model changes.

Decision categories:

- browser action;
- extraction;
- replan;
- ask user;
- request confirmation;
- finish;
- fail.

One state-changing browser action per step for the MVP.

## 5. ContextBuilder

Construct a bounded packet from:

- goal;
- current subgoal/plan;
- relevant facts;
- previous decision + verified result;
- current observation/change summary;
- allowed actions;
- policy state.

The ContextBuilder is responsible for truncation/filtering. The full trace never gets copied into the prompt.

## 6. StateStore

Use SQLite initially.

Suggested logical tables:

```text
runs
subgoals
checkpoints
observations
browser_events
actions
verifications
facts
human_handoffs
confirmations
artifacts
```

Do not over-normalize during the two-day MVP. The goal is explicit state and inspectable traces.

## 7. Verifier

A browser API returning success only means the operation executed without throwing. It does not prove task progress.

Verifier responsibilities:

- target-value verification after fill;
- navigation/URL/title changes;
- expected element/state appears/disappears;
- new tab/dialog detection;
- extraction completeness;
- no-op detection;
- postcondition result: `SATISFIED | NOT_SATISFIED | AMBIGUOUS`.

The model may suggest an expected outcome, but verification logic should use deterministic evidence whenever possible.

## 8. RecoveryManager

Recovery is policy, not improvisation.

Each classified failure maps to bounded behavior. Example:

```text
TARGET_STALE -> fresh observation -> re-decide
TARGET_NOT_ACTIONABLE -> fresh observation/short wait -> one bounded retry or re-decide
HYDRATION_RESET -> readiness wait -> fresh observation -> retry once
AUTH_REQUIRED -> WAITING_FOR_USER
CAPTCHA_REQUIRED -> WAITING_FOR_USER
POSTCONDITION_AMBIGUOUS after side effect -> inspect current state; never blind replay
MODEL_INVALID_DECISION -> validation feedback -> bounded re-decision
RUNTIME_DISCONNECTED -> restore checkpoint/profile -> rediscover browser state
```

No generic refresh recovery action exists in the model schema.

## 9. Human handoff

Before handoff, checkpoint. During handoff, automation stops. On resume, all prior browser targets are invalidated and the browser state is rediscovered.

## 10. FactStore

Research findings are data, not chat history. Facts carry provenance and can be deduplicated/contradicted. The planner retrieves only facts relevant to the current subgoal.

## 11. Tab ownership

Every known page/tab gets ownership metadata:

```text
user
agent
unknown
```

Only agent-owned tabs can be automatically cleaned up. If ownership is uncertain, do not close it.

## 12. Process architecture

Recommended first implementation:

```text
Python application
  - controller
  - SQLite
  - Qwen/Ollama adapter
  - MCP client
       |
       v
Playwright MCP subprocess
       |
       v
Dedicated persistent Chromium profile
```

If Playwright MCP fails the adoption spike, replace only the MCP adapter with direct Playwright.

## Anti-complexity rules

Do not add a subsystem unless a reproducible failing test requires it. Specifically, avoid during MVP:

- multi-agent delegation;
- site-specific workflow classes;
- arbitrary browser JavaScript;
- shell/code tools;
- vector database;
- generic self-healing loops;
- model-controlled refresh;
- separate planner/verifier LLMs unless benchmarks prove necessary.

## Architecture freeze condition

This design becomes implementation-frozen only after:

1. BrowserKernel spike passes;
2. Qwen decision-interface eval chooses a format;
3. state-changing retry semantics are tested;
4. test pages and exit gates are defined;
5. the old BrowserAgent repository is audited for reusable components rather than copied blindly.
