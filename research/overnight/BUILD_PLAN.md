# BrowserAgentV2 Build Plan

## Rule
Every phase is hypothesis -> smallest implementation -> repeated/adversarial test -> inspect failures -> decide. Do not advance past a failed correctness gate by adding a larger model.

## Phase 1 — Grounding contract
Build `computer_agent/types.py`, minimal `grounding.py`, and pure-Python mutable UI Fixture A. Implement `TargetSpec`, `ObservationVersion`, observation-local candidate/ExecutionRef and pre-dispatch freshness/abstention.

Test >=1,000 seeded replacement/reorder/reflow/duplicate/overlay/hide/absence/ambiguity/mutation trials. Gate: zero wrong-target and zero stale-target dispatch; ambiguous/absent targets abstain. Every failure seed becomes regression coverage.

STOP on any wrong/stale dispatch and repair identity/freshness before continuing.

## Phase 2 — Independent verifier
Build `verification.py` and deceptive Fixture B. Keep predicate vocabulary small and compositional. Inject API-success/no-op, wrong-object, partial, delayed, duplicate and collateral mutations.

Gate: zero false-success classifications across >=1,000 deterministic injected trials. `INCONCLUSIVE` is allowed. Expand verifier vocabulary only if representative postconditions cannot be expressed compositionally.

## Phase 3 — Durable controller + journal + recovery
Build `state.py`, SQLite WAL `journal.py`, minimal `controller.py`, `recovery.py`, crashable Fixture C. Enforce intent-before-dispatch and verifier-before-step-advance. Kill at every durable boundary.

Gate across >=1,000 randomized trials per side-effect class: no unsafe duplicate A-C effects where reconciliation can prevent them; no blind retry of ambiguous class D; no incorrect verified success; deterministic replay reconstructs controller state.

## Phase 4 — Bounded state/context projector
Generate 200/500/1,000-action synthetic trajectories with failures, replans and superseded facts. Implement deterministic materialization/projection and optional FTS retrieval.

Gate: 100% exact reconstruction of correctness-critical deterministic fields at 1,000 actions while active projection remains bounded. Retrieval cannot override authoritative state.

## Phase 5 — Deterministic policy/security
Build `policy.py` and authority-injection Fixture D. Initial capability schema: app/domain, filesystem prefixes, recipient sets, action classes, confirmation requirement and sensitive-read/external-write constraints.

Gate: zero authority expansion from untrusted content in deterministic tests.

## Phase 6 — Model proposal adapter
Only now integrate a typed replaceable proposal interface. Benchmark Qwen3-VL-8B-Instruct first on M5 24 GB and RTX 4070 12 GB. Measure schema validity, semantic target proposals, abstention, semantic-gap grounding, p50/p95 latency, memory, cold start and repeated variance.

Add UI-TARS-2B/ZonUI-3B/UGround-V1-2B only as challengers on semantic-gap cases. Keep a specialist only for material verifier-confirmed gain. Do not add an always-on critic.

## Phase 7 — Versioned skills
Implement metadata-first skill registry/loader with typed inputs, capabilities, preconditions, verifier/invariants and regression fixtures. Test 10 real + 100 decoy skills.

Gate: no capability widening; bounded context growth; schema-filtered progressive disclosure matches/exceeds full-injection reliability while reducing prompt size.

## Phase 8 — Real platform adapters
Preserve Playwright/CDP as browser semantic route. Integrate macOS AX behind measured capability metadata. Build/test Windows UIA adapter on target hardware across Win32, WPF/WinUI, Electron, Chrome/Edge and custom surfaces. Never infer background safety from UIA availability.

## Phase 9 — Visual fallback
Integrate visual grounding only for semantic gaps. Reuse the same TargetSpec/freshness/verification contracts. Wrong-target and abstention metrics dominate raw benchmark accuracy.

## Phase 10 — Endurance and external benchmarks
Run atomic, 5-20, 20-100, 150+, and 500+ action campaigns with injected popup/focus/restart/session/staleness/malformed-output/user-interruption faults. Report distributions and failure taxonomy. Only then map representative OSWorld/WindowsWorld/web tasks for comparability.

## Single next engineering task
Implement **Fixture A only** plus the minimal `TargetSpec` / `ObservationVersion` / candidate / freshness contract and `tests/computer_agent/test_grounding_freshness.py`. Run >=1,000 seeded mutation trials. Do not integrate an LLM until this gate passes.