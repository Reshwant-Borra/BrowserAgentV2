# Research Status

**Snapshot date:** 2026-09-15

## Current state

Research is **substantially expanded but still active**. We now have a top-to-bottom target architecture, a comprehensive failure catalog, an audit of the actual old BrowserAgent codebase, deterministic validation gates, a full multi-phase project roadmap, and a concrete two-day execution plan.

The project is not yet at final architecture freeze because several P0 choices require experiments rather than more paper research alone.

## Strong conclusions now considered resolved

- One authoritative `TaskController` should own runtime transitions.
- The LLM chooses intent; deterministic browser/runtime code owns mechanics.
- Browser targets must be observation-scoped and stale targets fail closed.
- State-changing intent is persisted before execution.
- Browser/tool success is different from task/postcondition success.
- Verification must be independent of the model's self-assessment.
- Blind retry of an ambiguous state-changing action is forbidden.
- Generic model-controlled refresh/reload is rejected.
- A dedicated Playwright-managed persistent BrowserAgent profile is the MVP default; existing-browser CDP attachment is a later optional mode.
- Page/tab ownership must be assigned at creation/discovery time; only agent-owned pages are auto-closeable.
- Full browsing history is stored as trace, not pushed into Qwen every step.
- Cross-page information is persisted as provenance-bearing facts.
- Page content is untrusted input and cannot grant capabilities or override policy.
- Site-specific workflow architecture is rejected.
- Every real failure should become a typed classification, reproduction fixture, fix, and permanent regression test.
- SQLite/event sourcing is sufficient for first-version durability; a vector database is not required initially.
- The old BrowserAgent should be mined for tests and small deterministic utilities, not used as the orchestration base.

## Evidence-backed feasibility conclusion

Research from Mind2Web, WebArena, SeeAct, WebVoyager, Agent-E, AgentOccam, WebLINX, BrowserGym/AgentLab, AssistantBench, WorkArena++, WebRL, Online-Mind2Web, WebChoreArena and related work supports the overall architecture direction:

- compact/pruned observations matter;
- grounding is a separate major source of failure;
- simple observation/action contracts can outperform unnecessary agent-system complexity;
- hierarchical subgoal reasoning helps compositional tasks;
- long research requires persistent memory/provenance outside the prompt;
- live websites introduce drift/auth/CAPTCHA failures that controlled benchmarks hide;
- open 8–9B models can become much stronger web agents with web-specific training.

The evidence does **not** prove that zero-shot Qwen3:8B will meet our target. That is an explicit model-evaluation gate.

## Actual old-repository audit

`Reshwant-Borra/BrowserAgent` has now been inspected directly.

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

See `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`.

## Master documents now present

### Evidence / risks
- `01_RESEARCH/PAPER_EVIDENCE_AND_FEASIBILITY.md`
- `01_RESEARCH/FAILURE_MODES_AND_MITIGATIONS.md`
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `01_RESEARCH/BROWSER_RUNTIME_RESEARCH.md`
- `01_RESEARCH/ECOSYSTEM_AND_BENCHMARKS.md`
- `01_RESEARCH/GROUNDING_AND_CONTEXT.md`
- `01_RESEARCH/QWEN_MODEL_INTERFACE.md`
- `01_RESEARCH/MEMORY_RECOVERY_AND_SECURITY.md`

### Architecture
- `02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md`
- `02_ARCHITECTURE/PROPOSED_ARCHITECTURE.md`

### Decisions
- `03_DECISIONS/ARCHITECTURE_DECISIONS.md`
- `06_OPEN_QUESTIONS/DECISION_GATES_V2.md`
- `06_OPEN_QUESTIONS/RESEARCH_GAPS.md`

### Validation
- `04_TESTING/MASTER_VALIDATION_PLAN.md`
- `04_TESTING/TEST_STRATEGY_AND_EXIT_GATES.md`

### Build plan
- `05_IMPLEMENTATION/FULL_PROJECT_ROADMAP.md`
- `05_IMPLEMENTATION/TWO_DAY_EXECUTION_PLAN_V3.md`
- `05_IMPLEMENTATION/TWO_DAY_BUILD_PLAN.md`

## Remaining P0 empirical work

1. Run Playwright MCP vs direct Playwright kernel spike.
2. Freeze exact runtime/browser/MCP versions after the spike.
3. Build 100-300 frozen model-decision cases and compare Qwen interface modes.
4. Determine whether Qwen3:8B reaches action-selection threshold; if not, invoke model-upgrade path instead of adding retries.
5. Measure exact observation invalidation rules under SPA churn, frames, tabs, dialogs and manual user action.
6. Demonstrate ambiguous state-changing action reconciliation with crash injection.
7. Repeatedly prove dedicated-profile persistence and page ownership.
8. Run prompt-injection/cross-origin/capability security fixtures.

## Remaining research/design expansions

- detailed long-research/100+ page architecture and completeness rules;
- precise source/fact deduplication and contradiction semantics;
- model-training data/trajectory collection strategy if Qwen is limiting;
- optional visual fallback trigger/contract;
- connector/API routing design after browser kernel is proven;
- distribution/packaging and telemetry/privacy policies after core runtime stabilizes.

## Architecture freeze definition

Research is complete enough to build when:

1. all P0 experimental gates have recorded results;
2. `END_TO_END_SYSTEM_SPEC.md` matches those results;
3. every component has one clear responsibility and typed interface;
4. failure ownership/recovery is explicit;
5. controlled tests exist for the highest-risk invariants;
6. the two-day implementation steps do not require Codex to invent architecture;
7. no master document contradicts another.

Until then, this repository remains the living source of truth and implementation should proceed only through bounded experiments/gates.
