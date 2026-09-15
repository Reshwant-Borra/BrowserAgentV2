# Old BrowserAgent Failure Regression Matrix

**Purpose:** convert known pain points and old-repository patches into permanent V2 invariants. The previous project is useful evidence only if the new architecture can prove it will not regress the same failures.

## Evidence from the old repository

The old code already contains tests and comments showing repeated work around:

- choosing the correct existing/open tab;
- preventing new tasks from attaching to an unrelated stale tab;
- preserving a resumed task's own page identity;
- search/type/select browser primitives;
- inference retry without duplicated action intent;
- verification/recovery;
- crash recovery;
- long-horizon state;
- domain/security policy.

Relevant old tests include:

```text
tests/unit/test_agent_loop_tab_wiring.py
tests/integration/test_cdp_attach.py
tests/integration/test_phase1_browser_actions.py
tests/integration/test_phase1b_contract_repair.py
tests/integration/test_phase2_verification_recovery.py
tests/integration/test_phase3_crash_recovery.py
tests/integration/test_phase4_long_horizon.py
tests/integration/test_domain_permission.py
```

V2 should adapt the invariants, not copy the old orchestration.

---

# Regression R1 — Agent opens/uses the wrong tab

## Old evidence

`test_agent_loop_tab_wiring.py` exists specifically because open-tab work items needed to propagate an exact `preferred_tab_url`, and explicit URL tasks needed an `explicit_target_url` so CDP attach would not select whatever unrelated tab was most recently active.

## V2 invariant

Task-to-page selection is never based on a hidden "last tab" heuristic when the task has an explicit target/resource.

### Required tests

1. user has tabs A/B/C open; task explicitly requests B -> agent acts only on B;
2. explicit URL not already open -> create AGENT tab, do not hijack A/B/C;
3. current-page task -> may use explicitly current user page;
4. resume task -> page identity rediscovered from persisted task/page registry;
5. sibling/concurrent workflow cannot change another task's active page binding.

### Pass rule

0 wrong-tab actions across repeated stress run.

---

# Regression R2 — Agent-created tab is mistaken for a user tab

## Failure mechanism to prevent

If a backend creates a target tab before a later "adopt existing tabs" pass, ownership can be incorrectly assigned as USER and cleanup then leaks the tab.

## V2 invariant

Page ownership is created atomically with the page event.

```text
AGENT creation -> owner=AGENT immediately
pre-existing discovery -> owner=USER/UNKNOWN immediately
popup inherits explicit creation metadata/opener
```

There is no generic later ownership-adoption pass that can overwrite provenance.

### Required tests

- agent creates tab -> AGENT;
- user tab present before agent start -> USER;
- user manually creates tab during handoff -> USER/UNKNOWN;
- agent popup -> AGENT with opener;
- cleanup closes only AGENT tabs.

---

# Regression R3 — Typing succeeds at API level but text is missing/wrong

## Old evidence

The old backend uses `locator.fill(text)`, and `test_phase1_browser_actions.py` covers a search fill flow. User testing nevertheless exposed typing/search fragility on real pages, so simple static-fixture success is insufficient.

## V2 invariant

A TYPE action succeeds only after a fresh observation proves the intended field value.

### Required fixtures

- normal `<input>`;
- textarea;
- contenteditable;
- controlled React input;
- delayed hydration replaces input;
- input formatter changes value;
- autocomplete steals focus;
- Enter-to-submit;
- keydown-dependent field where `fill()` is insufficient.

### Kernel policy

1. try standard deterministic fill/type method;
2. verify exact/normalized value;
3. if fixture-class evidence indicates keyboard-event requirement, use one bounded sequential-key fallback;
4. reverify;
5. otherwise emit `INPUT_VALUE_MISMATCH`.

The planner does not invent typing workarounds.

---

# Regression R4 — Search fails because typing and submission are conflated

## V2 invariant

Search is composition, not a special architecture:

```text
find search field
-> TYPE verified query
-> CLICK submit / PRESS Enter according to current page
-> verify results/navigation
```

A failure at each stage is separately visible.

### Tests

- button submit;
- Enter submit;
- live-search without submit;
- result opens same tab;
- result opens popup/new tab;
- autocomplete result selection.

Do not add a generic "search website" hard-coded workflow.

---

# Regression R5 — Unnecessary refresh/reload destroys state

## V2 invariant

`REFRESH` is absent from the model's normal action schema.

No recovery policy may default to reload for:
- stale target;
- missing element;
- typing mismatch;
- timeout;
- planner confusion;
- no-op click.

Instead:

```text
stale -> reobserve/redecide
input mismatch -> bounded kernel fallback or redecide
no-op -> reobserve/replan
transient read error -> bounded retry
ambiguous state-changing result -> reconcile
```

### Regression fixture

Create page with unsaved form state. Trigger a recoverable stale/no-op condition. Assert the controller never calls reload and the typed state remains intact.

---

# Regression R6 — Inference retry duplicates browser intent

## Old evidence

`test_phase1_browser_actions.py::test_inference_retry_does_not_duplicate_action_intent` verifies that a model request retry still creates one action intent.

## V2 invariant

Model transport retry happens **before** a validated Decision is committed as action intent.

```text
model request attempts N times
-> one validated Decision
-> at most one ACTION_INTENT
```

### Test

Force model timeout then successful identical response; assert one intent and one browser execution.

---

# Regression R7 — Browser action retries duplicate remote side effect

## V2 invariant

Once `ACTION_INTENT_PREPARED` is persisted for a state-changing action, any uncertain interruption is reconciled before replay.

### Required crash matrix

- crash before call -> safe to determine no action executed;
- crash during call -> ambiguous;
- remote state changes then crash -> reconciliation must discover success;
- result arrives then process crashes -> replay event log/current remote state;
- verification crashes -> inspect state, do not submit again.

0 duplicate server-side operations is a hard gate.

---

# Regression R8 — Irrelevant page change is mistaken for successful click

## Old evidence

The old default click verifier considers any state-hash or URL change meaningful. That detects no-ops but can false-positive on spinners, ads, counters, clocks, or unrelated DOM churn.

## V2 invariant

A state-changing click should have a more specific expected postcondition when advancing a subgoal.

Fallback "some page changed" may prove only that the click was received, not that the subgoal succeeded.

### Tests

- click desired button + unrelated animation only -> NOT_SATISFIED;
- click causes correct target element -> SATISFIED;
- click triggers unclear server transition -> AMBIGUOUS.

---

# Regression R9 — Recovery ladder keeps working around the wrong layer

## V2 invariant

Every failure includes:

```text
failure_type
owner_component
retry_safety
recommended_transition
```

Examples:

```text
TARGET_STALE -> BrowserKernel/Controller -> reobserve
MODEL_TARGET_INVALID -> ModelAdapter/Controller -> bounded redecision
INPUT_VALUE_MISMATCH -> BrowserKernel -> bounded deterministic fallback
POSTCONDITION_FAILED -> Verifier/Controller -> redecide/replan
SIDE_EFFECT_AMBIGUOUS -> Controller -> reconcile
```

A generic `recovery_level++` that changes multiple behaviors is not sufficient evidence-based recovery.

---

# Regression R10 — Full browser/task history overloads Qwen

## Old evidence

The old project evolved context summaries, active facts, retrieval and token budgets because long histories became a concern.

## V2 invariant

The first implementation starts with:
- canonical task/plan;
- relevant explicit facts;
- one recent verified transition;
- bounded current observation.

Trace history stays in SQLite.

### Test

Run a 50-step scripted task and assert context token count remains within configured bound and does not grow linearly with event count.

---

# Regression R11 — Resume reconstructs task but not browser reality

## V2 invariant

Persisted state does not make browser targets valid after restart.

Resume sequence:

```text
rebuild task state
-> start/reconnect browser
-> rediscover page registry
-> invalidate all previous refs
-> reconcile pending intent if any
-> fresh observation
-> continue active subgoal
```

### Test

Change browser page manually while controller is down; resume must use actual browser state, not stale persisted element IDs.

---

# Regression R12 — "Generality" becomes hard-coded example support

## V2 invariant

Any new fix must answer:

> Which general failure class does this solve?

If the answer is only "this makes Canvas / Google / Amazon work," reject or reformulate it as a general primitive.

Allowed examples:
- iframe support;
- controlled-input support;
- virtualized-list observation;
- popup handling;
- authentication handoff.

Disallowed pattern:
- `if domain == canvas...` in controller/planner.

Connectors are different: a connector is an explicit structured capability, not a hidden site special-case inside browser reasoning.

---

# Migration priority from old tests

Adapt in this order:

1. simple browser actions/search/select/download;
2. element/observation mapping;
3. tab/CDP/page identity cases;
4. verifier/recovery cases;
5. crash recovery;
6. loop detection;
7. domain/security policy;
8. long-horizon bounded context;
9. only later general-controller/batch/workspace cases that still match V2 requirements.

## Rule

Old test code is not automatically correct. Preserve the **behavioral invariant**, rewrite the test around V2 contracts, and remove assumptions tied to old controller classes.
