# BrowserAgentV2 Overnight Research Index

**Branch:** `research/overnight-2026-09-18`
**Mission date:** September 17-18, 2026 ET
**Final target:** one evidence-backed, buildable BrowserAgentV2 architecture and exact implementation sequence.

## Core State
- [MASTER_RESEARCH_MISSION.md](./MASTER_RESEARCH_MISSION.md) — authoritative mission/rules for every scheduled run.
- [RESEARCH_LEDGER.md](./RESEARCH_LEDGER.md) — persistent cross-run evidence and handoff state.

## Expected Research Outputs
The scheduled runs should create/update the following as evidence accumulates:

- CURRENT_SYSTEM_AUDIT.md
- RELATED_SYSTEMS.md
- PAPERS.md
- COMPUTER_CONTROL.md
- GROUNDING.md
- ACTION_VERIFICATION.md
- FAILURE_ANALYSIS.md
- LONG_HORIZON_RELIABILITY.md
- MEMORY_AND_CONTEXT.md
- LOCAL_MODEL_OPTIMIZATION.md
- SKILL_SYSTEM.md
- RECOVERY.md
- SECURITY.md
- BENCHMARKS.md
- RELIABILITY.md
- ARCHITECTURE_DECISIONS.md
- FINAL_ARCHITECTURE.md
- BUILD_PLAN.md
- VALIDATION_PLAN.md
- DO_NOT_BUILD.md
- OPEN_QUESTIONS.md
- FINAL_RESEARCH_REPORT.md

## Run Protocol
Each run must:
1. Read MASTER_RESEARCH_MISSION.md and RESEARCH_LEDGER.md.
2. Inspect existing outputs and recent commits on this branch.
3. Work on the highest-value unresolved architecture questions rather than restarting.
4. Update evidence, ADRs, open questions, and the handoff section.
5. Commit research artifacts to this branch.
6. During the final morning run, stop broad research and produce the final synthesis/report.
