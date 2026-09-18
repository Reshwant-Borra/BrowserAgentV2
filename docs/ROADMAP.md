# ComputerAgent Roadmap

ComputerAgent uses **three main phases**. Workstreams and builds inside a phase are milestones, not new phases. Phase 1 is broken into milestones M1-M10 in `docs/IMPLEMENTATION_PLAN.md`; Phase 2 is M11.

## Status legend

Every capability claim below carries one of these tags. Do not use a checkmark for a claim that has not passed an implementation/measurement gate.

- **PROVEN** — passed its measurement gate with no known contradicting evidence.
- **MEASURED BUT LIMITED** — real measurement exists, but it is scoped (single machine, small sample, specific apps/routes) and must not be generalized past that scope.
- **PLANNED** — a contract/design exists (often from the overnight research reconciliation, `docs/DECISIONS.md` D-017 onward) but nothing has been implemented or run yet.
- **UNVALIDATED** — depends on a future benchmark whose outcome is genuinely unknown (e.g. local model quality on target hardware).
- **BLOCKED** — cannot be measured yet because a prerequisite (usually target hardware) is unavailable.
- **NOT PROVEN / rejected as a universal assumption** — evidence exists but explicitly does not support the broader claim some might infer from it.

Representative current tags (see `docs/BUILD_SPEC.md` for the underlying evidence/gates):
- Browser semantic non-interference (Playwright/CDP, this machine): **MEASURED BUT LIMITED** — 500/500 verified postconditions, zero cursor/foreground interference, but the browser-focus-theft signal itself was unmeasurable on 93% of trials (`phase0/CAMPAIGN_REPORT.md`).
- macOS AX discovery/read across representative apps: **MEASURED BUT LIMITED** — broad across 8 apps; verified action/mutation only for the Cocoa fixture (`phase0/MAC_APP_CAPABILITY_REPORT.md`).
- Universal/arbitrary macOS AX action control: **NOT PROVEN / rejected as a universal assumption** — Chrome's `AXPress` returns success without effect; both browsers' `AXValue` writes are ordering-sensitive.
- Grounding freshness contract (`TargetSpec`/`TargetCandidate`/`ExecutionRef`): **PLANNED**, awaiting M1/Fixture A.
- Independent verifier contract: **PLANNED**, awaiting M2/Fixture B.
- Crash-safe reconciliation: **PLANNED**, awaiting M3/Fixture C.
- Bounded long-horizon context: **PLANNED**, awaiting M4.
- Deterministic policy/authority gate: **PLANNED**, awaiting M5/Fixture D.
- Local model quality (any candidate, any target machine): **UNVALIDATED**.
- Windows UIA capability: **BLOCKED** — no target Windows hardware campaign has run yet.

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

Exact milestone sequence, gates, and falsification order: `docs/IMPLEMENTATION_PLAN.md` (M1 grounding/freshness -> M2 verifier -> M3 durable controller/recovery -> M4 bounded state -> M5 policy -> M6 model benchmark -> M7 real adapters -> M8 visual fallback -> M9 skills -> M10 endurance). Falsifiable gates for M1-M6 are in `docs/BUILD_SPEC.md`. This order deliberately proves deterministic controller contracts (all **PLANNED**, per the status legend above) before adding model autonomy, real adapters, or endurance testing — a strong model must not be allowed to mask a broken grounding/verification/recovery contract.

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
