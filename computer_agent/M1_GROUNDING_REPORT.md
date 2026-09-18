# M1 — Grounding and Freshness: Report

**Date:** 2026-09-18 · **Milestone:** `docs/IMPLEMENTATION_PLAN.md` M1 · **Status:** implemented and falsified against the deterministic Fixture A gate in `docs/BUILD_SPEC.md` ("Gate M1").

This report covers only the M1 grounding/freshness contract on a synthetic, pure-Python fixture. **It does not prove anything about real GUI grounding** (Playwright, macOS AX, Windows UIA, or vision) — that evidence remains scoped to `phase0/` and to the later M7/M8 milestones.

## 1. What was implemented

Production package (`computer_agent/`) — exactly the M1 scope, nothing from later milestones:

- `computer_agent/types.py` — `ResolutionOutcome`, `DispatchSafety`, `ObservationVersion`, `TargetSpec`, `ExecutionRef`, `TargetCandidate`, `Observation`, `ResolutionResult`, `FreshnessResult`, plus the Developer Console observability schema (`CandidateSummary`, `GroundingTrace`).
- `computer_agent/grounding.py` — `resolve(spec, observation, *, expected_version=None)` and `freshness_check(ref, spec, fresh_observation)`.

No `TaskController`, journal, SQLite, verifier, recovery, policy engine, model integration, real adapter (Playwright/AX/UIA/vision), or InteractionRouter was added — all excluded per task scope, deferred to M2+.

Test/harness package (`tests/computer_agent/`) — Fixture A and the adversarial campaign, not production code:

- `fixtures/fixture_a.py` — `MutableUIGraph` (deterministic mutable UI graph with a hidden `true_id` per element, never exposed to `resolve`/`freshness_check`) and `DispatchAttempt` (the fake dispatch boundary).
- `fixtures/scenarios.py` — 21 named scenario builders + registry.
- `campaign.py` — `run_trial`/`run_campaign`, and an **independently written** ground-truth oracle (`_ground_truth`) that never calls `computer_agent.grounding.resolve` — deliberately avoiding the circularity of using the function under test to grade itself.
- `test_types.py`, `test_grounding_freshness.py`, `test_campaign_gate.py` — see §4.

## 2. Exact grounding contract implemented

```
TargetSpec (semantic intent only)
  -> Observation (fresh, from Fixture A's observe())
  -> resolve(spec, observation) -> ResolutionResult
       RESOLVED(selected candidate) | AMBIGUOUS | ABSENT | STALE | UNSUPPORTED
  -> [if RESOLVED] ExecutionRef (opaque, adapter-local, bound to this Observation's version)
  -> freshness_check(ref, spec, fresh_observation) -> FreshnessResult
       safe_to_dispatch=True with a (possibly re-resolved) ExecutionRef, or
       safe_to_dispatch=False (abstain) on any AMBIGUOUS/ABSENT/UNSUPPORTED re-resolution
  -> dispatch (Fixture A only, or abstain)
```

Key properties, matching `docs/DECISIONS.md` D-017/D-018:

- **No durable UniversalElement.** `TargetSpec` never stores a handle; `ExecutionRef` is only ever valid for the `ObservationVersion` it was produced against.
- **Ambiguity and absence abstain**, never guess. `ordinal` disambiguates only when the caller explicitly supplies it.
- **`freshness_check` never trusts a ref across a mutation.** It re-checks via `resolve(..., expected_version=ref.observation_version)`; on any mismatch it re-resolves from scratch against the fresh observation and uses the *new* ref, never the stale one. It only ever returns `safe_to_dispatch=True` when a full, singular `RESOLVED` outcome exists at the moment of the check.
- **Adapter contract this relies on** (documented in `grounding.py`'s docstring): `ObservationVersion` must change whenever anything happens that could make a previously-issued `ExecutionRef` unsafe. Fixture A satisfies this by construction; a real adapter (M7) must establish the same property independently — M1 does not and cannot prove that for a real system.

## 3. Fixture A scenarios (21)

Every scenario derives its `TargetSpec` from an element's *observable* attributes only; `true_id` never crosses that boundary. Each is run against 0-5 randomized decoy elements drawn from a vocabulary disjoint from every scenario's own role/name choices, so noise can never accidentally create an unintended collision.

| Scenario | Tests |
|---|---|
| `unique_target_no_mutation` | baseline: unique target, no mutation |
| `duplicate_labels_ambiguous_from_start` | ambiguity present before any mutation |
| `same_role_label_diff_container_disambiguated` | `container_hint` correctly disambiguates same role+label |
| `absent_target_from_start` | target never existed |
| `disabled_target_state_required` / `_not_required` | disabled element, with/without an `enabled` constraint |
| `hidden_target_state_required` / `_not_required` | hidden element, with/without a `visible` constraint |
| `target_removed_after_resolution` | target deleted between resolve and dispatch |
| `target_replaced_same_semantics_after_resolution` | new `true_id`, identical observable attributes (documented identity-is-semantic limitation, D-017) |
| `target_replaced_different_semantics_after_resolution` | new `true_id`, different name -> no longer matches |
| `controls_reordered_after_resolution` | pure reorder, no semantic change |
| `ordinal_disambiguation_then_reorder` | ordinal-based disambiguation stressed by reordering the tied candidates |
| `geometry_reflow_no_semantic_change` | bounds-only change; resolver must ignore coordinates |
| `overlay_inserted_colliding` | a new element that also matches the spec (real ambiguity injected) |
| `overlay_inserted_noncolliding` | a new unrelated element (must not cause false abstention) |
| `mutation_immediately_before_dispatch_disable` / `_hide` | state flips right before the freshness check |
| `unsupported_empty_spec` | a `TargetSpec` with no constraints at all |
| `duplicate_labels_introduced_by_mutation` | ambiguity introduced only after the initial resolve |
| `container_reassigned_after_resolution` | in-place container mutation (not a replace) against `container_hint` |

## 4. Tests added

- `tests/computer_agent/test_types.py` (8 tests) — `TargetSpec` semantics/immutability, `ExecutionRef` value equality and non-reuse across versions, `ResolutionResult` defaults, `GroundingTrace.build` assembly.
- `tests/computer_agent/test_grounding_freshness.py`:
  - 13 pure unit tests of `resolve`/`freshness_check` built directly on hand-constructed `Observation`s (unique match, container/state filtering, text-hint substring match, ambiguity with and without ordinal, out-of-range ordinal, absence, unsupported/empty spec, `expected_version` mismatch -> STALE, `expected_version` match, ephemeral-ref non-reuse, and all three `freshness_check` branches: unchanged/re-resolved/abstain).
  - 21 parametrized scenario sanity checks (one seed per named scenario, asserting the scenario reached its own intended T0 outcome, never produced a wrong/stale dispatch, and that the resolver agrees with the independent oracle).
  - The permanent regression corpus (`REGRESSION_SEEDS`) — see §5.
- `tests/computer_agent/test_campaign_gate.py` — the hard gate itself: 1,500 trials, asserted zero wrong/stale dispatch, zero T0-inconsistency, zero oracle disagreement, on every test run (no I/O, sub-second).

**126 tests pass, 0 fail, 1 skipped** (the empty-parametrize placeholder for `REGRESSION_SEEDS`) in the full repository suite (`pytest -q`, non-integration).

## 5. Bugs found during adversarial testing

- **One test-code bug**, not a production defect: an early version of `test_resolve_multiple_matches_without_discriminator_is_ambiguous` tried to put `TargetCandidate` objects in a `set()` for comparison; `TargetCandidate` carries a `dict` field (`states`) and is unhashable. Fixed by comparing as an ordered `list` instead (candidate order is already deterministic and meaningful). No `computer_agent/` code was touched to fix this.
- **Zero production defects found.** After the initial 1,500-trial gate passed cleanly on the first run, I deliberately looked for blind spots per task item 13 and found one real gap in scenario *coverage* (not a bug): no scenario exercised an **in-place container mutation** against `container_hint` (every existing scenario that changed identity did so via `replace_element`, which mints a new `true_id`, or via role/name change). I added `container_reassigned_after_resolution` (a new `MutableUIGraph.set_container` mutation + scenario) specifically to close that gap. It passed immediately with no implementation change required.
- I also specifically checked the "identity laundering" and "observation-version reuse" concerns named in task item 13:
  - `identity_shifted` diagnostic (dispatched `true_id` differs from the T0-selected one) fires in exactly the two scenarios where that is *architecturally correct*, and nowhere else: `target_replaced_same_semantics_after_resolution` (100% of trials — replacement is genuinely a new element, D-017 says semantic identity is all the contract promises) and `ordinal_disambiguation_then_reorder` (~40-45% of trials, depending on shuffle outcome — a documented consequence of ordinal being position-based, §7). All other 19 scenarios show 0% identity shift across every seed checked.
  - Reused-version / stale-handle risk: verified that `MutableUIGraph`'s handle history is keyed by `(observation_version, adapter_local_id)` and never cleared, so a freshness check that legitimately decides "nothing changed, reuse the original ref" is provably still resolving to the correct element — see the adapter-contract caveat in §7.

## 6. Campaign design

- **Independent oracle, not self-grading.** `campaign._ground_truth` is a second, separately written implementation of the same matching semantics, operating directly on Fixture A's hidden `true_id` ground truth — it never calls `computer_agent.grounding.resolve`. A bug in `resolve()` that happened to agree with itself could not silently pass grading.
- **Distribution.** Trials are assigned to the 21 scenarios by exact round-robin block assignment (`SCENARIO_NAMES[i % 21]`), not weighted random sampling — every scenario gets the same count (±1) for any campaign size, and any specific `(scenario, seed)` pair is exactly reproducible.
- **Determinism.** Every trial's randomness (decoy count/attributes, reorder shuffles) is derived from `random.Random(seed)`; `seed = base_seed + trial_index`.
- **Grading.** Zero-argument classification into `CORRECT_TARGET_DISPATCH` / `WRONG_TARGET_DISPATCH` / `STALE_TARGET_DISPATCH` / `ABSTAINED`, in that priority order (a stale-ref dispatch is reported as `STALE_TARGET_DISPATCH` even if it happened to also hit the "right" element by coincidence).

## 7. Campaign results

| Run | Trials | Wrong-target | Stale-target | T0-inconsistent | Oracle disagreement |
|---|---:|---:|---:|---:|---:|
| Permanent gate (`test_campaign_gate.py`, seed 0) | 1,500 | 0 | 0 | 0 | 0 |
| Manual adversarial sweep, 6 independent seed ranges (0, 7, 1e6, 5e6, ~1e9, 123456789) | 37,800 | 0 | 0 | 0 | 0 |
| **Total executed this session** | **~39,300** | **0** | **0** | **0** | **0** |

Outcome breakdown for the canonical 1,500-trial gate run (also written to `computer_agent/results/m1_campaign-seed0-n1500-summary.json`, gitignored):

- `CORRECT_TARGET_DISPATCH`: 643
- `ABSTAINED`: 857
- `WRONG_TARGET_DISPATCH`: **0**
- `STALE_TARGET_DISPATCH`: **0**

Per-scenario counts are exactly even (72 or 71 trials each, since 1500 / 21 is not integral) and match the scenario's designed outcome in 100% of trials — see the full breakdown reproducible via `run_campaign(n=1500, base_seed=0)`.

## H. Wrong-target dispatch count

**0**, across every run in this session (1,500-trial permanent gate + 37,800-trial manual sweep = ~39,300 trials).

## I. Stale-target dispatch count

**0**, across every run in this session.

## J. Abstention behavior

Abstention (`ABSTAINED`) occurred in exactly the 12 scenarios designed to require it (ambiguous-from-start, absent-from-start, disabled/hidden with a required state, removed-after-resolution, semantically-different replacement, newly introduced ambiguity via overlay or duplicate, state flipped immediately before dispatch, unsupported empty spec, container reassignment breaking a `container_hint` match) — 857/1,500 trials in the canonical run — and **never** in a scenario designed to have a safe, unambiguous target. No scenario showed unnecessary abstention (abstaining when the oracle said a safe unique target existed).

## 8. Exact gate verdict

Per `docs/BUILD_SPEC.md` "Gate M1" literally:

- ≥ 1,000 deterministic seeded trials: **satisfied** (1,500 in the permanent gate; ~39,300 total this session).
- Zero wrong-target dispatch: **satisfied**.
- Zero stale-target dispatch: **satisfied**.
- Correct abstention on ambiguous/absent/unsafe cases: **satisfied**.

**GATE M1: PASS.**

## 9. Limitations (do not overclaim)

- **Synthetic only.** This proves the abstract grounding/freshness contract against a fixture designed to exercise it. It says nothing about whether a real Playwright/AX/UIA adapter can produce an `Observation`/`ObservationVersion` with the properties `freshness_check` relies on (see the adapter-contract note in `grounding.py` and §5) — that is explicitly M7's job, not this milestone's.
- **Semantic identity is not durable identity, by design (D-017).** `target_replaced_same_semantics_after_resolution` shows the contract will happily dispatch to a *different* underlying element than the one originally resolved, if it is observably indistinguishable at freshness-check time. This is the documented, accepted cost of "no UniversalElement" — not a defect — but it means the contract cannot detect a real "identity laundering" attack where an adversary can make a different, dangerous control expose identical role/name/text/state to a benign one. Mitigating that further (e.g., stronger container/relation constraints, or task-level sanity checks) is out of M1's scope.
- **`ordinal` is position-based, not identity-based.** `ordinal_disambiguation_then_reorder` shows that reordering can change which element ordinal `N` refers to. Both `resolve()` and the independent oracle apply identical ordinal semantics, so this is not classified as a safety failure, but callers should treat `ordinal` as a last resort per its docstring, not a default disambiguator.
- **No expressive way to require "no container."** `TargetSpec.container_hint=None` means "don't care," not "must have none." Not needed by any scenario this milestone required; noted for a future milestone if it becomes load-bearing.
- **No retry-after-abstention.** If T0 resolution is itself `AMBIGUOUS`/`ABSENT`, M1 abstains immediately and never attempts a second resolution later. Deciding whether/when to retry, replan, or hand off belongs to the durable controller (M3), not this module.
- **`freshness_check` trusts its `fresh_observation` argument to actually be fresh.** Nothing in `grounding.py` can independently verify that; enforcing "you must have just observed" is a caller-discipline responsibility that M3's controller will own.

## Q. Ready to freeze?

**Yes**, for the scope defined in `docs/IMPLEMENTATION_PLAN.md` M1. The contract held under ~39,300 adversarial deterministic trials across 21 scenario classes including one added specifically to close a coverage gap found during active adversarial review, with zero wrong-target or stale-target dispatches and correct abstention throughout. Recommend freezing `computer_agent/types.py` and `computer_agent/grounding.py` as implemented, subject only to additive changes needed by M2 (which should not need to modify M1's public contract, only add `verification.py` alongside it).

## R. Recommended next milestone

**M2 — Independent verifier** (`docs/IMPLEMENTATION_PLAN.md`): build `computer_agent/verification.py` and the deceptive Fixture B, gated on zero verifier false-successes across ≥1,000 injected trials, directly motivated by the measured Chrome `AXPress` false-success finding in `phase0/MAC_APP_CAPABILITY_REPORT.md` §G.
