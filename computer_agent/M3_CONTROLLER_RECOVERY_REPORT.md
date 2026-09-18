# M3 — Durable Controller / Journal / Crash Recovery: Report

**Date:** 2026-09-18 · **Milestone:** `docs/IMPLEMENTATION_PLAN.md` M3 · **Gate:** `docs/BUILD_SPEC.md` "Gate M3" · **Verdict: PASS**

Synthetic evidence only (Fixture C). It proves the lifecycle and recovery contract against a crashable fake world, including real `SIGKILL` of the controller process. It does **not** prove power-loss or filesystem durability, and it does not show that a real app's effects fit their declared class.

## 1. Modules

- **`journal.py`**
  - SQLite with `journal_mode=WAL` and `synchronous=FULL`, and a `meta.schema_version` (1). A mismatched version is refused with `SchemaVersionError`.
  - An append-only `events` table with a UNIQUE deterministic `event_id`. Recording the same lifecycle event twice (for example a second DISPATCH_STARTED for the same dispatch number) raises `DuplicateEvent`.
  - Every append is its own committed transaction.
  - Payloads are compact JSON: the semantic TargetSpec, args, observed state and verdicts. `Indeterminate` round-trips.
  - **No** live `ExecutionRef` and no model state is ever persisted.
- **`state.py`** — `replay(events) -> TaskState`, a pure deterministic fold with an explicit phase transition table. It refuses to materialize corrupted or out-of-order lifecycles, raising `JournalIntegrityError`. Refused examples: a dispatch without an intent, a commit without `VERIFIED_SUCCESS`, `STEP_COMPLETED` without a committed verified action, a second live intent for a step, a skipped dispatch number, and events before `TASK_CREATED`.
- **`recovery.py`** — a pure decision table: `after_verification(class, outcome, dispatches)` and `on_restart(action)`.
- **`controller.py`** — the single owner of the lifecycle. It calls `crash(boundary)` fault-injection hooks and uses M1 `resolve`/`freshness_check` and M2 `verify`/`judge` unchanged.
- **`types.py`** — one additive enum, `EffectClass` (A–D). M1 types are unchanged.

## 2. Action lifecycle (as in BUILD_SPEC / IMPLEMENTATION_PLAN)

```
replay journal -> OBSERVED -> resolve TargetSpec -> TARGET_RESOLVED | TARGET_REJECTED(+STEP_BLOCKED)
 -> policy placeholder (granted kinds; M5 owns real policy) -> POLICY_ALLOWED | POLICY_BLOCKED
 -> ACTION_INTENT_PERSISTED (stable action_id = <step>.a<n>)
 -> fresh observation + freshness_check -> FRESHNESS_PASSED | FRESHNESS_FAILED(+ACTION_ABANDONED, STEP_BLOCKED)
 -> DISPATCH_STARTED {dispatch n, independently observed before-state}
 -> dispatch (only site; only with the freshness-approved ref)
 -> DISPATCH_RETURNED {executor claim - audit only}
 -> verify (poll independent channel) -> OBSERVED_AFTER {observations} -> VERIFICATION_RECORDED {outcome}
 -> ACTION_COMMITTED -> STEP_COMPLETED  (only on VERIFIED_SUCCESS)
    | ACTION_FAILED{retry} -> next dispatch of the same action_id  | [OUTCOME_UNKNOWN] -> NEEDS_REVIEW
```

`run()` always rebuilds state from the journal first. On a restart it records `RECOVERY_STARTED` and `STATE_RECONSTRUCTED`, then reconciles the in-flight action before advancing. It halts at the first step that is BLOCKED or NEEDS_REVIEW and never skips ahead.

## 3. Recovery classes and decisions

Classes: **A** idempotency-key, **B** externally queryable, **C** naturally idempotent state-set, **D** non-idempotent and non-queryable.

| Durable phase at restart | Decision |
|---|---|
| no intent / `INTENT_PERSISTED` / `RETRY_PENDING` | provably not dispatched (DISPATCH_STARTED precedes dispatch), so re-ground from the persisted TargetSpec and dispatch, for any class |
| `DISPATCH_STARTED` / `DISPATCH_RETURNED` | **A/B/C:** reconcile by observing and verifying now. If present → `OUTCOME_RECONCILED` and commit; otherwise settle (below). **D:** `OUTCOME_UNKNOWN` → `NEEDS_REVIEW`, **never re-dispatched** |
| `OBSERVED_AFTER` | re-`judge` the *persisted* observations; never re-act |
| `VERIFIED` | settle from the persisted verdict |
| `COMMITTED` without step completion | complete the step |

**Settling a verdict** (`after_verification`):
- **Success** → commit.
- **Partial or side effect** → `NEEDS_REVIEW`.
- **Failure** → A/B/C retry, D goes to review.
- **Inconclusive** → A retries (same key), C retries (idempotent), and B and D go to `OUTCOME_UNKNOWN` → review.
- **Budget:** `MAX_DISPATCHES = 2` per logical action. Retries reuse the same `action_id`, which is the class-A idempotency key.

## 4. Fixture C (`tests/computer_agent/fixtures/fixture_c.py`)

- **The world** is a JSON file written atomically (temp file, fsync, `os.replace`), so it survives controller death. A `WorldClient` is one controller session. Its UI handles are session-local, and a restart gets a new session.
- **Effect classes.** There is one button per class:
  - A `place_order` dedups on `action_id`;
  - B `record_payment` appends with an `action_id` reference;
  - C `set_theme`;
  - D `send_notification`, whose only evidence is a toast visible to the dispatching session.
- **Executor faults:** honest, `lie_noop`, `fail_but_applied`, `collateral`, and `blind_after_dispatch` (the evidence channel goes dark after the effect).
- **UI mutations**, injected at the freshness observation, for the combined M1 scenarios.
- **The hidden `_truth` ledger** records effects and dispatch calls per `action_id`, repeats after an effect was already applied, and stale or wrong-target dispatches.

**Crash boundaries (12):**
1. `before_intent_persist`
2. `after_intent_persist`
3. `after_freshness_before_dispatch_started`
4. `after_dispatch_started`
5. `during_dispatch_before_effect`
6. `after_effect_before_return`
7. `after_dispatch_returned` (the effect happened but was not yet observed)
8. `after_observation_before_persist`
9. `after_observation_persisted`
10. `after_verification_persisted`
11. `after_commit_before_step_complete`
12. `after_step_complete` (after durable success)

## 5. Campaign design (`tests/computer_agent/m3_campaign.py`)

- **Trial shape.** Each trial is a 2-step task. Step 1 has the class under test; step 2 has a different class, which checks that the plan resumes and completed work is not re-dispatched.
- **Crash injection.** The controller is killed at the first hit of the boundary, which is always inside step 1 on the success path. It is then restarted as a new journal connection plus a new world session, up to 4 runs. In 25% of trials a second crash is injected at a random boundary *during recovery*.
- **Fault mix:** 60% honest, 15% lie_noop, 15% fail_but_applied, 10% blind_after_dispatch.
- **Oracle.** It reads the world's `_truth` ledger and the journal's **raw SQLite rows** with its own SQL. It never calls `state`, `recovery` or `verification`. It checks:
  - duplicate effects (more than one real effect for A/B/D);
  - lost effects (an effect happened but the step is neither completed nor under review);
  - incorrect `VERIFIED_SUCCESS`;
  - unsafe retries (any second class-D dispatch, or any class-B repeat after the effect was applied);
  - completion without a verified success;
  - dispatch calls exceeding the durable `DISPATCH_STARTED` count;
  - stale or wrong-target dispatches;
  - `action_id` instability;
  - a task ending neither completed nor explicitly halted;
  - two independent replays disagreeing, or disagreeing with the oracle's step status.
- **Real process death.** In `--subprocess` mode every controller lifetime is a separate OS process, killed with `os.kill(getpid(), SIGKILL)` at the boundary.

## 6. Results

| Run | Trials | First crash fired | 2nd crash | Duplicates | Lost | Incorrect VERIFIED_SUCCESS | Unsafe retries | Unverified advance | Reconstruction failures | Reconciled | OUTCOME_UNKNOWN | NEEDS_REVIEW |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| In-process gate (`test_m3_gate.py`), 1,044/class | 4,176 | 4,112 | 894 | **0** | **0** | **0** | **0** | **0** | **0** | 1,112 | 586 | 668 |
| Real SIGKILL, 60/class (`--subprocess`) | 240 | 236 | 45 | **0** | **0** | **0** | **0** | **0** | **0** | 60 | 35 | 39 |
| Real SIGKILL permanent test (every class × boundary) | 48 | 48 | — | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — |

Other counters from the gate run were all 0: stale or wrong-target dispatches, dispatch without a durable start, and `action_id` instability. It recorded 43 **safe** same-key class-A retries, where the service deduplicated, and 34 idempotent class-C re-applies. The 48-trial SIGKILL test also asserts that each class × boundary produces the same authoritative outcome in-process and under SIGKILL.

**Task outcomes by class (in-process gate):**

| Class | COMPLETED | NEEDS_REVIEW |
|---|---:|---:|
| A | 1,021 | 23 |
| B | 982 | 62 |
| C | 1,013 | 31 |
| D | 492 | 552 |

Class D's reviews are the designed `OUTCOME_UNKNOWN` outcomes.

**Crashes that didn't fire.** The 64 in-process trials whose first crash did not fire are runs that correctly halted before reaching that boundary, for example class D with `lie_noop` going to review before commit. They are still graded, and all of them are safe.

**The gate can fail.** `test_oracle_detects_blind_class_d_retry` swaps in a naive "reconcile then retry" policy for class D, and the oracle reports duplicates and unsafe retries.

## 7. SQLite durability tests (`test_journal_replay.py`)

These cover:
- WAL mode and synchronous=FULL are active;
- a second connection reconstructs committed events without any checkpoint;
- duplicate-event rejection leaves nothing behind;
- schema-version refusal;
- deterministic replay, with `Indeterminate` round-tripping;
- 7 corrupted-lifecycle refusals.

They do **not** cover power loss or filesystem-level durability. `synchronous=FULL` is configured but unproven here.

## 8. Defects found

- **A harness defect.** It was found by the new `blind_after_dispatch` fault, which was added because the first run never exercised class-A key reuse. The oracle compared two independent replays with `==`. Persisted `Indeterminate` evidence is, by design, never equal to anything, so 74 identical replays were reported as mismatches. The fix compares canonical form (`repr`), in `grade()`. It is not a controller defect: the replays were identical.
- **A coverage gap, now closed.** The first 4,176-trial run had `safe_key_retries = 0`, because the idempotency key was never actually needed. The `blind_after_dispatch` fault now drives INCONCLUSIVE → same-key retry → service dedup (43 cases in the gate run).
- **Production defects: none.** No duplicate, unsafe retry, incorrect success or unverified advance was ever observed, so `REGRESSION_SEEDS` in `test_m3_gate.py` is empty.

## 9. Limitations

- **"Definitely did not happen" relies on the class-B query being read-after-write consistent.** A delayed class-B effect could be duplicated by a retry after `VERIFIED_FAILURE`. Real adapters must justify class B per action.
- **Conservative class-D reviews.** A crash between DISPATCH_STARTED and the actual dispatch makes class D go to review even though nothing happened. The journal cannot distinguish the two cases, so the review is the conservative choice, and the cost is extra human review.
- **The policy gate is a placeholder** (a granted action-kind allowlist). M5 owns real policy.
- **No checkpoints.** State is a full replay each time, which is fine at this scale. M4 owns bounded projection and long-horizon checkpoints.
- **One logical action per step.** An ABANDONED action blocks the step rather than minting a new `action_id`. Replanning is out of scope.
- **The before-state snapshot is stored inline in the journal.** Large real observations will need artifact references (see `OBSERVABILITY.md`).

## 10. Ready to freeze?

Yes, for the M3 scope. Freeze the event vocabulary, the transition table, the recovery decision table and the `WorldPort` shape. Changing any of them should re-run this gate.
