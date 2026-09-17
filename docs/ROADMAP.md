# ComputerAgent Roadmap

ComputerAgent uses **three main phases**. Workstreams and builds inside a phase are milestones, not new phases.

## Phase 0 — Prove the foundations

**Goal:** replace architectural assumptions with measured evidence.

Build:
- HardwareProfiler
- browser non-interference harness
- macOS AX capability harness
- Windows UIA capability harness
- model/runtime benchmark harness
- visual grounding benchmark
- long-horizon bounded-context benchmark
- crash/side-effect reconciliation tests
- security/handoff tests
- BrowserAgentV2 historical regression fixtures

Deliverables:
- repeatable benchmark/capability harness
- machine-readable evidence artifacts
- hardware/capability matrix
- measured model/runtime profiles
- updated `BUILD_SPEC.md`
- updated `DECISIONS.md`
- evidence-backed architecture freeze for Phase 1

Do not spend Phase 0 building product polish.

## Phase 1 — Build ComputerAgent

**Goal:** implement the production local agent engine around Phase 0 evidence.

Build/integrate:
- TaskController
- GoalState / PlanState
- EventStore / FactStore / ArtifactStore / RecoveryState
- bounded ContextBuilder
- PolicyEngine
- HardwareProfiler + InferenceProfileManager
- swappable ModelAdapter
- InteractionRouter
- BrowserAdapter
- macOS AccessibilityAdapter
- Windows UIAAdapter
- VisionAdapter
- capability-gated IsolatedDesktopProvider
- PermissionBroker
- Verifier
- reconciliation/recovery
- human handoff
- progress/loop/uncertainty detection

Validation progression:
- unit/kernel fixtures
- historical BrowserAgent regressions
- controlled browser/accessibility fixtures
- grounding benchmarks
- realistic browser benchmarks
- desktop benchmark subset
- security suite
- 500–1,000 action endurance runs
- selected live-site/application drift tests

Phase 1 exit condition: ComputerAgent can reliably execute broad multi-step tasks within measured capability boundaries, survive long runs/restarts, and correctly hand off when it cannot safely proceed.

## Phase 2 — Ship the consumer product

**Goal:** make ComputerAgent installable and understandable for ordinary users.

Build:
- polished task/chat UI
- onboarding and permission flows
- Agent Cursor visualization
- task progress/handoff/recovery UI
- automatic hardware calibration/profile selection
- model download/management
- signed/notarized macOS distribution
- signed Windows installer
- update and rollback system
- diagnostics/support bundle with privacy controls
- product telemetry only where explicitly designed/consented

Phase 2 exit condition: a new user can install ComputerAgent, grant required permissions, run supported tasks, understand when the agent is acting or needs help, and update/recover safely.

## Later research — not a fourth required build phase

After the product works, investigate optional improvements such as trajectory learning, fine-tuning/distillation/RL, stronger local planners, more advanced retrieval, Linux support, and occasional slow large-model escalation. These should improve a working architecture rather than delay it.
