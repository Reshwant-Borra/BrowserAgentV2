# Architecture Decision Gates V2

**Purpose:** distinguish decisions that are already research-backed from decisions that still require a BrowserAgentV2 experiment. No implementation prompt may silently choose an unresolved P0 item.

## Status vocabulary

```text
RESOLVED       — architecture decision can be implemented
PROVISIONAL    — strongest current choice; confirm during specified test
OPEN           — experiment required before implementation freeze
DEFERRED       — intentionally outside current MVP
REJECTED       — do not implement without a new ADR backed by evidence
```

---

# P0 — resolved by the experiment campaign

All nine P0 gates were resolved empirically on branch
`experiment/p0-gate-campaign`. Index:
[`../experiments/P0_EXPERIMENT_INDEX.md`](../experiments/P0_EXPERIMENT_INDEX.md).
Environment: [`../experiments/ENVIRONMENT.md`](../experiments/ENVIRONMENT.md).

| Gate | Status | Verdict | Evidence |
|---|---|---|---|
| Browser kernel: MCP vs direct Playwright | **RESOLVED** | `ADOPT_DIRECT_PLAYWRIGHT` | [E1](../experiments/browser_kernel/REPORT.md) — 105/105 vs 90/105, 0 unsafe either side |
| Observation invalidation | **RESOLVED** | `INVALIDATION_RESOLVED` | [E4](../experiments/observation_invalidation/REPORT.md) — 0 wrong-target in 336 safe-policy runs; unsafe control produced 84 |
| Tab ownership / page registry | **RESOLVED** | `PAGE_REGISTRY_RESOLVED` | [E5](../experiments/page_registry/REPORT.md) — 220/220, 0 user tabs closed |
| Ambiguous side-effect protocol | **RESOLVED** | `SIDE_EFFECT_RECOVERY_RESOLVED` | [E6](../experiments/side_effect_recovery/REPORT.md) — 32 crashes, 0 duplicates; blind-replay control produced 20 |
| Human handoff / resume | **RESOLVED** | `HANDOFF_RESOLVED` | [E7](../experiments/human_handoff/REPORT.md) — 90/90, 0 stale targets trusted |
| Browser profile strategy | **RESOLVED** | `DEDICATED_PROFILE_RESOLVED` | [Profile](../experiments/profile_strategy/REPORT.md) — 36/36 persistence and isolation |
| Policy / security boundary | **RESOLVED** | `POLICY_BOUNDARY_RESOLVED` | [E8](../experiments/security_policy/REPORT.md) — 272 probes, 0 bypasses, 0 false blocks |
| Qwen output interface | **RESOLVED** | `ADOPT_STRICT_JSON` | [E2](../experiments/qwen_decision_interface/REPORT.md) — quality tie; decided on 100% schema validity, 100% determinism, 5.4× latency |
| Qwen3:8B adequacy | **RESOLVED (negative)** | `QWEN3_8B_INADEQUATE` | [E3](../experiments/qwen_adequacy/REPORT.md) — misses the pre-registered bar; see constraint below |

## The one gate that resolved negatively

`QWEN3_8B_INADEQUATE` is a resolved gate, not an open one: we know the answer.
It does not block the architecture freeze, because
[ADR-004](../03_DECISIONS/ARCHITECTURE_DECISIONS.md) already requires that the
architecture not assume a particular model intelligence level. It does bind the
implementation:

```text
Qwen3:8B is the first decision SOURCE, not an autonomous POLICY.
```

Mandatory before any autonomous run:

1. The **Verifier** must exist. [E3's containment analysis](../experiments/qwen_adequacy/results/containment_analysis.json)
   shows the PolicyEngine catches 8 of 14 forbidden decisions and that the 3
   escapes are the model clicking a legitimate control for the wrong reason —
   exactly the class deterministic postcondition checking is for.
2. The **table-row context** representation defect must be fixed and the model
   re-measured on a new held-out version.
3. Re-run [`ADEQUACY_THRESHOLD.md`](../experiments/qwen_adequacy/ADEQUACY_THRESHOLD.md)
   after both. Autonomy is licensed by `QWEN3_8B_ADEQUATE`, not by a demo.

---

# P1 — Can be finalized during the first implementation spike

## File download semantics — PROVISIONAL

Choice:
- browser runtime writes temporary download;
- ArtifactStore explicitly saves/copies into `runtime/<task_id>/artifacts`;
- store hash, provenance, filename, source URL;
- sanitize paths/filenames.

Test before enabling broadly:
- collisions;
- interrupted download;
- context closure;
- malicious filename.

## Upload semantics — PROVISIONAL

Choice:
- model can reference only explicit `artifact_id` objects available to the task;
- no arbitrary filesystem path parameter in `Decision`;
- unexpected/sensitive uploads require confirmation.

## Iframe target identity — PROVISIONAL

Choice:
- frame scope is part of target ID;
- detached/reloaded frame invalidates target.

Confirm against same-origin and cross-origin iframe fixtures.

## Dialog handling — PROVISIONAL

Choice:
- dialog is explicit BrowserKernel state;
- unresolved dialog blocks normal page actions;
- consequential confirm/prompt goes through policy/user as needed.

## Progress/loop detector — PROVISIONAL

Signals:
- repeated semantic action;
- repeated observation/no useful change;
- A/B URL oscillation;
- repeated failed postcondition;
- no new fact/subgoal progress.

Loop detector emits evidence; controller decides replan/fail.

## Change summaries — PROVISIONAL

Store full observations in trace but feed the model bounded change information when possible.

Confirm that change summarization never hides newly actionable elements needed for controlled tasks.

---

# Resolved architectural decisions

## One authoritative controller — RESOLVED

Do not recreate separate overlapping `controller.py` + autonomous `loop.py` architectures.

## Deterministic browser mechanics — RESOLVED

The model selects intent; runtime performs browser mechanics and validates targets/actionability.

## Observation-scoped targets — RESOLVED

No long-lived browser handles/refs across incompatible page state.

## No generic model-controlled refresh — RESOLVED

Refresh is not a recovery primitive available to the model. A very specific deterministic feature may later use reload if a documented workflow requires it, but it cannot be a generic escape hatch.

## No blind retry of state-changing operations — RESOLVED

Ambiguous outcomes must be reconciled first.

## Append-only event trace + rebuildable state — RESOLVED

Old repo provides positive implementation evidence; use SQLite initially.

## Model does not self-verify actions — RESOLVED

Verification is a separate deterministic/controller-owned boundary.

## Bounded context instead of full history — RESOLVED

Canonical task state + relevant facts + current observation; full event trace remains outside prompt.

## Page content is untrusted — RESOLVED

Page content may supply facts but cannot change authorization/tool policy.

## Structured facts with provenance — RESOLVED

Needed for cross-page and later long-research tasks.

## No site-specific workflow architecture — RESOLVED

New site failures must map to general primitives/contracts or be declared unsupported.

---

# Rejected for MVP

## Arbitrary shell/code tool available to webpage agent — REJECTED

Creates unnecessary capability and prompt-injection exposure.

## Arbitrary JavaScript evaluation as normal model action — REJECTED

Can bypass semantic/actionability safety and is unnecessary for most workflows.

## Multi-agent planner/executor/verifier team — REJECTED FOR MVP

Research does not establish that this complexity is needed. One controller/model plus deterministic components is easier to debug and AgentOccam provides evidence that carefully aligned simple action/observation designs can be strong.

## Vector database from day one — REJECTED

SQLite structured facts + FTS are sufficient until measured retrieval failures justify embeddings.

## Existing daily-driver Chrome via CDP as default — REJECTED FOR MVP

Dedicated managed profile has clearer lifecycle/ownership and Playwright documents CDP as lower fidelity.

## Generic “self-healing” recovery ladder — REJECTED

Recovery must be tied to a typed failure and bounded transition.

---

# Deferred decisions

## Visual grounding implementation — DEFERRED

Research supports multimodal fallback, but add only after semantic fixtures demonstrate a necessary task class that cannot be completed otherwise.

## Persistent cross-task memory — DEFERRED

Task facts/event state first. Cross-task memory introduces staleness/privacy complexity.

## Connector/API capability router — DEFERRED UNTIL CORE KERNEL

Architecturally planned, but browser kernel must prove general behavior first.

## Web-specific fine-tuning/RL — DEFERRED, CONDITIONAL

WebRL gives evidence that an 8-9B model can improve dramatically with web-specific training. Trigger only if measured Qwen decision quality/generalization is the limiting factor after browser mechanics are stable.

## Existing-browser attachment — DEFERRED

Optional later mode with explicit privacy/tab-ownership boundaries.

## Long 100+ page research — DEFERRED UNTIL MEDIUM TASK STABILITY

Architecture is prepared for it through FactStore/provenance/checkpoints, but it should not be used to validate the primitive agent loop.

---

# Architecture freeze checklist

Before we write the implementation master prompt, every P0 row must be either:

```text
RESOLVED
or
PROVISIONAL with a test that occurs before dependent implementation
```

No row may remain "we will figure it out inside Codex." That is exactly what this repository is intended to prevent.

## Status: satisfied

All nine P0 rows are `RESOLVED`. One resolved negatively (`QWEN3_8B_INADEQUATE`)
and carries the three mandatory pre-conditions listed above rather than a
"figure it out later".

Frozen architecture:
[`../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md`](../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md).
Consolidated go/no-go:
[`../experiments/p0_summary/P0_CONSOLIDATION.md`](../experiments/p0_summary/P0_CONSOLIDATION.md).

## New findings that changed the design

The campaign did not merely confirm the existing plan. Four things changed:

1. **The load-bearing freshness mechanism is node binding, not the invalidation
   rule.** [E4](../experiments/observation_invalidation/REPORT.md)'s
   `UNSAFE_URL_ONLY` control was designed to be unsafe and was not, because it
   still held an element handle. A policy that re-resolves by accessible name
   produced 84 wrong-target executions.
2. **Explicit invalidation must outrank the invalidation policy.**
   [E7](../experiments/human_handoff/REPORT.md) found that when a human merely
   types in a field, nothing is detectable from the DOM, so only an explicit
   controller command can invalidate. This is now unconditional.
3. **Playwright MCP cannot express page ownership.** It has no page-creation
   event and no opener, so a popup can only ever be `UNKNOWN`. This disqualified
   it under a rule written before the experiment.
4. **The Verifier is load-bearing, not optional polish.** It is the only layer
   that can catch the model's remaining failure class.
