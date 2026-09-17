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
