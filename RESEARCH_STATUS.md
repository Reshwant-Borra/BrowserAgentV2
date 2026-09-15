# Research Status

**Snapshot date:** 2026-09-15

## Current state

Research is now **top-to-bottom at the design level but still pre-freeze**. The repository contains:

- paper-backed feasibility evidence;
- 2025–2026 research updates;
- a detailed failure/mitigation catalog;
- a direct audit of the actual old BrowserAgent repository;
- an end-to-end system architecture;
- a dedicated long-research/memory architecture;
- a local-model evaluation/training strategy;
- a master validation plan;
- an old-failure regression matrix;
- a full project roadmap;
- a concrete two-day MVP execution plan;
- explicit unresolved decision gates.

The remaining blockers are mostly **experiments**, not missing architecture prose. They should be resolved through small deterministic spikes before broad implementation.

## Strong conclusions considered resolved

- One authoritative `TaskController` should own runtime transitions.
- The LLM chooses intent; deterministic browser/runtime code owns mechanics.
- Browser targets are observation-scoped and stale targets fail closed.
- State-changing intent is persisted before execution.
- Browser/tool success is different from task/postcondition success.
- Verification is independent of model self-assessment.
- Blind retry of an ambiguous state-changing action is forbidden.
- Generic model-controlled refresh/reload is rejected.
- A dedicated Playwright-managed persistent BrowserAgent profile is the MVP default; existing-browser CDP attachment is later/optional.
- Page/tab ownership is assigned at creation/discovery time; only agent-owned pages are auto-closeable.
- Full browsing history is stored as trace, not pushed into Qwen every step.
- Cross-page information is persisted as provenance-bearing facts.
- Page content is untrusted input and cannot grant capabilities or override policy.
- Site-specific workflow architecture is rejected.
- Every real failure becomes a typed classification, reproduction fixture, fix, and permanent regression test.
- SQLite/event sourcing is sufficient for first-version durability; a vector database is not required initially.
- The old BrowserAgent should be mined for tests and small deterministic utilities, not used as the orchestration base.

## Feasibility conclusion from research

The literature does support the project direction, but not a guarantee of arbitrary-site reliability.

### Strongly supported

- compact/pruned observations over raw HTML;
- grounding as a first-class failure source;
- semantic/deterministic browser actions;
- hierarchical subgoal state for compositional work;
- persistent external task memory for long workflows;
- reproducible traces/evaluations;
- a local/open model upgrade path through web-specific training.

### Important newer evidence

- **WebAgent-R1 (2025):** multi-turn RL reports Qwen-2.5-3B improving from 6.1% to 33.9% and Llama-3.1-8B from 8.5% to 44.8% on WebArena-Lite.
- **WEBSERV (2025):** explicitly targets noisy context and non-deterministic browser/UI waiting, supporting the compact-observation + deterministic-kernel architecture.
- **BrowserArena (2025):** live traces show recurring CAPTCHA, popup/banner and navigation brittleness.
- **DynaWeb (2026):** model-based web RL improves open web-agent models and strengthens the value of collecting transition-quality traces.

See:
- `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md`
- `01_RESEARCH/RECENT_2025_2026_WEB_AGENT_RESEARCH.md`
- `01_RESEARCH/MODEL_STRATEGY_AND_TRAINING_PATH.md`

## Actual old-repository audit

`Reshwant-Borra/BrowserAgent` has been inspected directly.

High-value reuse candidates:
- append-only SQLite event-store pattern;
- deterministic loop detectors;
- deterministic verifier boundary;
- persisted-state/token-budgeted context principles;
- model-backend abstraction;
- startup health-check ideas;
- unit/integration/model test fixtures and benchmark fixtures.

Major rewrite candidates:
- ~104 KB `agent/controller.py`;
- ~69 KB `agent/loop.py`;
- browser page-selection/tab heuristics;
- sophisticated memory/orchestration features that are not required by initial V2 gates.

Old tests explicitly cover browser search/type/select/download, tab wiring/CDP binding, contract repair, verification/recovery, crash recovery and long-horizon behavior. V2 now has a regression matrix mapping these behaviors to new architecture invariants.

See:
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`

## Master documents

### Product / evidence
- `00_PROJECT/VISION_AND_SCOPE.md`
- `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md`
- `01_RESEARCH/RECENT_2025_2026_WEB_AGENT_RESEARCH.md`
- `01_RESEARCH/FAILURE_MODES_AND_MITIGATIONS.md`
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `01_RESEARCH/BROWSER_RUNTIME_RESEARCH.md`
- `01_RESEARCH/ECOSYSTEM_AND_BENCHMARKS.md`
- `01_RESEARCH/GROUNDING_AND_CONTEXT.md`
- `01_RESEARCH/QWEN_MODEL_INTERFACE.md`
- `01_RESEARCH/MODEL_STRATEGY_AND_TRAINING_PATH.md`
- `01_RESEARCH/MEMORY_RECOVERY_AND_SECURITY.md`

### Architecture
- `02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md`
- `02_ARCHITECTURE/LONG_RESEARCH_AND_MEMORY_ARCHITECTURE.md`
- `02_ARCHITECTURE/PROPOSED_ARCHITECTURE.md`

### Decisions
- `03_DECISIONS/ARCHITECTURE_DECISIONS.md`
- `06_OPEN_QUESTIONS/DECISION_GATES_V2.md`
- `06_OPEN_QUESTIONS/RESEARCH_GAPS.md`

### Validation
- `04_TESTING/MASTER_VALIDATION_PLAN.md`
- `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`
- `04_TESTING/TEST_STRATEGY_AND_EXIT_GATES.md`

### Build plan
- `05_IMPLEMENTATION/FULL_PROJECT_ROADMAP.md`
- `05_IMPLEMENTATION/TWO_DAY_EXECUTION_PLAN_V3.md`
- `05_IMPLEMENTATION/TWO_DAY_BUILD_PLAN.md`

## Remaining P0 empirical work

1. Run Playwright MCP vs direct Playwright BrowserKernel spike.
2. Freeze exact runtime/browser/MCP versions after the spike.
3. Build 100-300 frozen model-decision cases and compare Qwen interface modes.
4. Determine whether zero-shot Qwen3:8B reaches action-selection threshold; if not, invoke the model-improvement path instead of adding retries.
5. Measure exact observation invalidation rules under SPA churn, frames, tabs, dialogs and manual user action.
6. Demonstrate ambiguous state-changing action reconciliation with crash injection and zero duplicate server-side operations.
7. Repeatedly prove dedicated-profile persistence and page ownership.
8. Run prompt-injection/cross-origin/capability security fixtures.

## Later planned capabilities already designed

- 100+ page research with coverage-based stopping, source dedupe, provenance, contradictions and bounded context;
- download/upload ArtifactStore;
- optional visual fallback;
- connector/API routing when a structured integration is more reliable than UI automation;
- cross-task memory after task-local state is stable;
- supervised/RL/world-model training if model quality becomes the limiting factor;
- UI/productization and Mac/Windows packaging after runtime reliability.

## Architecture freeze definition

Research is complete enough to issue the implementation master prompt when:

1. all P0 experimental gates have recorded results;
2. `END_TO_END_SYSTEM_SPEC.md` matches those results;
3. every component has one clear responsibility and typed interface;
4. failure ownership/recovery is explicit;
5. controlled tests exist for the highest-risk invariants;
6. the two-day implementation steps do not require Codex to invent architecture;
7. no master document contradicts another.

Until then, the repo remains the living source of truth and implementation should proceed only through bounded experiments/gates.
