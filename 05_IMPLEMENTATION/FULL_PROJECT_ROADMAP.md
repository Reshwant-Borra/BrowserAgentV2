# BrowserAgentV2 Full Project Roadmap

**Goal:** provide the complete build order from an empty V2 codebase to a reliable general browser agent, while preserving the two-day MVP goal for the kernel/agent loop and leaving advanced research capabilities as later phases.

## Guiding rule

Each phase has:
- prerequisites;
- implementation scope;
- explicit non-goals;
- tests;
- exit gate;
- fallback if the gate fails.

Codex should never be asked to "build the agent" across several gates at once.

---

# Phase 0 — Research/architecture freeze

## Objectives
- resolve BrowserKernel candidate;
- resolve model decision interface;
- finalize state schemas;
- finalize failure classifications;
- audit old repo for reusable tests/utilities;
- pin first implementation versions.

## Deliverables
- `END_TO_END_SYSTEM_SPEC.md` approved;
- `MASTER_VALIDATION_PLAN.md` executable;
- decision gate matrix has no unresolved P0 assumptions that would require a rewrite.

## Exit gate
- BrowserKernel deterministic spike passes;
- Qwen frozen decision eval establishes viable interface or model upgrade decision.

---

# Phase 1 — Repository skeleton and contracts

## Build

```text
browser_agent_v2/
  app/
    task_service.py
    controller.py
  browser/
    kernel.py
    models.py
    errors.py
    mcp_adapter.py OR playwright_adapter.py
  model/
    adapter.py
    qwen_ollama.py
    schemas.py
  state/
    store.py
    events.py
    schemas.py
  context/
    builder.py
  verification/
    verifier.py
    progress.py
  policy/
    engine.py
  human/
    handoff.py
  artifacts/
    store.py
  tests/
    fixtures/
    unit/
    integration/
```

## Principles
- interfaces exist before implementation grows;
- Pydantic schemas are canonical runtime contracts;
- controller imports interfaces, not Playwright/MCP internals.

## Exit gate
- schemas serialize/deserialize;
- SQLite migration initializes;
- empty task lifecycle `NEW -> INITIALIZING -> RUNNING -> COMPLETED/FAILED` test passes with fake components.

---

# Phase 2 — BrowserKernel deterministic foundation

## Build first
- runtime startup/shutdown;
- dedicated persistent browser profile;
- page registry and ownership;
- snapshot/observation;
- navigate;
- click;
- type/fill;
- select;
- press key;
- scroll;
- back;
- tabs/popups;
- dialogs;
- frames;
- screenshot fallback hook;
- downloads;
- uploads from approved artifact workspace only.

## Do not connect Qwen yet

Use scripted deterministic test driver.

## Exit gate
- primitive stress thresholds in `MASTER_VALIDATION_PLAN.md` pass;
- zero user-tab ownership violations;
- stale refs reject safely;
- no uncontrolled refresh/retry behavior.

## Fallback
- if MCP fails invariants, implement Direct Playwright adapter; do not change controller contracts.

---

# Phase 3 — State/event/checkpoint foundation

## Build
- SQLite `runs`/`events`/derived state;
- append-only event trace;
- action intents;
- action results;
- observation metadata;
- checkpoints;
- artifact records;
- replay/rebuild current state from event log.

## Recommended event sequence

```text
TASK_CREATED
PLAN_SET
OBSERVATION_CAPTURED
MODEL_DECISION
POLICY_RESULT
ACTION_INTENT_PREPARED
ACTION_RESULT
VERIFICATION_RESULT
FACT_ADDED / PLAN_UPDATED
CHECKPOINT
...
TASK_COMPLETED
```

## Exit gate
- process can be killed/restarted after any read-only boundary and reconstruct identical task state;
- event log remains append-only.

---

# Phase 4 — Verification and recovery semantics

## Build
- typed verifier `SATISFIED | NOT_SATISFIED | AMBIGUOUS`;
- action-specific defaults;
- task/subgoal postconditions;
- stale-target recovery;
- bounded transient read retry;
- ambiguous side-effect reconciliation;
- progress/loop detector.

## Critical requirement

Complete crash-injection fixture before model is allowed to execute consequential submits.

## Exit gate
- no duplicated state-changing operation across injected crash matrix;
- no infinite fixture loops;
- verifier false-positive cases in master suite pass.

---

# Phase 5 — ModelAdapter and frozen decision eval

## Build
- Qwen3/Ollama adapter;
- structured output/tool interface candidate;
- timeout and token metrics;
- strict Pydantic validation;
- bounded contract repair.

## Thinking policy experiment

Qwen3 supports thinking and non-thinking modes. Test:
- non-thinking for simple action selection;
- thinking for replan/ambiguous reasoning;
- always-thinking baseline.

Choose based on action accuracy and latency, not intuition.

Ollama supports JSON-schema structured outputs, which makes the strict `Decision` schema practical.

## Exit gate
- frozen model decision thresholds pass;
- if they do not, stop and revise model strategy rather than compensate with browser retries.

---

# Phase 6 — ContextBuilder + single-step agent

## Build
- canonical goal/success criteria block;
- current subgoal;
- relevant facts;
- previous verified action;
- current change summary;
- pruned observation;
- allowed decision schema/policy summary.

## First autonomous tasks

Only one-step/easy multi-step local fixtures.

## Exit gate
- agent chooses correct primitive without site-specific branches;
- context stays within configured budget;
- full history never leaks into prompt by accident.

---

# Phase 7 — Planning and multi-step controller

## Build
- coarse PlanState/subgoals;
- explicit replanning state;
- completion requirements;
- subgoal transitions;
- progress detector integration.

## Keep simple

One model can plan/replan and select actions. Do not create planner/executor agents unless evaluation proves benefit.

## Exit gate
- controlled 5-20 step tasks pass repeatedly;
- cross-site dependency fixture passes;
- no architecture patch for a particular site.

---

# Phase 8 — Human handoff and confirmations

## Build
- `WAITING_FOR_USER`;
- `WAITING_FOR_CONFIRMATION`;
- UI/status representation;
- resume token/signal;
- fresh rediscovery after handoff;
- risk-policy preview for consequential writes.

## Exit gate
- manual login/MFA fixture survives resume;
- all old refs invalidated;
- task/subgoal remains consistent;
- confirmation cannot be bypassed by page text.

---

# Phase 9 — FactStore and medium-length research

## Build
- structured facts;
- provenance;
- normalized keys;
- contradictions;
- fact retrieval by subgoal;
- source revisit/deduplication.

Start with SQLite queries/FTS. No vector DB unless measured retrieval failures justify it.

## Exit gate
- multi-page comparison retains facts after navigation;
- no dependence on complete transcript;
- provenance appears in final answer/report.

---

# Phase 10 — File workflows

## Build
- download artifact persistence/hash;
- safe filename/path handling;
- approved upload artifact IDs;
- file chooser/drop handling;
- confirmation boundary for unexpected uploads.

## Exit gate
- artifacts survive browser context shutdown;
- page cannot select arbitrary filesystem files;
- provenance recorded.

---

# Phase 11 — Security hardening

## Build
- action authority/policy engine;
- cross-origin data-transfer checks;
- sensitive fact labels;
- prompt-injection fixture corpus;
- origin allow/block convenience configuration;
- secrets excluded from prompt/trace.

## Exit gate
- security fixture suite has zero capability escalations;
- all consequential actions remain policy-gated.

Note: no security benchmark result is treated as proof of complete prompt-injection immunity.

---

# Phase 12 — Visual fallback

Only after logs show semantic observation cannot complete an important class of valid tasks.

## Build
- screenshot request;
- bounding boxes/set-of-mark if required;
- vision-capable model adapter if local hardware/model permits;
- coordinate interaction remains isolated in BrowserKernel.

## Exit gate
- visual fallback improves a frozen inaccessible-control set without reducing normal semantic-path reliability.

---

# Phase 13 — Structured connectors/API routing

Examples:
- Calendar;
- email;
- Drive/docs;
- other structured services.

## Build
- capability registry;
- route structured operations to connector when available;
- preserve confirmation/policy semantics;
- browser remains fallback/discovery layer.

## Why later

The browser kernel must work generically before connector convenience is allowed to mask browser failures.

---

# Phase 14 — Long-research mode

Target tasks like:
- compare many products/places/sources;
- research 50-100+ pages;
- gather structured evidence over a long run.

## Add
- research questions/coverage plan;
- source queue;
- facts/evidence graph or relational structures;
- contradiction tracking;
- source quality/diversity;
- completeness evaluator;
- periodic checkpoint/resume;
- deterministic calculation helpers where needed.

## Exit gate
- bounded model context throughout long run;
- restart/resume without lost facts;
- source dedupe works;
- final output traceable to evidence;
- stopping based on coverage, not arbitrary page count.

---

# Phase 15 — Model improvement / training if necessary

This phase is conditional.

Trigger if:
- Qwen3:8B model decision eval remains below target;
- unseen-site generalization is poor despite stable browser runtime;
- replan errors dominate trace statistics.

Options in order:
1. improve observation/action alignment;
2. collect successful/failed trajectories;
3. supervised fine-tuning on decisions;
4. trajectory synthesis (AgentTrek-style research direction);
5. RL/web-curriculum training (WebRL-style direction);
6. larger local model if hardware allows.

The runtime/state architecture should not change for model training.

---

# Phase 16 — External benchmark program

Use:
- BrowserGym/AgentLab for reproducibility;
- WebArena-Verified for deterministic audited scoring;
- selected Online-Mind2Web for live realism;
- AssistantBench/WebChoreArena later for long research/memory.

Benchmark failures are triaged into:

```text
MODEL
GROUNDING
BROWSER_RUNTIME
VERIFIER
RECOVERY
SECURITY/POLICY
WEBSITE_INVALID/CHANGED
AUTH/CAPTCHA
UNSUPPORTED_CAPABILITY
```

---

# Phase 17 — UI/productization

Only after core reliability.

## UI needs
- task input;
- run status/current subgoal;
- browser status;
- human intervention request;
- confirmation request;
- stop/cancel;
- trace/log view for debugging;
- final result + provenance/artifacts.

Avoid building a polished UI around a moving runtime architecture.

---

# Phase 18 — Packaging/distribution

## Build
- one-command health check/start;
- dependency/version checks;
- model presence check;
- dedicated browser profile setup;
- platform-specific Mac/Windows launch behavior;
- clean runtime directory policy;
- update/migration process.

The old repo's health-check UX is a useful reference, but V2 should use the new architecture underneath.

---

# What must NOT happen during the roadmap

- new site-specific code because one task fails;
- generic refresh added as recovery;
- multiple autonomous agents added without benchmark evidence;
- hidden retries around state-changing actions;
- entire event history fed back to Qwen;
- CDP daily-driver attachment made default before fidelity tests;
- model allowed arbitrary JS/shell/filesystem access;
- memory/vector database added because it sounds advanced rather than because measured retrieval requires it.

---

# Project completion definition

BrowserAgentV2 is "complete" for the general local-agent vision when it can:

1. reliably execute deterministic browser primitives;
2. plan and complete diverse multi-step tasks on unseen sites without site-specific code;
3. survive browser/controller restarts;
4. pause/resume for login/MFA/confirmation;
5. retain provenance-bearing facts across many pages;
6. complete medium/long research with bounded context;
7. safely handle downloads/uploads;
8. resist capability escalation from untrusted page content;
9. route structured integrations when more reliable than UI automation;
10. provide traces that explain every failure;
11. pass a maintained internal regression suite plus selected external benchmarks at acceptable measured success rates.

The two-day goal is not to finish Phases 0-18. It is to finish enough of Phases 0-8 to prove that the architecture is sound and capable of growing without another rewrite.
