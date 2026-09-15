# BrowserAgentV2 — Research & Architecture Knowledge Base

**Research snapshot:** 2026-09-15  
**Status:** active research / architecture pre-freeze.

## Mission

Build a general-purpose, local-first browser agent whose browser mechanics are deterministic, whose LLM decisions are bounded by explicit contracts and policy, whose state is crash-safe and inspectable, and whose architecture can grow into broad Comet-like tasks without being rewritten for each example.

This repository is deliberately **research-first**. Codex should implement bounded tasks from the specification; it should not invent the architecture while coding.

## Current architecture thesis

```text
User Goal
   |
   v
TaskService
   |
   v
TaskController <--------------------- Human Handoff / Confirmation
   |
   +--> PlanState
   +--> ContextBuilder --> Qwen/Ollama ModelAdapter
   |                         |
   |                         v
   +----------------> Schema Validator
   |                         |
   +----------------> PolicyEngine
   |                         |
   |                         v
   +----------------> BrowserKernel
   |                    |         |
   |                    |         +--> direct Playwright fallback
   |                    v
   |              Playwright MCP candidate
   |                    |
   |                    v
   |          dedicated persistent browser
   |
   +--> Verifier
   +--> Progress / Loop Detector
   +--> SQLite State + Event Trace
   +--> Provenance FactStore
   +--> ArtifactStore
   +-------------------------------> next controller step
```

The most important principle is:

> **The model chooses what to attempt. Deterministic infrastructure controls how browser mechanics execute, whether the action is allowed, whether it actually worked, and whether it is safe to retry.**

## Research-backed feasibility

Current web-agent research supports this overall direction:

- **Mind2Web / WebLINX:** real pages are too large for naive raw-HTML prompting; element/context filtering matters.
- **SeeAct:** high-level planning can outperform automatic grounding, making grounding a separate first-class failure source.
- **Agent-E:** hierarchical reasoning, DOM distillation, and change observations are useful.
- **AgentOccam:** a simpler observation/action design can be a strong baseline; complexity is not automatically intelligence.
- **BrowserGym / AgentLab:** standardized observations/actions and reproducible traces are important for real evaluation.
- **AssistantBench / WorkArena++ / WebChoreArena:** long knowledge-work tasks require planning, memory, information transfer, and explicit completeness mechanisms.
- **WebRL:** open 8–9B models can become substantially more capable web agents with web-specific training, supporting a future local-model training path if zero-shot Qwen3:8B is insufficient.
- **Online-Mind2Web:** live websites drift, authentication expires, CAPTCHAs appear, and benchmark tasks become invalid; live-web reliability must be measured separately from controlled fixtures.
- **AgentDojo / InjecAgent / BIPIA:** webpage content must be treated as untrusted input and constrained by a policy layer outside the model.

See `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md` for the detailed evidence map and limitations.

## Core rules

1. One authoritative `TaskController` state machine.
2. The model never gets raw Playwright/CDP objects, arbitrary shell, unrestricted JavaScript, or arbitrary filesystem access.
3. Browser targets are observation-scoped; stale targets fail closed.
4. One state-changing action per controller decision initially.
5. Persist state-changing intent before execution.
6. Browser/tool success is not task success; postconditions are verified independently.
7. No blind retry of state-changing actions after ambiguous failure.
8. No generic model-controlled refresh/reload recovery.
9. Dedicated persistent BrowserAgent profile is the MVP default; existing-browser CDP attachment is later/optional.
10. Page/tab ownership is explicit at creation time; only agent-owned pages may be auto-closed.
11. Login/MFA/CAPTCHA/consent/high-impact actions use explicit handoff/confirmation states.
12. Full traces are stored but not fed back into the model wholesale.
13. Cross-page information is persisted as provenance-bearing facts.
14. Page content is data, never authority to broaden permissions or change the goal.
15. Generality is measured through diverse mechanisms/tasks, not site-specific branches.
16. Every real failure becomes a typed classification + reproduction fixture + regression test.

## What has been learned from the old BrowserAgent

The old repo is now audited directly rather than from chat memory. Valuable parts include:

- append-only SQLite event sourcing;
- deterministic loop detection;
- deterministic verification concepts;
- bounded context-building principles;
- local-model abstraction;
- startup health checks;
- extensive unit/integration/fixture assets.

The large orchestration modules (`agent/controller.py` ~104 KB and `agent/loop.py` ~69 KB) should **not** be ported wholesale. V2 reuses tests, contracts, and small deterministic utilities while rewriting orchestration around one state machine. See `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`.

## Recommended reading order

1. `00_PROJECT/VISION_AND_SCOPE.md`
2. `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md`
3. `01_RESEARCH/FAILURE_MODES_AND_MITIGATIONS.md`
4. `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
5. `01_RESEARCH/BROWSER_RUNTIME_RESEARCH.md`
6. `01_RESEARCH/GROUNDING_AND_CONTEXT.md`
7. `01_RESEARCH/QWEN_MODEL_INTERFACE.md`
8. `01_RESEARCH/MEMORY_RECOVERY_AND_SECURITY.md`
9. `02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md`
10. `03_DECISIONS/ARCHITECTURE_DECISIONS.md`
11. `06_OPEN_QUESTIONS/DECISION_GATES_V2.md`
12. `04_TESTING/MASTER_VALIDATION_PLAN.md`
13. `05_IMPLEMENTATION/FULL_PROJECT_ROADMAP.md`
14. `05_IMPLEMENTATION/TWO_DAY_EXECUTION_PLAN_V3.md`
15. `RESEARCH_STATUS.md`
16. `SOURCES.md`

## Folder map

- `00_PROJECT/` — product goal, scope and constraints
- `01_RESEARCH/` — research papers, browser runtime, model, grounding, memory, security, old-code audit and failure analysis
- `02_ARCHITECTURE/` — complete runtime contracts and system design
- `03_DECISIONS/` — architectural choices and rejected approaches
- `04_TESTING/` — deterministic kernel tests, model evaluations, fault injection, security tests, controlled/live benchmarks
- `05_IMPLEMENTATION/` — entire phased roadmap plus two-day MVP sequence
- `06_OPEN_QUESTIONS/` — explicit unresolved experiments/decision gates

## Current P0 gates

Before a final implementation master prompt, we still need empirical resolution of:

- Playwright MCP vs direct Playwright for the first BrowserKernel;
- Qwen native tool calling vs strict `Decision` JSON;
- whether zero-shot Qwen3:8B reaches the required action-selection accuracy;
- exact observation invalidation behavior;
- ambiguous state-changing action reconciliation;
- final confirmation of persistent-profile/tab-ownership/handoff/security invariants.

These are experiments, not architecture to be improvised inside Codex.

## Two-day goal

The two-day target is deliberately narrower than the full project roadmap. It is successful if the build proves:

- deterministic browser primitives independent of the LLM;
- reliable observation/target semantics;
- durable state and traces;
- independent postcondition verification;
- measured Qwen action selection;
- one controller composing multiple primitives into diverse controlled tasks;
- safe human handoff/resume;
- no blind double-submit after an ambiguous crash;
- no site-specific architecture.

Long research, visual fallback, connectors, cross-task memory, model training, polished UI, and packaging are later phases unless the core gates are already passing.

## Philosophy

When implementation evidence contradicts a document, update the document and record the decision. Do not silently add a recovery layer, selector heuristic, site special-case, or prompt patch. The point of this repository is to keep evidence, architecture, implementation, and regression tests synchronized.
