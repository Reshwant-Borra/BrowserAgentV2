# ComputerAgent Architecture Decision Ledger

This file records decisions that coding agents must not casually reverse. A decision may change when Phase 0 evidence disproves it; record the evidence and replacement explicitly.

## D-001 — Evolve BrowserAgentV2 rather than wholesale restart
**Status:** Accepted

Preserve useful reliability concepts: authoritative controller, durable event traces/state, independent verification, explicit handoff, provenance-bearing facts, loop detection, recovery/reconciliation, and refusal to blindly retry ambiguous state-changing actions.

## D-002 — ComputerAgent, not browser-only architecture
**Status:** Accepted

Broaden execution from BrowserKernel-only assumptions to an interaction fabric spanning native tools/APIs, browser semantics, desktop accessibility, visual grounding, isolation where supported, and human handoff.

## D-003 — No literal host “second mouse” as the core abstraction
**Status:** Accepted

Provide a second-cursor experience using cursorless semantic actions plus isolated coordinate interaction when supported. Generic host pointer injection is not the default.

## D-004 — Vision is an escalation path
**Status:** Accepted

Prefer deterministic/semantic representations when available. Screenshot/coordinate control exists for inaccessible/custom UI, not as the mandatory representation for every step.

## D-005 — Authoritative state lives outside the model
**Status:** Accepted

The model proposes decisions over bounded working context. Goal, plan, facts, events, artifacts, policy, verification, and recovery are application state.

## D-006 — Bounded context is a first-class requirement
**Status:** Accepted

Long task duration must not cause linear prompt growth. Retrieval and milestone state replace transcript accumulation.

## D-007 — State-changing actions use intent -> execute -> observe -> verify -> persist
**Status:** Accepted

On ambiguous restart, never blindly duplicate an external side effect.

## D-008 — Safety/policy is outside the model
**Status:** Accepted

Untrusted UI/web content cannot grant authority or rewrite user constraints. Consequential actions and authentication/security boundaries are governed by deterministic policy/handoff.

## D-009 — Hardware-adaptive inference
**Status:** Accepted

Probe physical resources and capabilities. Do not hard-code model selection by GPU name. Apple unified memory and laptop/desktop GPU differences require resource-aware profiles.

## D-010 — Model/runtime choice remains experimentally open
**Status:** Phase 0 gate

Do not commit to Qwen3-8B, UI-TARS, llama.cpp, Ollama, MLX, vLLM, or another candidate merely from reputation. Benchmark supported candidates under common fixtures and target hardware. Existing Qwen3-8B remains a useful control baseline.

## D-011 — Background safety is measured per route/action/app class
**Status:** Accepted

Use explicit capability metadata such as `BACKGROUND_PROVEN`, `BACKGROUND_BEST_EFFORT`, and `FOREGROUND_REQUIRED`. Never infer background safety from model confidence.

## D-012 — macOS and Windows are P0; Linux later
**Status:** Accepted

Cross-platform architecture begins immediately, but Linux is not required to block the first product validation.

## D-013 — Isolated desktop/workspace is capability-gated
**Status:** Accepted

Do not promise arbitrary local app/session duplication inside a VM or isolated environment. Use isolation where it is measured and practical; otherwise hand off or use a foreground-required route.

## D-014 — Repository Markdown is the development source of truth
**Status:** Accepted

`CLAUDE.md`, `PRODUCT.md`, `ARCHITECTURE.md`, `BUILD_SPEC.md`, `ROADMAP.md`, and this decision ledger provide operational context. Research PDFs remain supporting evidence.

## D-015 — Graphify is auxiliary developer memory only
**Status:** Accepted

Graphify may index repository documentation/code to improve Claude retrieval and cross-session navigation, but it is not authoritative state and is not required for ComputerAgent to build or run. Verify the exact Graphify implementation, license, setup, and security before installation. Keep it removable and do not commit secrets or generated private indexes.

## D-016 — Do not optimize architecture around example tasks
**Status:** Accepted

Examples are evaluation cases, not architecture specifications. New examples should become fixtures/benchmarks without causing ad-hoc core redesign unless they reveal a genuine general architectural gap.
