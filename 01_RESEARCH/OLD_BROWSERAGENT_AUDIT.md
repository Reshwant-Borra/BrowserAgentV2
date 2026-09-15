# Old BrowserAgent Codebase Audit

**Source audited:** `Reshwant-Borra/BrowserAgent` current `main` branch on 2026-09-15.

**Purpose:** restart the architecture without throwing away proven engineering. The old repository is treated as evidence and a parts bin, not as a base that must be incrementally patched.

## High-level finding

The old repo contains several genuinely valuable pieces: deterministic browser primitives, an append-only SQLite event log, crash-rebuild concepts, context budgeting, deterministic verification, loop detection, local-model abstraction, and a substantial fixture/test corpus.

The main architectural problem is not that everything was bad. It is that too many responsibilities accumulated in very large orchestration modules and interacted through recovery/planning/resource-resolution behavior. The result was difficult to reason about and easy to regress.

The safest migration strategy is therefore:

> **reuse contracts, tests, and small deterministic modules first; rewrite orchestration around the V2 state machine; only port old behavior after it passes a V2 requirement/test.**

## Repository evidence

The old tree includes:

```text
agent/controller.py      ~104 KB
agent/loop.py             ~69 KB
memory/task_memory.py     ~28 KB
batch/orchestrator.py     ~27 KB
agent/workspace_ops.py    ~24 KB
memory/workspace_store.py ~11 KB
browser/playwright_backend.py ~14 KB
```

A controller over 100 KB plus a separate ~69 KB loop is a strong maintainability signal: orchestration policy, browser behavior, recovery, planning, and task semantics have become too interdependent.

By contrast, several small modules have clear single responsibilities and are much better reuse candidates.

---

# KEEP / ADAPT / REWRITE / DELETE matrix

## KEEP CONCEPT + PORT WITH SMALL CHANGES

### `memory/event_store.py`

**Why:** strong fit for V2.

The module is explicitly append-only and treats derived task state as rebuildable. This supports crash recovery and auditability without requiring a complex external database.

Useful properties:
- stdlib SQLite;
- explicit event types;
- append + commit boundary;
- deterministic replay support;
- no update/delete of history.

**V2 action:** adapt schema/event names to the new controller, but preserve the append-only event-log concept.

### `agent/loop_detector.py`

**Why:** deterministic and narrow.

Existing useful signals:
- repeated semantic action;
- no-op detection;
- repeated action fingerprint;
- A/B navigation oscillation;
- modal obstruction.

**V2 action:** port/refactor behind a `ProgressDetector` interface. Add observation-repeat and no-new-fact signals. Do not let it directly decide recovery; it only emits evidence.

### deterministic context construction concepts from `agent/context_builder.py`

The old implementation reconstructs context from persisted state rather than relying on an in-memory chat list and already uses token-budgeted blocks.

**V2 action:** keep these principles:
- persisted canonical goal/subgoal;
- bounded recent window;
- stable section ordering;
- full history stored but not copied into prompt;
- deterministic prompt/context rendering.

Do **not** initially port the whole task-memory/FTS/compaction stack. Start smaller and add retrieval only when long tasks require it.

### deterministic verification principles from `agent/verifier.py`

Good existing behavior:
- verify typed value;
- verify select value;
- URL/title/content postconditions;
- execution error becomes failed verification;
- the model does not self-grade success.

**V2 action:** preserve the verifier boundary but redesign result type to support:

```text
SATISFIED
NOT_SATISFIED
AMBIGUOUS
```

A single boolean is insufficient for state-changing ambiguity.

### local-model backend abstraction

The README confirms Ollama and llama.cpp were already hidden behind an inference-client abstraction, with structured output approaches for each.

**V2 action:** keep the adapter concept, but V2 begins with one supported path (likely Ollama/Qwen3) until action-selection evaluation is stable.

### startup/health-check concepts

The old CLI verifies that Ollama/model/browser/CDP actually respond rather than reporting success because a process was launched.

**V2 action:** retain health checks as deterministic startup diagnostics, but keep them outside the agent controller.

---

# KEEP TEST ASSETS BEFORE KEEPING IMPLEMENTATION

The old repo has substantial:

```text
tests/unit/
tests/integration/
tests/model/
tests/fixtures/
benchmarks/general_agent/fixtures/
```

The benchmark tree already includes fixtures such as:
- cross-site dependency;
- dynamic DOM churn;
- failure/replan scenarios;
- crash/recovery probes.

These are high-value because V2 can run the same failure cases against a new kernel and prove that the rewrite actually improves behavior.

**Migration rule:** copy/adapt a fixture only after identifying the invariant it tests. Do not copy old controller assumptions into the expected output.

---

# ADAPT CAREFULLY

## `browser/playwright_backend.py`

### Good ideas
- only one module touches live `Page`;
- `fill()` rather than naive key-by-key typing;
- persistent launch mode;
- explicit URL matching;
- browser-native download event;
- no long-lived element handles across calls.

### Problems / risks

1. **Selector-hint re-resolution**
   - V2 should prefer snapshot/observation-scoped semantic refs when using MCP, or a robust semantic locator abstraction with direct Playwright.
   - Cached CSS + `nth` can silently retarget after DOM churn.

2. **CDP attachment as everyday default path**
   - Playwright documentation states `connect_over_cdp()` is significantly lower fidelity than the native Playwright protocol and can lose functionality when Chromium was launched differently.
   - V2 should default to a dedicated Playwright-managed persistent profile.

3. **Page-selection heuristic**
   - comments show repeated fixes around preferred tab URL, explicit target URL, and most-recent-page heuristics.
   - this is evidence that tab ownership/page selection must be an explicit registry, not inferred inside browser startup.

4. **Tab ownership bug history**
   - prior testing found an agent-created tab could be created before adoption/ownership classification, then incorrectly become `user` owned.
   - V2 assigns ownership at the exact creation event.

**V2 action:** do not copy the backend wholesale. Reuse tests and a few helper ideas after the BrowserKernel spike decides MCP vs direct Playwright.

## `agent/security_policy.py`

Good direction:
- deterministic policy outside model;
- domain permissions;
- sensitive-fact heuristics;
- separate risk classification.

V2 changes:
- make policy decisions typed and centralized;
- track origin/provenance of sensitive facts;
- explicit cross-origin data-transfer policy;
- confirmation boundary for consequential operations;
- add prompt-injection threat tests.

Keep the principle, not necessarily the exact keyword heuristics.

---

# REWRITE

## `agent/controller.py`

At ~104 KB, this is the clearest rewrite candidate.

V2 controller must be small enough that its entire transition system can be reasoned about as a state machine. It should orchestrate interfaces, not contain browser/site/resource-specific behavior.

Target responsibilities only:

```text
load state
observe
build context
request Decision
validate/policy-check
persist intent
execute
verify/reconcile
persist result
transition state
```

Everything else belongs behind a component boundary.

## `agent/loop.py`

At ~69 KB, it duplicates/overlaps controller-level orchestration and recovery concerns.

**V2:** there should be one authoritative controller loop. Browser execution is a method call, not a second autonomous loop.

## large semantic planner/resource resolver stack

The old README describes a semantic planner + deterministic resource resolver that resolves open tabs and safe matches. This was built in response to real needs, but it also increases hidden task-specific behavior.

**V2:** first prove general navigation/grounding. Then add a small `ResourceResolver` only for explicit cases such as:
- user says "this page";
- user names an already-open tab/resource;
- user supplies a URL;
- external connector returns a canonical resource.

Do not make resource resolution a substitute for browser reasoning.

## `memory/task_memory.py` as a whole

The existing task memory is sophisticated: summaries, retrieval queries, FTS records, active facts, compaction.

That sophistication may be useful later, but it should not be a day-one dependency.

**V2 stages:**
1. event trace + current task state;
2. explicit facts with provenance;
3. FTS retrieval only when fact volume exceeds bounded direct selection;
4. summaries/compaction only after metrics show need;
5. embeddings/vector DB only if FTS fails measured retrieval tasks.

---

# DO NOT PORT YET

- batch orchestration;
- multi-agent/delegation features;
- complex workspace abstractions;
- automatic skill learning;
- site-specific task classes;
- recovery ladders that do not correspond to a typed failure;
- model-controlled generic refresh;
- existing-browser daily-driver attachment as primary architecture;
- any subsystem whose only justification is "the old repo already has it."

---

# Specific old failure lessons to encode into V2

## 1. Tab ownership must be established at creation time

Do not run a later "adopt existing tabs" pass that can launder an agent-created tab into user ownership.

Required fields:

```text
page_id
browser_context_id
opener_page_id
created_by: USER | AGENT | EXTERNAL | UNKNOWN
created_at_event_id
current_url
closed
```

Only `AGENT` pages are auto-closeable.

## 2. Browser startup cannot silently choose an unrelated stale tab

If a task has an explicit URL/resource, page selection must be exact or a new agent page is created. "Most recently active" heuristics are allowed only when the user's goal explicitly targets the current page.

## 3. Fix the primitive, not the planner

The old project repeatedly accumulated planner/recovery changes around browser symptoms. V2 requires each browser primitive to pass repeated fixture tests before model integration.

## 4. Keep deterministic verification, but increase semantic strength

Old `CLICK` default verification uses state-hash/URL change. This catches no-ops but can still mark irrelevant state changes as success.

V2 requires action-specific and subgoal-specific postconditions where possible.

## 5. Preserve event sourcing, simplify memory

The append-only event store is worth keeping. The full higher-level memory stack should be rebuilt incrementally from requirements.

---

# Migration sequence

1. **Do not import old `agent/controller.py` or `agent/loop.py`.**
2. Create V2 interfaces/state schemas independently.
3. Port/adapt old controlled fixtures into V2 tests.
4. Run BrowserKernel candidate against old fixture cases.
5. Port small deterministic utilities only when the V2 test requires them.
6. Reuse event-store concepts and loop detectors early.
7. Reuse memory retrieval only after long-research tests fail without it.
8. Keep old repo intact as a reference until V2 regression coverage is stronger.

## Reuse verdict summary

| Area | Verdict |
|---|---|
| SQLite append-only event log | KEEP/ADAPT |
| deterministic loop detectors | KEEP/ADAPT |
| deterministic verification boundary | KEEP/ADAPT |
| bounded deterministic context building | KEEP PRINCIPLE |
| local model adapter | KEEP PRINCIPLE |
| test fixtures / benchmarks | HIGH-PRIORITY REUSE |
| Playwright backend | REWRITE BEHIND NEW KERNEL; salvage helpers/tests |
| tab/page-selection logic | REWRITE |
| controller | REWRITE |
| loop | REWRITE |
| sophisticated task memory | DEFER / REBUILD IN STAGES |
| batch/multi-agent orchestration | DO NOT PORT YET |
| security policy | ADAPT PRINCIPLE, EXPAND THREAT MODEL |

## Final audit conclusion

The old project was not wasted work. It proved several important pieces and, more importantly, exposed failure classes that V2 can now design around. The best use of the old repo is **to reuse its tests, state/event ideas, and small deterministic utilities while refusing to inherit its orchestration complexity.**
