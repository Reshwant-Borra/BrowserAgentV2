# Two-Day Build Plan

**Important:** this is a provisional execution plan. Do not start implementation until the open research gates in `06_OPEN_QUESTIONS/RESEARCH_GAPS.md` are resolved enough to freeze the browser kernel and model interface.

## Build philosophy

The order is deliberately bottom-up:

```text
test fixtures
→ browser kernel
→ observations/targets
→ verification
→ state/checkpoints
→ model adapter
→ controller loop
→ autonomous tasks
```

A failing low-level primitive is fixed at that layer. Do not compensate with prompt instructions or another recovery agent.

# Day 1 — deterministic system

## Step 1: repository skeleton

Create only the minimum modules needed:

```text
browseragent/
  controller.py
  schemas.py
  browser/
    kernel.py
    playwright_mcp.py
  state/
    store.py
  verification/
    verifier.py
  model/
    adapter.py
  policy/
    policy.py
  context/
    builder.py

tests/
  fixtures/
  browser/
  recovery/
```

Do not build site-specific modules.

## Step 2: controlled browser fixtures

Create local/static test pages for:

- simple forms;
- delayed hydration;
- popup/tab;
- iframe;
- duplicate targets;
- overlay/disabled controls;
- stale target after mutation;
- dialog;
- simulated auth/handoff.

These fixtures are more important than early LLM integration.

## Step 3: BrowserKernel interface

Implement the interface and a Playwright MCP adapter candidate.

Required methods:

```text
start
stop
observe
navigate
click
fill
press
select
scroll
back
list_tabs
switch_tab
close_tab
```

The adapter translates MCP/runtime details into BrowserAgent schemas and classified failures.

## Step 4: observation versioning and target validity

Every observation has an id/version. Every target belongs to an observation/page. Reject stale/incompatible targets.

This must have tests before autonomous execution.

## Step 5: deterministic verification

Implement postconditions for:

- fill value;
- URL/title/navigation;
- visible element appearance/disappearance;
- checkbox/select state;
- popup/tab creation;
- no-op/ambiguous result.

## Step 6: tab ownership

Maintain a page registry with ownership (`agent`, `user`, `unknown`). Cleanup can automatically close only `agent` pages.

## Step 7: SQLite state + trace

Persist runs, checkpoints, decisions/actions, verifications, facts, and handoffs.

Keep the schema simple enough to inspect manually.

## Step 8: pause/resume and runtime restart

Prove:

- checkpoint before manual takeover;
- user changes browser state;
- resume invalidates old targets;
- fresh browser discovery occurs;
- current subgoal continues.

Also test MCP/browser subprocess restart from task state.

## Day 1 gate

Stop if deterministic tests are not stable. Do **not** connect Qwen just to make the demo look further along.

# Day 2 — constrained intelligence

## Step 9: frozen Qwen decision eval

Before a live controller loop, run Qwen against frozen observations and choose native tools vs structured `Decision` based on results.

## Step 10: ModelAdapter

Implement only the winning interface. Validate every decision before execution.

## Step 11: ContextBuilder

Construct bounded context from:

- goal/subgoal;
- short plan;
- relevant facts;
- previous verified result;
- current observation/change summary;
- action schema/policy.

No full browser history.

## Step 12: TaskController loop

Implement one state-changing action per controller step:

```text
observe
→ context
→ model decision
→ validate/policy
→ execute
→ verify
→ update state/facts/trace
→ continue/replan/handoff/finish
```

## Step 13: recovery policies

Implement only failure classes already covered by fixtures. No generic catch-all recovery.

## Step 14: task ladder

Run in order:

1. one-step extraction;
2. search + result selection;
3. form/filter task;
4. multi-page research;
5. popup/multi-tab task;
6. authenticated task with human handoff;
7. longer research task with provenance facts.

## Step 15: adversarial test

Include a page containing prompt-injection-like instructions and prove webpage text cannot grant itself new tool authority or secret access.

# What should *not* be built in these two days

- vector database;
- multi-agent orchestration;
- arbitrary JavaScript or shell tools;
- site-specific skill library;
- GUI polish;
- generalized vision system;
- self-healing prompt layers;
- Calendar/Email UI automation if an API/connector can later do the action deterministically.

# Codex handoff rules

When Codex receives implementation tasks:

1. point it to specific architecture/test documents;
2. give one bounded milestone at a time;
3. require tests and exact commands/results;
4. prohibit architecture redesign unless a failing test demonstrates a blocker;
5. require documentation/ADR update when assumptions change;
6. never ask it to “make BrowserAgent work” as one giant prompt.

# Success at end of Day 2

Success is not feature count. Success means we own a kernel where failures are localizable, state is durable, browser actions are deterministic, Qwen has a small action surface, and the same loop works across different task types.
