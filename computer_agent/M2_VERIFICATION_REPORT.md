# M2 — Independent Verification: Report

**Date:** 2026-09-18 · **Milestone:** `docs/IMPLEMENTATION_PLAN.md` M2 · **Gate:** `docs/BUILD_SPEC.md` "Gate M2" · **Verdict: PASS**

Synthetic evidence only (pure-Python Fixture B). It proves the verification *contract* resists a lying executor. It does not prove any real adapter's observation channel is independent or trustworthy; that is M7's job.

## 1. Contract (`computer_agent/verification.py`)

- **Evidence model.** The verifier sees only a `VerificationSpec` and observed state: plain JSON-like data captured by an observation channel that is separate from dispatch. An observer marks unreadable data with `Indeterminate` (the whole observation via `UNAVAILABLE`, or any subtree). A missing key means the value is determinately absent. An `Indeterminate` means "don't know", and it is never equal to anything, including itself.
- **Three-valued predicates (Kleene).** The primitives are `Eq`, `Ne`, `Exists`, `Absent`, `Contains`, `OneOf`, `InRange`, `Count`, `CountDelta`, `Delta`, `Transition`, `Unchanged` and `UnchangedExcept`, composed with `And`/`Or`. There is also `Check`, a bounded domain callback: it receives deep copies of the evidence, and it returns UNKNOWN if it raises or returns anything other than a bool. Any read that touches `Indeterminate` data returns UNKNOWN.
- **`VerificationSpec(success, invariants)`.** `success` holds the required sub-effects and `invariants` holds the prohibited-effect checks. An empty `success` tuple is refused, because it would verify vacuously.
- **Outcome precedence (`evaluate`).**
  1. Any invariant FALSE → `UNEXPECTED_SIDE_EFFECT`.
  2. Otherwise any UNKNOWN → `INCONCLUSIVE`.
  3. Otherwise all success predicates TRUE → `VERIFIED_SUCCESS`.
  4. None TRUE → `VERIFIED_FAILURE`.
  5. Some TRUE → `PARTIAL_SUCCESS`.

  `INCONCLUSIVE` is never folded into success or failure.
- **Confirmation (`judge`).** Success requires two consecutive observations that both evaluate to success and have identical observed state. A success seen once is `INCONCLUSIVE`. A success that is then contradicted takes the later verdict. A side effect ends judgement immediately.
- **Polling (`verify`).** Up to `max_observations` observations are taken, so a delayed effect can land without anything being re-executed. `verify` returns the observations it used, so `judge()` can re-derive the identical verdict from persisted evidence (M3 relies on this).
- **Independence is structural.** `verify`/`judge`/`evaluate` have no parameter through which an executor claim could arrive. The module imports only the stdlib, and it contains no `claim`/`executor` identifiers. `test_verifier_has_no_channel_for_executor_claims` enforces this with an AST check.

## 2. Fixture B (`tests/computer_agent/fixtures/fixture_b.py`)

`DeceptiveService` holds the true records and outbox. It has:
- a lying executor;
- an independent `observe()` that advances a logical clock, so scheduled delayed, reverting and drifting changes land *between* observations;
- a ground-truth `truth_at_tick` record that only the oracle reads.

Four action kinds, each with a production-shaped declared spec:
- `update_fields`, a state-set;
- `increment`, a non-idempotent numeric change;
- `create_record`;
- `send_message`.

12 behavior classes:

| Class | What the executor really does |
|---|---|
| `correct` | the right effect, and claims success |
| `noop_claims_success` | nothing, and claims success |
| `wrong_object` | mutates a different record, key or recipient |
| `partial` | applies one of two fields, or sends a truncated body |
| `delayed` | the effect lands 2 to 5 ticks later, sometimes after the polling window |
| `duplicate` | applies twice (idempotent for `update_fields`, harmful for the other kinds) |
| `collateral` | the right effect plus a prohibited change to another record or the outbox |
| `unavailable` | the after-observation is fully unavailable, the target subtree is masked, the channel is intermittent, or the *before* observation is unavailable |
| `claims_failure_but_applied` | the effect is applied, but the executor reports a timeout |
| `ambiguous_result` | the target is reported by conflicting sources (`Indeterminate`), whether or not the effect happened |
| `precondition_satisfied` | the desired state was already true, so the executor does nothing |
| `state_changes_between_observations` | a transient revert, unrelated drift, or a revert after the window |

That makes 44 (behavior × kind) cases. Four combinations are meaningless and are excluded rather than faked, for example `partial` for a single-effect increment.

## 3. Campaign design (`tests/computer_agent/m2_campaign.py`)

- **Trial order** mirrors production:
  1. an independent pre-dispatch observation;
  2. the (possibly lying) executor runs;
  3. `verify` polls the observation channel.

  The claim is recorded for reporting and is never passed to the verifier.
- **Independent oracle.** `_oracle_expected` is a separately written reference implementation of each intent. It is applied to the *unmasked* true pre-dispatch state.
  - `VERIFIED_SUCCESS` counts as a **false success** unless the true state at the verifier's final observation equals that expected state exactly: the effect is present, applied once, and nothing else changed.
  - A **false failure** is `VERIFIED_FAILURE` when the effect was truly established.
- **Seeding.** Seeds are assigned round-robin over the 44 cases, with `seed = base_seed + i`. The evidence is `computer_agent/results/m2_campaign-seed0-n2200{.jsonl,-summary.json}`, which is gitignored and reproducible with `python -m tests.computer_agent.m2_campaign`.

## 4. Results

| Run | Trials | False success | False failure | Success | Failure | Inconclusive | Partial | Side effect |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Permanent gate (`test_m2_gate.py`, seed 0) | 2,200 | **0** | 0 | 783 | 283 | 399 | 100 | 635 |
| Sweep over 6 more seed ranges (7, 1e6, 5e6, 987654321, 123456789, 2^31) | 13,200 | **0** | 0 | 4,705 | 1,715 | 2,380 | 600 | 3,800 |

In the gate run, the executor's claim disagreed with the truth in 1,406 trials, and every one of those lies was caught. The effect was truly established in 1,037 trials. 783 of those were `VERIFIED_SUCCESS`. The other 254 are the price of conservatism, and none of them are false failures:
- delayed effects that were seen but unconfirmed at the end of the window;
- confirmations broken by unavailable or masked evidence.

Per-behavior verdicts match their design. For example, `wrong_object` and `collateral` are always `UNEXPECTED_SIDE_EFFECT`, `ambiguous_result` is always `INCONCLUSIVE`, and `claims_failure_but_applied` and `precondition_satisfied` are always `VERIFIED_SUCCESS`. The full table is in the summary JSON.

**The gate can fail.** `test_oracle_detects_invariant_free_specs` and `test_oracle_detects_claim_trusting_verifier` deliberately sabotage verification: they strip the invariants, or trust the executor's claim. The same oracle then reports false successes, so a result of 0 is meaningful.

## 5. Defects found

No false success was ever observed. Two **spec-level misclassifications** were found in the first 2,200-trial run and fixed in Fixture B's declared specs. The verifier itself did not change. Neither was a false success, but both would have invited an unsafe retry in M3:

1. `wrong_object:send_message`, a message to the wrong recipient, was classified `PARTIAL_SUCCESS`. Because "every *new* message equals the intended one" is not expressible with the primitives, a bounded `Check` callback now enforces it, and the case is now `UNEXPECTED_SIDE_EFFECT`.
2. `duplicate:increment` (+2n) was classified `VERIFIED_FAILURE`, which a naive controller would "retry" into +3n. An upper-bound invariant `Delta(0..n)` now makes it `UNEXPECTED_SIDE_EFFECT`.

Lesson: a VerificationSpec must guard *over-application* as well as under-application. Otherwise failure-driven retry policies can amplify side effects.

## 6. Limitations

- The predicate-coverage ≥90% criterion in BUILD_SPEC (design-level INCONCLUSIVE) was not measured against real BrowserAgentV2 task postconditions. The vocabulary expressed all four fixture action kinds with a single callback.
- The oracle's "truth" is the true state *at the verifier's last observation*. A revert that happens after verification completes is outside what any verifier can see, and is not graded as a false success.
- The confirmation rule compares whole observed states. Any `Indeterminate` anywhere prevents confirmation, even outside the predicates' paths. This is conservative, and costs some success outcomes as `INCONCLUSIVE`.
- Polling pace is the observer's job; there are no wall-clock sleeps in the fixture.

## 7. Ready to freeze?

Yes, for the M2 scope. Freeze the `verification.py` public contract: the predicates, `VerificationSpec`, `evaluate`/`judge`/`verify`, and the outcome vocabulary.
