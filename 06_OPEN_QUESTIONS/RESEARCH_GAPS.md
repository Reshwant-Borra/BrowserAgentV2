# Open Research Questions and Decision Gates

**Status:** design plan is comprehensive; final architecture freeze still requires empirical P0 results.

The repository now contains a full top-to-bottom architecture and project roadmap. The remaining open questions are mostly things documentation/papers cannot answer for our exact machine, model, browser version, and workloads. They require small experiments, not another speculative architecture layer.

For the canonical decision table, also see `DECISION_GATES_V2.md`.

## P0 — Must resolve before final implementation freeze

### 1. Playwright MCP vs direct Playwright

Run the deterministic BrowserKernel adoption spike.

Measure:
- typing/fill reliability on dynamic/controlled apps;
- stale-ref semantics;
- popup/tab/page identity;
- iframe/dialog behavior;
- dedicated persistent profile behavior;
- controller/browser restart;
- human takeover/resume;
- file operations;
- error classification quality;
- performance/latency overhead.

**Decision rule:** use MCP if it cleanly preserves our invariants; otherwise implement direct Playwright behind the exact same `BrowserKernel` contract.

### 2. Qwen Decision interface

Compare:

```text
A. strict single Decision JSON schema
B. native/Hermes-style tool calling
```

Use the same frozen 100-300 Observation -> Decision cases.

Measure:
- schema validity;
- correct action/target;
- exact arguments;
- hallucinated targets;
- safe ask/replan behavior;
- latency/tokens.

Do not choose from anecdotal demos.

### 3. Qwen3:8B capability threshold

This is distinct from output syntax.

Question:

> Given a good compact observation/action space, does zero-shot Qwen3:8B make correct enough decisions to be the first autonomous policy?

If no:
- simplify observation/action contracts;
- try thinking-mode policy changes;
- test a larger local model if practical;
- then use the supervised/trajectory/RL path in `01_RESEARCH/MODEL_STRATEGY_AND_TRAINING_PATH.md`.

Do not add browser recovery heuristics to hide a model-quality problem.

### 4. Ambiguous side-effect reconciliation

Rule is already resolved: **no blind replay**.

What must be experimentally proven:
- exact event ordering/checkpoint boundaries;
- what information the controller has after different crash points;
- whether current page/server state can prove action success/not-applied;
- how unresolved ambiguity reaches the user.

Use a deterministic local endpoint with operation IDs and crash injection.

### 5. Observation invalidation policy

Find the smallest safe invalidation policy.

Experiment across:
- full navigation;
- SPA route changes;
- DOM subtree rerender;
- controlled input rerender/hydration;
- frame reload/detach;
- tab switch/new popup;
- modal/dialog changes;
- manual user action during handoff.

Under-invalidation risks wrong targets; over-invalidation increases snapshots/model calls.

### 6. Dedicated profile + page ownership invariants

The architecture choice is provisionally strong, but prove repeatedly:
- auth/session persists across controller restarts;
- AGENT/USER/UNKNOWN page ownership is correct at creation/discovery;
- only AGENT pages are auto-closed;
- explicit target tasks never hijack unrelated pages;
- current-page tasks intentionally use the user-selected page.

### 7. Security/prompt-injection behavior

Run adversarial controlled pages that attempt to:
- rewrite goal/instructions;
- request secrets/cookies;
- trigger uploads;
- initiate unexpected cross-origin writes;
- impersonate system/tool messages;
- bypass confirmations.

Required result is not “the model noticed the injection”; required result is **the architecture prevents capability escalation even if the model is misled**.

## Completed research gaps

### Old BrowserAgent audit — RESOLVED AT RESEARCH LEVEL

The actual repo was inspected. Reuse matrix and old regression tests are documented in:
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`

### Downloads/uploads — DESIGNED, VERIFY DURING KERNEL SPIKE

Current design:
- downloads saved explicitly into ArtifactStore because browser temp files are not durable;
- sanitized unique artifact paths + provenance/hash;
- uploads may reference only approved task artifact IDs;
- no arbitrary model-supplied local path;
- unexpected/sensitive upload requires policy/confirmation.

### Iframes — DESIGN RESOLVED, VERIFY IMPLEMENTATION

Target identity includes frame scope; frame detach/reload invalidates the target.

### Progress/loop detection — DESIGN RESOLVED, TUNE THRESHOLDS LATER

Signals include:
- repeated semantic action;
- repeated observation/no useful change;
- A/B navigation oscillation;
- repeated postcondition failure;
- no new research facts/progress.

Detector emits evidence; controller owns replan/fail transition.

### Long-research memory design — RESOLVED AT ARCHITECTURE LEVEL

See `02_ARCHITECTURE/LONG_RESEARCH_AND_MEMORY_ARCHITECTURE.md` for:
- research questions/gaps;
- source queue;
- provenance facts;
- URL/content/claim dedupe;
- contradiction groups;
- source diversity;
- coverage-based stopping;
- bounded context;
- resume/checkpoint semantics.

It still requires later implementation/benchmarking after short/medium tasks are stable.

## P1 — Resolve after core kernel loop is stable

### Visual fallback trigger

Determine from failed semantic tasks exactly when screenshot/vision is required.

Questions:
- which valid controls disappear from semantic/DOM view;
- local vision-model capability/latency;
- whether set-of-mark is needed;
- coordinate action safety/verification.

Do not build vision-first browsing without evidence.

### Virtualized/infinite-scroll pages

Design fixture for:
- items rendered only near viewport;
- repeated loading;
- duplicate/recycled DOM nodes.

Need safe observation/search/scroll strategy that does not assume the full list exists in DOM.

### Rich editors / drag-drop / complex widgets

After normal form primitives pass, test:
- contenteditable editors;
- custom dropdowns;
- drag/drop;
- date pickers;
- canvas controls.

Add general BrowserKernel capabilities only when a recurring task class requires them.

### Connector/API routing

Define capability contract for structured integrations such as Calendar/email/Drive.

Need rules for:
- browser vs connector routing;
- consistent confirmation/policy;
- provenance/state transfer;
- connector failure/fallback;
- no hidden app-specific browser logic.

## P2 — Later research/program expansion

### Progressive determinism / reusable recipes

Study whether repeated successful observation->action patterns should be cached/replayed deterministically, similar in spirit to Stagehand-style workflows.

Requirements before adopting:
- stable element/semantic anchors;
- invalidation/version strategy;
- fallback to normal model decision;
- no site-specific architecture explosion.

### Existing daily-driver browser attachment

Dedicated BrowserAgent profile stays default. Optional existing-browser attach needs separate research on:
- CDP lower-fidelity limitations;
- privacy boundaries;
- tab ownership;
- extension/service-worker behavior;
- browser launch flags;
- session locking.

### Cross-task persistent memory

Do not add until task-local facts are proven.

Research:
- user-controlled retention;
- staleness/expiration;
- privacy/deletion;
- retrieval boundaries;
- avoiding accidental transfer between unrelated tasks.

### Long-horizon model training

If measured traces show the model is the limiting factor, research/implement:
- supervised decision tuning;
- trajectory synthesis (AgentTrek direction);
- multi-turn RL (WebRL / WebAgent-R1 direction);
- world-model/simulated rollouts (DynaWeb direction).

The runtime/state architecture should remain unchanged.

## Research completion definition

Research is “complete enough to build the planned MVP” when:

1. all P0 questions have recorded experiment results;
2. `END_TO_END_SYSTEM_SPEC.md` is updated to match those results;
3. `DECISION_GATES_V2.md` has no unresolved architecture-changing P0 item;
4. every high-risk invariant has a controlled fixture/test;
5. model-vs-runtime failures are independently measurable;
6. Day 1/Day 2 tasks can be handed to Codex in bounded stages without asking it to make architectural choices;
7. README/status/sources/master documents are internally consistent.

At that point, remaining P1/P2 topics are planned extensions rather than reasons to redesign the core.
