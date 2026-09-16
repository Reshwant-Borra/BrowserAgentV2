# BrowserAgentV2 Two-Day Execution Plan V3

> **Re-sequencing required after the P0 campaign (2026-09-15).**
> This plan assumes a Day-2 autonomous loop. The evidence says otherwise:
> [E3's containment analysis](../experiments/qwen_adequacy/results/containment_analysis.json)
> shows the PolicyEngine catches the model's *dangerous* mistakes but not the
> class where it clicks a legitimate control for the wrong reason, and
> [E3](../experiments/qwen_adequacy/REPORT.md) returned `QWEN3_8B_INADEQUATE`.
> Build the **Verifier** before the controller loop, and do not run autonomously
> until the model clears the
> [pre-registered bar](../experiments/qwen_adequacy/ADEQUACY_THRESHOLD.md).
> See [`../experiments/p0_summary/P0_CONSOLIDATION.md`](../experiments/p0_summary/P0_CONSOLIDATION.md).


**Purpose:** define what can realistically be built in two focused days without recreating the previous architecture failure pattern.

**Important:** this is a two-day **architecture proof + working MVP**, not a promise to finish every phase in `FULL_PROJECT_ROADMAP.md`.

The output after two days should be a stable general browser-agent kernel that can execute diverse short/medium tasks, survive common failures, pause for humans, and produce traces. Long-research, connectors, visual fallback, and model training are later phases unless time remains after all gates pass.

---

# Pre-day prerequisites

Before implementation begins:

- repository contracts and schemas agreed;
- BrowserKernel candidate spike instructions written;
- old BrowserAgent fixtures identified for reuse;
- Playwright/browser/model versions pinned for the experiment;
- Qwen3:8B available through Ollama;
- controlled local fixture server ready or old fixtures copied/adapted;
- no unresolved architectural question that would require rewriting controller/state schemas.

If these prerequisites are not met, use the beginning of Day 1 for them rather than writing agent logic.

---

# DAY 1 — Prove the deterministic substrate

## Block 1 — Repository skeleton and contracts

### Build

```text
browser_agent_v2/
  browser/
  model/
  state/
  context/
  verification/
  policy/
  human/
  artifacts/
  app/
  tests/
```

Implement only interfaces/Pydantic models first:
- TaskRecord;
- PlanState;
- Observation;
- PageRecord;
- Decision;
- ActionIntent;
- ActionResult;
- VerificationResult;
- Fact;
- typed KernelError hierarchy.

### Test
- round-trip serialization;
- invalid Decision rejection;
- state-machine legal/illegal transitions.

### Gate
**Do not proceed if component boundaries are unclear.** Fix schemas now, not after browser/model code depends on them.

---

## Block 2 — BrowserKernel candidate spike

Start with Playwright MCP adapter because it already provides snapshot refs and many desired primitives.

Scripted tests only; no model.

### Must prove

1. start dedicated persistent browser;
2. navigate local fixture;
3. capture snapshot;
4. click by current ref;
5. type exact text and verify value;
6. stale ref fails after rerender/navigation;
7. popup/new tab captured;
8. page ownership known at creation time;
9. frame target works;
10. dialog is surfaced;
11. browser profile survives controller restart;
12. pause for manual interaction and fresh-resnapshot works;
13. deterministic download saved to task artifacts;
14. adapter emits useful typed errors.

### Hard decision

**KEEP MCP** if critical invariants work cleanly.

**SWITCH TO DIRECT PLAYWRIGHT** immediately if MCP cannot guarantee:
- target freshness;
- page/tab identity;
- persistent-profile control;
- pause/resume;
- predictable typed results/errors.

Do not spend the whole day patching around the adapter. The `BrowserKernel` contract exists specifically to make this decision replaceable.

---

## Block 3 — Primitive stress tests

Before Qwen integration, run the controlled stress set.

Minimum Day-1 target:

```text
click stable button           50/50
exact fill/type               50/50
stale-target rejection        30/30
popup capture                 20/20
user-tab preservation         20/20
frame action                  20/20
persistent profile restart    10/10
```

Any deterministic failure becomes a fixture and is fixed in the kernel before continuing.

### Special typing fixture

Must include:
- normal input;
- controlled/rerendering input;
- delayed hydration input;
- Enter-to-submit.

This specifically targets the old project's typing/search regressions.

---

## Block 4 — State/event/checkpoint layer

Implement:
- SQLite initialization;
- append-only events;
- current derived TaskState;
- page registry;
- checkpoints;
- artifact records.

Recommended first events:

```text
TASK_CREATED
PLAN_SET
OBSERVATION_CAPTURED
MODEL_DECISION
POLICY_RESULT
ACTION_INTENT_PREPARED
ACTION_RESULT
VERIFICATION_RESULT
CHECKPOINT
TASK_COMPLETED
TASK_FAILED
```

Port/adapt the old repo's event-store idea rather than its controller.

### Gate
Kill/restart a fake task and reconstruct current state from disk.

---

## Block 5 — Verifier + failure classifier

Implement deterministic checks for:
- TYPE value;
- SELECT value;
- URL/navigation;
- element present/absent;
- tab/dialog event;
- download result;
- no-op state change;
- ambiguous submit status.

Return:

```text
SATISFIED
NOT_SATISFIED
AMBIGUOUS
```

Add initial progress detectors:
- repeated semantic action;
- repeated observation/no progress;
- A/B navigation oscillation.

### Day 1 exit gate

At end of Day 1 we should have:

- no Qwen dependency for browser correctness;
- stable BrowserKernel;
- stable page/tab ownership;
- state/event persistence;
- deterministic verification;
- controlled crash/restart support for read-only actions;
- regression fixtures for every bug found.

**If this gate is not met, Day 2 begins by finishing it. Do not compensate by adding model prompting/recovery tricks.**

---

# DAY 2 — Add bounded intelligence and prove general task composition

## Block 6 — Frozen Qwen decision evaluation

Create an initial frozen set of approximately 100 observations/decisions from controlled fixtures.

Test:
- strict JSON Decision schema;
- native Qwen/Hermes tool calling if practical.

Measure:
- schema validity;
- target validity;
- action+target accuracy;
- argument accuracy;
- hallucinated refs;
- latency.

### Decision
Use whichever interface wins measured evaluation.

### Stop condition
If Qwen3:8B is materially below acceptable action selection quality on easy/medium controlled observations, **stop expanding the agent**. Adjust observation/action space or model plan.

Do not hide poor decision quality behind endless retries.

---

## Block 7 — Minimal ContextBuilder

Implement only:

```text
system/policy
canonical goal + success criteria
active subgoal
relevant task facts
previous verified action/result
current page change summary
relevant current observation
allowed Decision schema
```

No running transcript.
No vector DB.
No sophisticated memory compaction.

Track context tokens and model latency every step.

---

## Block 8 — Single authoritative controller loop

Implement controller step:

```text
load state
-> observe
-> build context
-> model Decision
-> schema validate
-> policy validate
-> persist intent if mutating
-> execute kernel action
-> fresh observe
-> verify
-> persist facts/result/checkpoint
-> transition
```

Do not create a separate autonomous execution loop or secondary agent.

---

## Block 9 — Planning + multi-step tasks

Implement a small PlanState:
- 1-8 coarse subgoals;
- active subgoal;
- completion requirements;
- `REPLAN` transition.

Start on local controlled tasks:

```text
1. search -> extract answer
2. form fill -> submit -> verify
3. two-page comparison
4. popup workflow
5. cross-site dependency
6. dynamic DOM churn
```

Fix kernel/state/model contract problems at their actual layer. Do not introduce site-specific handlers.

---

## Block 10 — Human handoff

Add:
- WAITING_FOR_USER;
- WAITING_FOR_CONFIRMATION;
- checkpoint before handoff;
- explicit resume;
- old-ref invalidation;
- full page/tab rediscovery after resume.

Test manual-login fixture end-to-end.

---

## Block 11 — Ambiguous side-effect recovery

Use controlled local endpoint with operation IDs.

Inject crash:
- after intent persist;
- after remote state changes;
- before result persist;
- before verification persist.

Required behavior:
- inspect/reconcile;
- no blind double-submit;
- unresolved ambiguity surfaces clearly.

Consequential browser writes stay disabled until this works.

---

## Block 12 — Controlled autonomous acceptance suite

Target at least these classes:

```text
read/search
form entry
navigation
multi-page extraction
popup/tab
iframe
dynamic rerender
cross-site dependency
human login handoff
loop/replan
prompt-injection fixture
crash/reconcile
```

Pass requirement for the two-day proof:
- all task classes have at least one controlled passing fixture;
- core deterministic tasks pass repeatedly;
- no site-specific code;
- no user-tab closure;
- no unsafe blind retry;
- trace identifies whether each failure is model/runtime/verification/policy.

---

## Block 13 — Low-risk live canaries

Only if controlled suite is stable.

Examples:
- search/read public documentation;
- compare facts across a few public websites;
- use an authenticated read-only account page after human login.

Do not begin with consequential writes to third-party services.

Record website drift/CAPTCHA/invalid-task separately from agent failures.

---

# What is explicitly NOT required by end of Day 2

- full 100-site autonomous benchmark;
- vision-first browsing;
- 100-page research;
- Calendar/Gmail connectors;
- cross-task semantic memory;
- RL/fine-tuning;
- multi-agent delegation;
- desktop/computer control;
- polished UI;
- production packaging.

Trying to add these before the core gates pass would repeat the old project's failure pattern.

---

# Two-day MVP success definition

The two-day build is successful if we can show:

1. the browser primitives are repeatable independently of the LLM;
2. Qwen can select valid actions over the compact observation at an acceptable measured rate;
3. a single controller composes those primitives into diverse multi-step fixture tasks;
4. browser/task state survives controlled interruption;
5. login/manual intervention resumes safely;
6. consequential ambiguity does not cause duplicate actions;
7. failures are typed and diagnosable;
8. no task-specific architecture has been introduced.

The strongest possible two-day result is **a small kernel that we trust**, not a large feature list that only demos successfully once.
