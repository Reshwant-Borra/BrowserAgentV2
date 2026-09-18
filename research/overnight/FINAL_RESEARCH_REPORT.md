READY_TO_BUILD

# BrowserAgentV2 Final Research Report

## Meaning of the verdict
BrowserAgentV2 is ready to begin the specified falsification-first implementation. This is **not** a claim that the agent is production-ready. The P0 correctness fixtures and hardware benchmarks are specified but not yet executed. No known contradiction currently requires another broad architecture redesign before coding begins.

## Recommended architecture
Build a durable deterministic ComputerAgent controller. Prefer deterministic APIs/tools, then Playwright/CDP, then AX/UIA, then visual grounding/input, then explicit foreground/handoff. Persist semantic target intent rather than backend handles. Re-resolve against fresh observations. Persist logical action intent before consequential dispatch. Independently observe and verify semantic postconditions plus safety invariants before committing success or advancing a step. Keep Goal/Plan/Action/Recovery state and event history outside the model. Give models bounded state projections and proposal-only authority. Enforce task-scoped capabilities deterministically. Reconcile uncertain external effects after crashes rather than blindly retrying.

## Why this architecture survived the red team
The candidate architecture has explicit safe behavior for the major failure classes identified overnight:
- dynamic/replaced UI: observation-local target refs + freshness gate
- duplicate/ambiguous controls: abstention, not guessing
- API false success: independent verifier
- wrong-but-successful mutation: success predicates + safety invariants
- crash after external effect: durable intent + reconciliation/action class
- non-queryable irreversible ambiguity: OUTCOME_UNKNOWN/NEEDS_REVIEW
- prompt injection: information cannot increase authority
- long trajectories: structured durable state + bounded projection
- weak semantic surfaces: visual fallback behind same verification contract
- model failure/malformed output: bounded proposal interface, deterministic controller state
- telemetry failure: no effect on recovery truth
- route/app quirks: measured capability matrix rather than universal promises

The remaining uncertainty is primarily whether implementations satisfy these contracts, not what the contracts should be.

## Architecture-changing discoveries
1. Existing BrowserAgentV2 Phase 0 measurement infrastructure is more valuable than replacing it with an agent framework. Browser semantic campaigns and AX campaigns provide direct repeated-trial evidence.
2. Chrome AXPress produced an API-success/page-no-op case. This makes independent postcondition verification non-negotiable and rejects browser-through-AX as the primary route.
3. Backend element identity is too ephemeral for a durable UniversalElement. Semantic TargetSpec + fresh observation-local resolution is the safer abstraction.
4. Post-action verification alone cannot prevent an irreversible wrong-target action; consequential actions need a pre-dispatch freshness gate.
5. Long-horizon memory and recovery are different problems. Authoritative execution state must remain structured/durable; retrieval is advisory.
6. Checkpointing cannot provide generic exactly-once external effects. Recovery needs idempotency/reconciliation and an explicit outcome-unknown state.
7. Prompt-injection resistance is not an authorization system. Authority and information must be separated by deterministic policy.
8. Multi-agent planner/executor/recovery decomposition is unnecessary for v1. A single durable controller produces clearer ownership and recovery semantics.
9. A permanent local model ensemble is premature. Semantic-first execution reduces the need for an always-resident GUI specialist.
10. External benchmark score is a late metric. Wrong-target, verifier false-success and unsafe recovery must be falsified first.

## Assumptions rejected
Rejected: pixel-only universality; AX/UIA availability implies behavioral/background reliability; durable semantic handles; screenshot difference equals success; full transcript as memory; vector retrieval as execution truth; checkpoint-after-step equals exactly once; blind retry after ambiguous side effects; prompt-injection classifier as root defense; autonomous multi-agent hierarchy; always-on model ensemble; maximum context as memory target; auto-promoted trajectory skills; OpenTelemetry as recovery store; Phase 0 ExperimentRunner as production runtime; external benchmark optimization before deterministic contract validation.

## Existing BrowserAgentV2 components to keep
- Phase 0 ExperimentRunner / ActionSpec execution-vs-verification discipline
- machine-readable evidence and human-readable reports
- repeated-trial campaign methodology and failure conversion to regressions
- Playwright/CDP semantic browser control
- bounded macOS AX discovery/observation helpers
- non-interference/focus/cursor measurement discipline, with hardening
- typed classification/evidence patterns
- stale-element failure handling

## Components to replace, remove or isolate
- Do not use browser AX as primary browser action route.
- Do not use physical mouse/keyboard as default execution.
- Do not create a durable UniversalElement.
- Do not use Graphify/vector memory as runtime truth.
- Do not turn Phase 0 JSONL into the transactional journal.
- Do not grow ExperimentRunner into the production controller.
- Do not freeze Qwen3-VL, a visual specialist, critic or multi-agent framework before measurements.

## Final production-shaped core
`computer_agent/types.py`
`computer_agent/state.py`
`computer_agent/journal.py`
`computer_agent/grounding.py`
`computer_agent/verification.py`
`computer_agent/policy.py`
`computer_agent/controller.py`
`computer_agent/recovery.py`

Adapters/models/skills plug into this core without owning authority or durable truth.

## Ranked risks
### 1. Grounding freshness contract — P0
Specified, not executed. Any wrong/stale dispatch in the controlled fixture blocks consequential GUI actions.

### 2. Verifier false-success resistance — P0
Specified, not executed. A false success is more dangerous than an inconclusive result because it corrupts durable task state.

### 3. Crash reconciliation — P0
Specified, not executed. Production side effects remain unsafe until kill-point tests demonstrate correct reconciliation.

### 4. Bounded 1,000-action state reconstruction — P1
Architecture is strong conceptually but must prove exact deterministic reconstruction while prompt projection stays bounded.

### 5. Local model quality/performance — P1
Qwen3-VL-8B may fail latency, memory, schema or grounding gates on M5 24 GB / RTX 4070 12 GB. This should require model replacement, not controller redesign.

### 6. Windows UIA capability — P1
No equivalent target-hardware campaign has been executed. Failures should downgrade route capability and use fallback rather than invalidate the whole architecture.

### 7. Visual fallback quality — P2
Specialist value remains unmeasured. It is intentionally optional.

### 8. Skill routing/progressive disclosure — P2
Useful but not required for the first reliable vertical slice.

## Overall confidence
**92% confidence in the architecture direction.**

Confidence is lower than production confidence because V1-V8 have not run. The architecture has been deliberately designed so the remaining P1 model/platform uncertainty sits behind replaceable interfaces rather than forcing a rewrite.

## Exact build sequence
1. Fixture A + TargetSpec/ObservationVersion/candidate/freshness contract.
2. Fixture B + typed independent verifier.
3. SQLite journal + durable controller + crash/reconciliation Fixture C.
4. 200/500/1,000-action deterministic state projector benchmark.
5. Deterministic capability/security Fixture D.
6. Typed model proposal adapter; benchmark Qwen3-VL-8B on both target machines.
7. Add visual specialist only if semantic-gap measurements justify it.
8. Add versioned progressive-disclosure skill system.
9. Integrate/measure macOS AX and Windows UIA capability routes.
10. Run cross-app endurance/fault campaigns, then representative external benchmarks.

## Release gates before expansion
- zero wrong/stale dispatch in >=1,000 deterministic grounding fault trials
- zero verifier false success in >=1,000 deterministic injected-fault trials
- no blind retry of ambiguous non-idempotent effects and no incorrect verified success in crash matrix
- exact correctness-critical reconstruction at 1,000 actions with bounded active projection
- zero deterministic authority expansion from untrusted content
- acceptable model schema/latency/memory on target hardware or replacement behind same interface
- measured Windows capability matrix

## Single next engineering task
Implement only **Fixture A** and the minimal target freshness contract: `TargetSpec`, `ObservationVersion`, `TargetCandidate`, observation-local `ExecutionRef`, resolver outcomes, and pre-dispatch freshness/abstention. Add `tests/computer_agent/test_grounding_freshness.py`. Run at least 1,000 deterministic seeded mutation trials across replacement, reorder, duplicate labels, overlays, hidden/disabled targets, absence, ambiguity and mutation between resolution and dispatch. Require zero wrong-target and zero stale-target dispatches. Convert every failing seed into a permanent regression.

Do **not** integrate an LLM before this passes. This is the cheapest experiment capable of disproving the core target/control contract; if it fails, repair that contract before investing in models, skills, Windows work or benchmarks.