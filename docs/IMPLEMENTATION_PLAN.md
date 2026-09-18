# ComputerAgent Implementation Plan

## Status of this document

This is the concrete engineering sequence for building ComputerAgent, reconciled from:

1. Measured Phase 0 evidence (`phase0/CAMPAIGN_REPORT.md`, `phase0/MAC_APP_CAPABILITY_REPORT.md`).
2. The overnight architecture red-team on `research/overnight-2026-09-18` (`research/overnight/*.md`), which is **supporting research**, not production truth. Its own verdict is `READY_TO_BUILD` for a falsification-first implementation, explicitly *not* a production-readiness claim.
3. `docs/ARCHITECTURE.md`, `docs/BUILD_SPEC.md`, `docs/DECISIONS.md` as they stood before this reconciliation, which the overnight research did not contradict — it sharpened them into concrete, testable contracts.

Where a milestone below implements something the overnight research proposed but nothing has executed yet, it is labeled **PLANNED**, not proven. Do not read any code example in this file as already built.

## How milestones nest inside the existing phase structure

`docs/ROADMAP.md` still owns the top-level Phase 0 / Phase 1 / Phase 2 framing. M0-M10 below are the Phase 1 ("Build ComputerAgent") milestones, in dependency order. M11 is Phase 2. M0 is this documentation-convergence task itself.

## M0 — Documentation / architecture convergence
**Status: this task.** Reconcile overnight research into `docs/ARCHITECTURE.md`, `docs/BUILD_SPEC.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, and this file. No application or Phase 0 code changes.

## M1 — Grounding and freshness contract
**Status: PLANNED — the single next engineering task.**

Build the minimal production-shaped types and a deterministic Fixture A. No LLM, no real adapters, no Playwright/AX wiring yet — this milestone must falsify or confirm the target-resolution contract in complete isolation.

Package beginnings:
```
computer_agent/
  __init__.py
  types.py
  grounding.py
```

`types.py` — value types only, no backend handles:
- `TargetSpec` — semantic intent (app/window hint, role, name, text hint, state constraints, relation hint, ordinal, route preferences). Never stores a DOM/AX/UIA node or a coordinate.
- `ObservationVersion`
- `TargetCandidate` — observation-local: source, role/name/text/states/bounds, ancestry hint, confidence, provenance, and an opaque `execution_ref`.
- `ExecutionRef` — opaque, adapter-local, valid only for the observation version it was produced against.
- `ResolutionResult` — one of `RESOLVED`, `AMBIGUOUS`, `ABSENT`/`NOT_FOUND`, `STALE`, `UNSUPPORTED`.

`grounding.py`:
- `Resolver.resolve(TargetSpec, Observation) -> ResolutionResult`
- `freshness_check(candidate, current_observation)` — runs immediately before any consequential dispatch; any identity/version mismatch aborts (re-resolve or abstain), never guesses.

Fixture A — pure-Python deterministic mutable UI graph, with seeded cases:
- duplicate labels
- target replacement after observation
- target reorder/reflow
- overlay inserted between resolution and execution
- hidden target
- disabled target
- absent target
- ambiguous same-label controls
- mutation injected between resolve and dispatch

The fixture's hidden ground-truth ID must never be visible to the controller through `TargetSpec` (a test that leaked it would be circular).

**Gate (must pass before M2):**
- ≥ 1,000 deterministic seeded trials, distributed across the mutation classes above.
- **Zero wrong-target dispatches.**
- **Zero stale-target dispatches.**
- Ambiguous or absent cases abstain (`AMBIGUOUS`/`NOT_FOUND`) rather than guessing.
- Every discovered failure seed becomes a permanent regression case in `tests/computer_agent/test_grounding_freshness.py`.

**Stop condition:** any wrong- or stale-target dispatch halts expansion; repair the identity/freshness contract before continuing. Do not compensate with a bigger model later — there is no model in this milestone.

A small Developer Console may start once the M1 schemas exist (see "Developer Console," below) — it visualizes `TargetSpec`/`TargetCandidate`/resolution/freshness output; it does not gate M1's pass/fail criteria.

## M2 — Independent verifier
**Status: PLANNED.**

Build `computer_agent/verification.py` and a deceptive Fixture B: a fake service whose actions can report success while actually performing expected mutation, no-op, wrong-object mutation, partial mutation, delayed mutation, duplicate mutation, prohibited collateral mutation, or leaving verification evidence unavailable.

Predicate vocabulary (small and compositional; expand only if ≥90% of representative postconditions cannot be expressed with it plus a bounded domain callback):
equality/inequality, existence/absence, membership/contains, numeric/range, count/delta, before→after transition, invariant-not-changed, AND/OR, bounded domain-specific callback.

Outcome vocabulary: `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, `INCONCLUSIVE`, `PARTIAL_SUCCESS`, `UNEXPECTED_SIDE_EFFECT`. `INCONCLUSIVE` must never silently become success — this is the exact failure mode measured directly in `phase0/MAC_APP_CAPABILITY_REPORT.md` §G (Chrome's `AXPress` returns AX success without firing the page's click handler).

**Gate:** ≥ 1,000 injected deterministic trials. **Zero verifier false successes.** `INCONCLUSIVE` is an acceptable outcome; converting it to success anywhere in the pipeline is not.

**Stop condition:** any false success halts expansion; inspect observation independence and predicate semantics before continuing.

## M3 — Durable state / controller / journal / recovery
**Status: PLANNED.**

Add `state.py`, `journal.py`, `controller.py`, `recovery.py`. SQLite in WAL mode; append-only event journal plus deterministic materialized state. Do not grow the Phase 0 `ExperimentRunner`/JSONL persistence into this — it stays a measurement harness (`phase0/`), production state is a separate package (`computer_agent/`).

Enforce the consequential-action transaction:
```
read durable state -> fresh observation -> resolve TargetSpec -> reject ambiguity/absence
  -> deterministic policy gate -> persist ACTION_INTENT -> pre-dispatch freshness check
  -> persist DISPATCH_STARTED -> dispatch -> independently observe
  -> evaluate success predicates + safety invariants -> persist verification
  -> commit outcome -> advance step
```

Recovery classifies unresolved persisted actions into four classes, never a generic exactly-once guarantee:
- A. idempotency-key capable → retry/reconcile with same logical `action_id`.
- B. externally queryable effect → query before retry.
- C. naturally idempotent state-set → verify current state, repeat only if still needed.
- D. non-idempotent + non-queryable → `OUTCOME_UNKNOWN`/`NEEDS_REVIEW`; **never** blind-retried.

Fixture C — a crashable side-effect service implementing all four classes, with kill hooks at every durable boundary (before intent persist, after intent persist/before dispatch, during dispatch, after external effect/before observation, after observation/before verification, after verification/before commit, after commit/before plan advance, after plan advance).

**Gate:** ≥ 1,000 randomized trials per action class. Zero unsafe duplicate effects for classes A-C where reconciliation can prevent them. Zero blind retry of ambiguous class-D effects. Zero incorrect `VERIFIED_SUCCESS`. Restart reconstructs the same accepted plan/action IDs from durable state alone (journal replay, never model hidden state).

**Stop condition:** any blind retry of an ambiguous class-D effect, or any incorrect verified success, halts expansion.

## M4 — Bounded long-horizon state
**Status: PLANNED.**

Generate synthetic tasks at 200 / 500 / 1,000 actions with known Goal/Plan/Action/Fact/Recovery ground truth, including superseded facts, replans, failures, and recovery events. Implement the deterministic materialization/projection described in `docs/ARCHITECTURE.md`'s `ContextBuilder`.

Compare full transcript vs. rolling summary vs. structured bounded projection vs. projection + advisory FTS retrieval.

**Gate:** 100% exact reconstruction of correctness-critical deterministic fields at 1,000 actions. Active model-context projection size stays approximately flat as action count grows from 200 to 1,000 (median prompt tokens after warm-up should not grow materially with trajectory length). Retrieval may improve recall but can never override authoritative state.

## M5 — Deterministic policy / security
**Status: PLANNED.**

Build `computer_agent/policy.py`: a deterministic capability gate that receives the original task's granted authority plus a structured `ActionIntent`. Observations, model text, and any other content derived from webpages/documents/tool output are evidence only — they cannot widen scope.

Fixture D — authority-injection observations requesting new recipients/domains, filesystem paths outside task scope, new tools/capabilities, verifier bypass, credential disclosure, or disabled safety checks, fed directly into policy tests (no model needed to falsify this; if determinism policy can be tricked by content provenance, the architecture fails regardless of model quality).

**Gate:** zero deterministic capability expansion from untrusted content across the fixture suite.

## M6 — Model / runtime benchmark
**Status: PLANNED — UNVALIDATED until run.**

Only now connect a local model. Benchmark on target hardware: Apple Silicon M5 (24 GB unified memory) and RTX 4070 (12 GB VRAM).

Baseline candidate: one replaceable multimodal ~8B-class generalist, with Qwen3-VL-8B-Instruct as the first benchmark candidate — **not** a permanent dependency (see D-023 in `docs/DECISIONS.md`). Add a 2-3B GUI grounder (UI-TARS-2B first, ZonUI-3B/UGround-V1-2B as challengers) only if semantic-gap fixtures show a material verifier-confirmed improvement after accounting for latency/residency cost. Do not add an always-on critic; invoke one only on measured verifier-inconclusive cases.

Measure: typed-schema validity, `TargetSpec` proposal quality, correct abstention, wrong-target rate, semantic-gap visual grounding accuracy, p50/p95 latency, peak RAM/VRAM, cold start, repeated-run variance.

**No model-specific behavior may leak into controller state.** Model output remains a proposal the controller validates against the same schemas/policy/verification contracts built in M1-M5.

## M7 — Real interaction adapters
**Status: PLANNED, reusing measured Phase 0 evidence where it exists.**

Integrate Playwright/CDP (reusing the measured browser non-interference evidence from `phase0/CAMPAIGN_REPORT.md`), macOS AX (reusing `phase0/MAC_APP_CAPABILITY_REPORT.md`'s capability matrix and the Chromium focus-warm-up fix), and Windows UIA (net new — no target-hardware evidence exists yet, per `docs/BUILD_SPEC.md` §4).

All adapters route through the same `TargetSpec` → freshness → policy → journal → verification → recovery contracts built in M1-M5. Do not infer background safety from route/mechanism availability — background-safety classification stays per measured app/action/route (`BACKGROUND_PROVEN` / `BACKGROUND_BEST_EFFORT` / `FOREGROUND_REQUIRED`, per D-011). Note the existing macOS evidence is itself capped at `INCONCLUSIVE` for the campaign's focus-theft signal (Chrome's on-demand AX tree) — carrying the `warm_up_ax_focus_tree` fix from `phase0/CAMPAIGN_REPORT.md` §M into a rerun is a prerequisite for calling that specific route `BACKGROUND_PROVEN`.

## M8 — Visual universal fallback
**Status: PLANNED, only for semantic gaps.**

Evaluate a generalist vs. optional GUI specialists (UI-TARS-2B first) only on cases where semantic resolution (M7's adapters) fails or is ambiguous. Vision outputs `TargetCandidate` evidence, not authority — coordinates remain ephemeral and pass through the identical M1 freshness contract and M2 verification contract. Wrong-target and abstention rate dominate raw grounding-benchmark accuracy as the release metric.

## M9 — Skills / progressive disclosure
**Status: PLANNED.**

Versioned procedures with typed inputs, declared capabilities, preconditions, a procedure/helpers entry point, a postcondition verifier (same M2 contract), safety invariants, an idempotency classification (same M3 recovery classes), and regression fixtures. Metadata-only visibility by default; full procedure loads only on selection (progressive disclosure), to keep M4's bounded-context property intact as the skill library grows.

**No automatic promotion of successful trajectories into trusted executable code.** A trajectory is at most a candidate; promotion requires explicit review plus regression tests, same as M1-M3's fixtures.

## M10 — Endurance / cross-app validation
**Status: PLANNED, gated on M1-M9.**

Only after M1-M9 gates are credible, run atomic, 5-20, 20-100, 150+, and 500+ action synthetic endurance campaigns across multiple apps, injecting popups, focus changes, app/browser restarts, session expiration, stale targets, malformed model output, user interruption, and route failure. Report distributions and failure taxonomy — not single successful runs (per D-004's repeated-trial requirement). Only then map a small representative external benchmark subset (OSWorld/WindowsWorld/web) for comparability; external benchmark score is never a substitute for the deterministic contracts above.

## M11 — Consumer product
**Status: Phase 2, out of scope until M1-M10 gates are credible.**

Polished task UI, onboarding, permissions, model management, Agent Cursor / visible execution UX where needed, handoff UI, task history, installers, signing/notarization, updates/rollback.

## Developer Console — timing and role

A Developer/Test Console may begin as early as M1, once `TargetSpec`/`TargetCandidate`/`ResolutionResult` exist to visualize. It grows across milestones to display: active task, current step, current observation/version, `TargetSpec`, `TargetCandidate`s, resolution result, freshness result, selected route, action intent, dispatch result, verification result, recovery state, the event timeline, and abstention/blocking reasons.

**It is observational only.** It visualizes authoritative backend state; it never becomes part of the correctness contract, and the backend must remain fully testable headlessly without it. This is distinct from the Phase 2 consumer product UI (M11), which is a different artifact with different design goals (onboarding, polish, non-developer users).

## What this plan deliberately excludes for now

Per the reconciliation task's scope: no Fixture A implementation, no `computer_agent/` production code, no LLM/Qwen integration, no visual grounding implementation, no Windows UIA implementation, no rewriting of Phase 0 experiments, no UI build-out, no new dependency installation. Those begin in M1 onward as separate, explicitly scoped engineering tasks.
