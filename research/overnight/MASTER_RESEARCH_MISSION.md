# BrowserAgentV2 Overnight Research Mission

## Mission
Research BrowserAgentV2 from approximately midnight ET through the morning of September 18, 2026 and converge on one buildable architecture for a universal computer agent. The purpose is not to maximize report length. The purpose is to eliminate enough architectural uncertainty that implementation becomes a sequence of small, measurable engineering problems rather than repeated speculative rewrites.

## Central Question
If BrowserAgentV2 were rebuilt tomorrow, what exact architecture should be built, in what order, and why should we believe it will work?

Do not finish with a menu of possibilities. Select one coherent architecture. Alternatives may be documented, but final decisions must converge.

## Research Loop
RESEARCH -> COMPARE -> FALSIFY -> PROTOTYPE -> MEASURE -> DECIDE

Prefer simple + measurable + recoverable over clever + complicated + theoretically elegant.

## Existing-System Audit First
Inspect the actual BrowserAgentV2 implementation before proposing replacement architecture. Study directory structure, execution loop, browser abstraction, Playwright/CDP integration, observation generation, model interface, prompts, tool schemas, state representation, memory, tab ownership, retries, verification, recovery, crash/resume, security/scope controls, batch orchestration, tests, benchmarks, experiments, macOS/accessibility work, documentation, abandoned approaches, TODOs, and known failures. Use git history and issues when useful. Classify each major component KEEP / MODIFY / REPLACE / REMOVE / UNKNOWN-NEEDS-TESTING.

## Research Areas
Investigate the strongest current work and source code related to computer-use agents, browser agents, GUI agents, OS agents, multimodal grounding, accessibility/DOM/vision control, local models, routing, long-horizon reliability, crash recovery, memory/context compression, safety, prompt injection, skills, verification, benchmarks, and testing.

At minimum consider relevant systems/projects such as OpenAI computer-use systems, Anthropic computer use, Google/Microsoft/Apple work where relevant, Browser Use, OpenHands, Open Interpreter, AutoGen, Magentic-One, Agent-S, UFO, OSWorld agents, UI-TARS, OmniParser, SeeAct, WebVoyager, ShowUI, CogAgent, AppAgent, Mobile-Agent, BrowserGym, WebArena, VisualWebArena, WorkArena, AgentTrek, Mind2Web-based work, and newer systems that supersede them.

For important open-source systems inspect actual source code, prompts, schemas, action systems, perception, grounding, memory, retries, browser/computer-control code, tests, and issue trackers. Prefer failure reports over demos.

## Highest-Priority Architecture Questions
1. Universal control stack: when to use native APIs, DOM/CDP, browser accessibility, macOS AX, vision, OCR, and raw coordinates.
2. Grounding: how instructions map to stable semantic/physical targets; stale target detection; confidence; unified element representation if justified.
3. Action verification: preconditions, postconditions, deterministic verification, screenshot/DOM/AX deltas, semantic success predicates, retries/fallbacks/replanning.
4. Long-horizon reliability: explicit state, subgoals, invariants, bounded retries, checkpoints, watchdogs, replanning, state drift prevention.
5. Memory/context: working/task/episodic/semantic/procedural memory; SQLite/FTS5/embeddings only when justified; aggressive observation pruning and compact state deltas for local models.
6. Local-model architecture: whether one ~8B model is enough; planner/grounder/verifier/router split; multimodal/UI models; quantization; inference on Apple Silicon 24 GB and RTX 4070 12 GB.
7. Routing and skills: deterministic execution for known skills; confidence-based escalation; primitive actions vs reusable skills.
8. Planning: ReAct vs planner/executor/verifier vs hierarchical planning/FSM/behavior trees/HTN/DAG/deterministic workflows depending on task complexity.
9. Crash recovery: action journal, checkpoints, browser/app rediscovery, duplicate-action avoidance, idempotency, side-effect tracking.
10. Security: indirect prompt injection, untrusted web/document content, credentials/secrets, destructive actions, filesystem boundaries, capability security, scope guards, confirmations, audit logs.
11. Benchmarking/testing: external benchmarks plus BrowserAgentV2-specific atomic, short, medium, long, cross-app, adversarial, and recovery tasks with repeated trials and regression tests.
12. Observability: structured traces for each step including task/subgoal/observation/target/confidence/action/expected result/actual result/verification/retry/fallback/model/tokens/latency/screenshot/DOM-or-AX references.

## Evidence Hierarchy
5 = direct BrowserAgentV2 experiment
4 = source-code evidence or reproducible external experiment
3 = peer-reviewed paper or strong technical report
2 = maintainer documentation
1 = blog/discussion/anecdote

Architecture-changing claims should preferably have Level 3-5 evidence.

## Source Discipline
For important claims record source, question, finding, evidence quality, architecture impact, and follow-up. Prefer primary sources, source code over marketing, experiments over speculation, recent work for current state of the art, and foundational older work only when still architecturally relevant. Follow citations when they could change architecture. Stop duplicate research once strong sources converge and no material contradiction remains.

## Prototype Uncertain Assumptions
When a decision can be tested cheaply, test it. Examples: AX click behavior in Chrome/Safari/Electron, AX value writes, typical AX tree size/compression, local-model element selection, DOM-first vs screenshot-first, browser-state reconstruction after restart, stable element IDs, 8B structured-output reliability. Record hypothesis, method, result, conclusion.

## Architecture Decision Records
For every major decision record:
DECISION
CONFIDENCE (%)
EVIDENCE
ALTERNATIVES
WHY REJECTED
RISKS
HOW TO VALIDATE

Do not inflate confidence.

## Persistent Files
Maintain and update these when applicable:
- RESEARCH_INDEX.md
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
- RESEARCH_LEDGER.md
- FINAL_RESEARCH_REPORT.md

## Build-Plan Rule
Avoid large speculative implementation. Before every major phase: state hypothesis -> build smallest implementation -> test -> inspect failures -> decide whether architecture remains valid -> only then expand. Every phase must be testable and include goal, why now, files/components, implementation, tests, pass criteria, dependencies, and stop conditions.

## Red-Team Scenarios
Attack the proposed architecture with UI changes, failed/no-op clicks, stale DOM nodes, canvas UIs, weak Electron accessibility, focus-stealing popups, browser/agent crashes, machine sleep, malformed JSON, repeated failed actions, prompt injection, many pre-existing tabs, many agent-created tabs, slow downloads, expired login, 2FA, unresponsive apps, 150+ action contexts, task drift, user interruption, and irreversible actions.

## Final Convergence
During the final morning pass, stop broad discovery. Review evidence, code, experiments, ADRs, and open questions. Try to falsify the candidate architecture. Remove unnecessary complexity. Ensure the architecture fits local hardware, supports browser + native apps, can recover, can be benchmarked, and has a fast first useful vertical slice.

## Final Report
FINAL_RESEARCH_REPORT.md must start with one verdict:
READY_TO_BUILD
READY_WITH_BLOCKERS
NOT_READY

Then include exact recommended architecture, architecture-changing discoveries, previous assumptions proven wrong, current BrowserAgentV2 code that survives, code/components to replace/remove, ranked risks, overall confidence, exact build sequence, and the single next engineering task small enough to implement/test without another architectural redesign.
