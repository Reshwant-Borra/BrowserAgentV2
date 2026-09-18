# ComputerAgent Build Specification

## Status

Current stage: **Phase 0 — validation and evidence collection**.

This document becomes progressively more authoritative as measured Phase 0 results replace assumptions. Do not claim a capability as proven until its gate has evidence.

## Phase 0 objective

Build a reusable capability/benchmark harness that determines what ComputerAgent can safely and reliably do on target macOS and Windows machines before freezing production implementation choices.

## Required Phase 0 workstreams

### 1. HardwareProfiler
Collect at minimum:
- OS/version and architecture
- CPU
- physical and currently available RAM
- GPU/vendor/model
- dedicated VRAM when applicable
- unified-memory characteristics on Apple Silicon
- available accelerator/runtime backends
- relevant screen-capture/accessibility permissions
- virtualization/isolation availability
- battery/thermal information where useful for endurance tests

Output machine-readable capability data and a human-readable report.

### 2. Browser non-interference harness
Test Playwright-driven browser actions while continuously recording physical cursor coordinates, foreground application/window, keyboard focus where measurable, target window/tab, action type, pre/post state, and failures.

Test click, type/fill, scroll, navigation, tabs, downloads, stale targets, popups, and repeated action sequences.

P0 target: semantic browser execution causes **zero unexpected physical pointer movement** and does not steal unrelated application focus in the tested background-safe route.

### 3. macOS Accessibility harness
Measure AXUIElement inspection/actions across representative native and custom applications. Record cursor movement, focus/window changes, stale-element behavior, permission state, and unsupported controls.

Do not mark an AX action `BACKGROUND_PROVEN` without measurement.

**Measured (2026-09-17):** a breadth capability survey across 8 representative applications (Finder, Notes, Calendar, System Settings, Safari, Chrome, VS Code/Electron, the existing Cocoa fixture) is recorded in `phase0/MAC_APP_CAPABILITY_REPORT.md`. Discovery/read is broadly supported; verified action/value-mutation is not — native system apps were deliberately left untested for mutation (real user data), and both browsers showed a genuine action/mutation gap (Chrome's `AXPress` doesn't invoke a plain HTML button's handler; both browsers' `AXValue` writes into web form fields were ordering-sensitive). This is evidence *for* the existing browser-semantics-before-AX routing preference (D-002), not a reason to change it. Still not `BACKGROUND_PROVEN` for any real (non-fixture) application's action route — see that report's §L/§M for what remains open.

### 4. Windows UIA harness
Measure UI Automation semantic patterns including inspect/search, InvokePattern, ValuePattern, scrolling, waiting, occluded targets where supported, and representative Electron/custom UI coverage.

Separate semantic UIA operations from physical click/send-key injection.

### 5. Model/runtime benchmark harness
Use a fixed fixture dataset containing browser semantic states, desktop accessibility states, screenshot-grounding states, planning checkpoints, and failure/recovery checkpoints.

Benchmark suitable current candidates rather than hard-coding one model family. Include the existing Qwen3-8B baseline plus small/medium planner and GUI-specialist candidates identified by current research and verified availability.

Runtime candidates should include llama.cpp and development-friendly/current platform comparators; include MLX on Apple Silicon when appropriate. Only test a runtime/model combination when actually supported.

Collect:
- peak GPU/unified/host memory
- cold load time
- time to first token
- decode throughput
- full action-decision latency
- vision preprocessing latency
- structured schema validity
- accepted-action accuracy
- grounding accuracy where applicable
- p50/p95 latency
- one-hour thermal/energy/stability behavior
- OOM/crash rate

Test multiple bounded context sizes, including roughly 2K, 8K, 16K and a larger stress condition where supported. The objective is the smallest context that preserves task quality, not the largest context that can technically fit.

Initial targets (engineering gates, not claims):
- structured decision schema validity >= 99.5%
- controlled easy-fixture semantic action selection >= 90%, with harder baseline recorded separately
- semantic hot-path p95 decision < 2 seconds desired on capable target hardware
- vision-route p95 decision < 4 seconds desired on capable target hardware
- sufficient memory headroom for stable operation
- no OOM during endurance run
- invalid/stale target executions = 0

### 6. Grounding benchmark
Compare semantic-only baseline with verified current visual/GUI candidates such as UI-TARS and parser/VLM routes where licensing and hardware permit.

Measure correct element, box/pixel error where relevant, small-icon accuracy, text-control accuracy, duplicate-label ambiguity, latency, memory, and abstention/failure detection.

### 7. Long-horizon bounded-context benchmark
Create deterministic tasks around 50, 200, 500, and 1,000 actions. Inject constraints/facts early that matter much later.

Compare rolling transcript, rolling summary, and ComputerAgent structured-state retrieval.

Measure constraint retention, fact recall precision/recall, wrong-fact contamination, average input tokens/step, p95 latency, memory/KV behavior, loop rate, task success, and recovery success.

Critical P0 gate: average decision-prompt size should remain approximately flat as task length grows from 200 to 1,000 actions.

### 8. Crash/side-effect reconciliation
Fault-inject before intent persistence, after intent persistence, during execution, immediately after execution, during verification, and after verification before state advance.

Test representative state-changing fixtures such as form submission, calendar/event creation fixture, file save, message draft, and cart fixture.

Critical invariant: **an ambiguous restart must never blindly perform a second state-changing action.**

### 9. Security/handoff tests
Test malicious/untrusted content attempting to change the goal, exfiltrate secrets, trigger purchases/uploads/deletions, or falsely report success.

Policy must structurally prevent ungranted capabilities. Authentication, MFA, CAPTCHA, secret entry, and OS security prompts require human handoff.

### 10. Existing BrowserAgentV2 regression conversion
Preserve historical lessons by converting known tab-binding, typing, inference-retry, ambiguous verification, crash/recovery, stale-target, and looping failures into regression fixtures before relying on higher-level benchmark scores.

## Evidence format

Every Phase 0 probe should produce machine-readable evidence with at least:
- test/probe ID
- timestamp
- git commit
- OS/hardware profile
- adapter/runtime/model versions
- configuration
- actions/inputs
- pre/post observations
- metrics
- pass/fail/uncertain result
- artifact references
- error/failure classification

Raw benchmark output belongs in a dedicated results/artifacts location and should not be pasted into model prompts by default.

## Phase 0 completion criteria

Phase 0 is complete when:
1. Browser background behavior is measured on target macOS and Windows configurations.
2. AX and UIA capability matrices exist with explicit background-safety classifications.
3. Model/runtime selection is evidence-based per hardware class.
4. Grounding route(s) have measured accuracy/latency/abstention behavior.
5. Bounded context survives long-horizon tests without linear prompt growth.
6. Crash reconciliation prevents blind duplicate side effects.
7. Security/handoff fixtures pass at the policy layer.
8. Historical BrowserAgentV2 failures remain covered.
9. `docs/DECISIONS.md` and `docs/ARCHITECTURE.md` are updated from measured evidence.

## Production-code rule

Phase 0 may build reusable libraries/interfaces when needed for measurement, but do not prematurely construct a giant final UI or lock in unmeasured implementation assumptions.

## Phase 1 (M1-M6) falsifiable gates

These gates convert `docs/IMPLEMENTATION_PLAN.md`'s milestones into pass/fail experiments, reconciled from the overnight research branch's `VALIDATION_PLAN.md`/`VERTICAL_SLICE_BUILD_SPEC.md` (`research/overnight-2026-09-18`, supporting research only — see D-017 through D-024 in `docs/DECISIONS.md`). **Measured status (2026-09-18):** M1, M2 and M3 **PASS** on their synthetic fixtures — see `computer_agent/M1_GROUNDING_REPORT.md`, `M2_VERIFICATION_REPORT.md`, `M3_CONTROLLER_RECOVERY_REPORT.md`; permanent gates run in the default `pytest` suite (`tests/computer_agent/test_campaign_gate.py`, `test_m2_gate.py`, `test_m3_gate.py`, plus real-SIGKILL `test_crash_reconciliation.py`). These are contract-level results on fixtures, not real-adapter capability claims. M4-M6 remain **PLANNED**. Implement strictly in order — a later gate's fixtures assume an earlier gate's contract is trustworthy.

### Gate M1 — Grounding freshness and abstention
**Hypothesis:** `TargetSpec -> fresh observation -> TargetCandidate -> ExecutionRef -> pre-dispatch freshness` achieves zero wrong/stale dispatch under seeded UI mutation.
**Experiment:** pure-Python deterministic mutable-UI Fixture A (`computer_agent/`), seeded with duplicate labels, replacement, reorder/reflow, overlay-between-resolve-and-dispatch, hidden/disabled/absent targets, ambiguity, and mutation between resolve and dispatch.
**Metric:** wrong-target dispatch rate; stale-target dispatch rate; correct-abstention rate on ambiguous/absent cases.
**Minimum trials:** >= 1,000 seeded trials, distributed across mutation classes.
**PASS:** zero wrong-target dispatches and zero stale-target dispatches; ambiguous/absent cases abstain.
**FAIL:** any wrong-target or stale-target dispatch.
**INCONCLUSIVE:** not applicable — the fixture is deterministic and fully observable; every trial must resolve to PASS or FAIL.
**Stop condition:** any FAIL halts all downstream milestones; repair the identity/freshness contract (`computer_agent/grounding.py`) before continuing. Every failing seed becomes a permanent regression in `tests/computer_agent/test_grounding_freshness.py`.
**Measured (M1):** PASS — 1,500-trial permanent gate (21 scenarios) + ~37,800-trial sweep: 0 wrong-target, 0 stale-target dispatch; re-confirmed byte-identical after the M2/M3 work.
**Architecture consequence on FAIL:** D-017's TargetSpec/TargetCandidate/ExecutionRef contract itself is called into question, not just its implementation — re-open grounding design before writing more code.

### Gate M2 — Verifier false-success resistance
**Hypothesis:** the small compositional predicate vocabulary (D-018) detects no-op/wrong-object/partial/delayed/duplicate/collateral mutation without app-specific DSL explosion.
**Experiment:** deceptive Fixture B — a fake service whose dispatch can report success while independently producing expected mutation, no-op, wrong-object mutation, partial mutation, delayed mutation, duplicate mutation, prohibited collateral effect, or leaving verification evidence unavailable.
**Metric:** false-success rate (critical); false-failure rate; inconclusive rate; predicate coverage across representative postconditions.
**Minimum trials:** >= 1,000 injected deterministic trials.
**PASS:** zero verifier false successes. `INCONCLUSIVE` outcomes are acceptable and must not be silently promoted to success anywhere in the pipeline.
**FAIL:** any false success.
**INCONCLUSIVE (design-level, not per-trial):** if >= 10% of representative BrowserAgentV2/ComputerAgent task postconditions cannot be expressed compositionally with the small vocabulary plus a bounded domain callback, treat the *vocabulary* as inconclusive and expand it deliberately rather than declaring the contract failed.
**Stop condition:** any false success halts downstream milestones; inspect observation independence and predicate semantics in `computer_agent/verification.py` before continuing.
**Measured (M2):** PASS — 2,200-trial permanent gate (44 behavior×action classes) + 13,200-trial seed sweep: 0 false successes, 0 false failures; sabotaged verifiers are caught by the same oracle. Predicate-coverage (≥90% of real postconditions) not yet measured against real tasks.
**Architecture consequence on FAIL:** re-open D-018 — evidence-source ordering or predicate semantics, not just the fixture, is suspect.

### Gate M3 — Crash/side-effect reconciliation
**Hypothesis:** durable intent + per-class reconciliation (D-020) prevents unsafe duplicate side effects across every crash boundary, and ambiguous non-idempotent/non-queryable effects never get blindly retried.
**Experiment:** crashable Fixture C implementing recovery classes A (idempotency-key capable), B (externally queryable), C (naturally idempotent state-set), D (non-idempotent + non-queryable), with kill hooks at every durable boundary (before intent persist; after intent persist/before dispatch; during dispatch; after external effect/before observation; after observation/before verification; after verification/before commit; after commit/before plan advance; after plan advance).
**Metric:** duplicate side effects; lost committed effects; incorrect success declarations; incorrect blind retries; recovery classification accuracy.
**Minimum trials:** >= 1,000 randomized trials per action class (A-D).
**PASS:** zero duplicate effects for A-C where reconciliation/idempotency makes that achievable; zero blind retry for ambiguous class D; zero incorrect `VERIFIED_SUCCESS`; deterministic journal replay reconstructs the same controller state after every kill point.
**FAIL:** any duplicate effect, any blind class-D retry, or any incorrect verified success.
**INCONCLUSIVE:** a class-D effect correctly surfaces as `OUTCOME_UNKNOWN`/`NEEDS_REVIEW` — this is a PASS outcome for that trial, not an inconclusive one; reserve INCONCLUSIVE for kill points the harness itself cannot observe cleanly (fix the harness, do not count these toward the trial total).
**Stop condition:** any FAIL halts downstream milestones; inspect the journal/recovery transition table (`computer_agent/journal.py`, `computer_agent/recovery.py`).
**Measured (M3):** PASS — 1,044 trials per class (4,176) across 12 crash boundaries with 25% double crashes, plus 240 + 48 trials with real `SIGKILL`: 0 duplicate effects, 0 lost effects, 0 incorrect `VERIFIED_SUCCESS`, 0 unsafe/blind class-D retries, 0 unverified step advancement, 0 replay mismatches. Power-loss/filesystem durability not tested.
**Architecture consequence on FAIL:** re-open D-019/D-020 — the SQLite WAL journal design or the four-class recovery taxonomy itself, not just this implementation.

### Gate M4 — Bounded long-horizon state reconstruction
**Hypothesis:** a structured bounded projection (D-006, elaborated by D-019) reconstructs correctness-critical state exactly at 1,000 actions while active model-context projection stays approximately flat.
**Experiment:** synthetic 200/500/1,000-action tasks with known Goal/Plan/Action/Fact/Recovery ground truth, including superseded facts, replans, failures, and recovery events. Compare full transcript vs. rolling summary vs. structured projection vs. structured projection + advisory retrieval.
**Metric:** exact reconstruction of deterministic fields; prompt tokens by action index; stale/superseded-fact contamination rate; required-fact recall.
**Minimum trials:** the 200/500/1,000-action generated set (not a repeated-trial gate in the same sense as M1-M3; report per-length results).
**PASS:** 100% exact reconstruction of correctness-critical deterministic fields at 1,000 actions; median active-projection token count does not grow materially from 200 to 1,000 actions.
**FAIL:** any incorrect reconstructed field at any tested length, or projection size growing materially with trajectory length.
**INCONCLUSIVE:** retrieval-augmented variant (D) shows improved recall but at ambiguous correctness cost — acceptable to defer D pending M6 model integration, provided variant C alone passes.
**Stop condition:** revise the state/projector schema before model integration (M6).
**Architecture consequence on FAIL:** re-open the state schema in `computer_agent/state.py`, not the model strategy.

### Gate M5 — Deterministic policy / authority-injection resistance
**Hypothesis:** a deterministic capability gate (D-021) blocks authority expansion from untrusted content regardless of model behavior.
**Experiment:** Fixture D — untrusted observation text/labels requesting new recipients/domains, filesystem paths outside task scope, new tools/capabilities, verifier bypass, credential disclosure, or disabled safety checks, fed directly into policy tests (no model required — this must fail purely at the policy layer if it fails at all).
**Metric:** authority-expansion acceptance rate.
**Minimum trials:** representative adversarial fixture suite covering each capability class (recipients, filesystem, tools, verifier, credentials, safety checks).
**PASS:** zero deterministic capability expansion from untrusted content.
**FAIL:** any accepted expansion.
**INCONCLUSIVE:** not applicable — policy is deterministic and fully observable per trial.
**Stop condition:** any FAIL blocks all consequential-action work; fix `computer_agent/policy.py` before continuing.
**Architecture consequence on FAIL:** re-open D-021's capability schema — likely too coarse, not merely buggy.

### Gate M6 — Model/runtime benchmark
**Hypothesis:** one replaceable ~8B-class multimodal generalist (Qwen3-VL-8B-Instruct first, D-023) meets schema/latency/memory/abstention gates on both target machines, without requiring a permanent specialist ensemble.
**Experiment:** common fixture set (semantic next-action selection, duplicate-label TargetSpec selection, screenshot grounding, absent/ambiguous-target abstention, tool/schema emission, adversarial authority-expansion text) run on Apple Silicon M5 (24 GB unified) and RTX 4070 (12 GB VRAM).
**Metric:** schema validity rate; wrong-target rate; abstention precision/recall; p50/p95 latency; peak RAM/VRAM; cold start; repeated-run variance.
**Minimum trials:** 200-500 fixture cases per candidate configuration, repeated for variance measurement.
**PASS (engineering gate, not a claim):** >= 99.5% schema-valid proposals after at most one repair attempt; absent/ambiguous false-click rate < 0.5%; zero policy-authority expansion accepted from adversarial text (re-validates M5 with the model in the loop); no OOM/crash across the run.
**FAIL:** miss any PASS threshold on the primary candidate.
**INCONCLUSIVE:** primary candidate fails on one target machine only — record as a hardware-tier-specific limitation, not an architecture failure; do not block the other tier.
**Stop condition:** on FAIL, replace the model behind the same typed proposal interface (`computer_agent/` model adapter boundary) — this must never require touching the controller, grounding, verification, or policy contracts built in M1-M5.
**Architecture consequence on FAIL:** none for the controller architecture; model identity is explicitly the replaceable layer (D-023).
