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
- **WebRL / WebAgent-R1:** open 3B–8B class models can improve dramatically at web tasks through web-specific multi-turn training, supporting a future local-model training path if zero-shot Qwen3:8B is insufficient.
- **WEBSERV:** compact site-agnostic observations and deterministic browser/UI waiting are themselves important design variables for scalable web agents.
- **World-model / DynaWeb research:** transition-focused state changes and training from structured trajectories are promising later extensions, which is why V2 preserves before/action/after/verification traces.
- **Online-Mind2Web / BrowserArena:** live websites drift and repeatedly expose CAPTCHA, popup/banner, navigation and other mundane environment failures that sandbox benchmarks can hide.
- **AgentDojo / InjecAgent / BIPIA:** webpage content must be treated as untrusted input and constrained by a policy layer outside the model.

See `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md` and `01_RESEARCH/RECENT_2025_2026_WEB_AGENT_RESEARCH.md` for the detailed evidence and caveats.

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

The large orchestration modules (`agent/controller.py` ~104 KB and `agent/loop.py` ~69 KB) should **not** be ported wholesale. V2 reuses tests, contracts, and small deterministic utilities while rewriting orchestration around one state machine. The old tests also document regressions around tab binding, typing/search, inference retry, verification/recovery and crash recovery; these have been converted into a V2 regression matrix.

See:
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`

## Recommended reading order

1. `00_PROJECT/VISION_AND_SCOPE.md`
2. `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md`
3. `01_RESEARCH/RECENT_2025_2026_WEB_AGENT_RESEARCH.md`
4. `01_RESEARCH/FAILURE_MODES_AND_MITIGATIONS.md`
5. `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
6. `01_RESEARCH/BROWSER_RUNTIME_RESEARCH.md`
7. `01_RESEARCH/GROUNDING_AND_CONTEXT.md`
8. `01_RESEARCH/QWEN_MODEL_INTERFACE.md`
9. `01_RESEARCH/MODEL_STRATEGY_AND_TRAINING_PATH.md`
10. `01_RESEARCH/MEMORY_RECOVERY_AND_SECURITY.md`
11. `02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md`
12. `02_ARCHITECTURE/LONG_RESEARCH_AND_MEMORY_ARCHITECTURE.md`
13. `03_DECISIONS/ARCHITECTURE_DECISIONS.md`
14. `06_OPEN_QUESTIONS/DECISION_GATES_V2.md`
15. `04_TESTING/MASTER_VALIDATION_PLAN.md`
16. `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`
17. `05_IMPLEMENTATION/FULL_PROJECT_ROADMAP.md`
18. `05_IMPLEMENTATION/TWO_DAY_EXECUTION_PLAN_V3.md`
19. `RESEARCH_STATUS.md`
20. `SOURCES.md`

## Folder map

- `00_PROJECT/` — product goal, scope and constraints
- `01_RESEARCH/` — research papers, browser runtime, model, grounding, memory, security, old-code audit and failure analysis
- `02_ARCHITECTURE/` — complete runtime contracts, long-research design, and system architecture
- `03_DECISIONS/` — architectural choices and rejected approaches
- `04_TESTING/` — deterministic kernel tests, model evaluations, old-regression matrix, fault injection, security tests, controlled/live benchmarks
- `05_IMPLEMENTATION/` — entire phased roadmap plus concrete two-day MVP sequence
- `06_OPEN_QUESTIONS/` — explicit unresolved experiments/decision gates

## P0 gates — resolved

All nine P0 gates were resolved by the experiment campaign on
`experiment/p0-gate-campaign`. Roughly 2,200 experiment runs and 1,000 local
model calls; every raw row is committed under `experiments/*/results/`.

| Gate | Verdict |
|---|---|
| Browser kernel | `ADOPT_DIRECT_PLAYWRIGHT` |
| Decision interface | `ADOPT_STRICT_JSON` |
| Qwen3:8B adequacy | **`QWEN3_8B_INADEQUATE`** |
| Observation invalidation | `INVALIDATION_RESOLVED` |
| Page registry / ownership | `PAGE_REGISTRY_RESOLVED` |
| Side-effect recovery | `SIDE_EFFECT_RECOVERY_RESOLVED` |
| Human handoff | `HANDOFF_RESOLVED` |
| Policy / security boundary | `POLICY_BOUNDARY_RESOLVED` |
| Browser profile | `DEDICATED_PROFILE_RESOLVED` |

Start here:

- [`experiments/P0_EXPERIMENT_INDEX.md`](experiments/P0_EXPERIMENT_INDEX.md) — gate to evidence
- [`experiments/p0_summary/P0_CONSOLIDATION.md`](experiments/p0_summary/P0_CONSOLIDATION.md) — go / no-go
- [`03_DECISIONS/ARCHITECTURE_FREEZE_V1.md`](03_DECISIONS/ARCHITECTURE_FREEZE_V1.md) — what is frozen

**The mechanics are proven; the decision layer is not.** Qwen3:8B has perfect
schema validity and determinism, never invented a target, and obeyed none of 16
hostile pages — but it misses the pre-registered adequacy bar on judgment
(sequencing 33%, recognising no-valid-action 57%). It is frozen as a decision
*source* behind the deterministic boundary, not as an autonomous *policy*.

The single most important finding for sequencing: the PolicyEngine catches the
model's dangerous mistakes, but not the class where it clicks a legitimate
control for the wrong reason. Only the Verifier can, and the Verifier does not
exist yet. **Build it before the controller loop.**

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
