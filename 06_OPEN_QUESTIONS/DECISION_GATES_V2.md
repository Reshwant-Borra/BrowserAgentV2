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

# P0 — Must resolve before architecture freeze

| Gate | Current status | Current strongest choice | Resolution evidence required |
|---|---|---|---|
| Browser kernel: MCP vs direct Playwright | **RESOLVED (2026-09-15)** | **Direct Playwright**, behind `BrowserKernel` | Scripted spike (`experiments/browser_kernel/`, 295 cases/candidate) covering refs, typing, tabs, frames, dialogs, profile persistence, handoff, errors, crash. Direct Playwright 285/295 (96.6%) vs MCP 275/295 (93.2%); MCP failed exact typing (40/50) deterministically due to whitespace-normalizing accessibility-snapshot value reporting — a critical-invariant failure per ADR-002. Full evidence: `experiments/browser_kernel/results/report.md`. |
| Qwen output interface | OPEN | strict single `Decision` JSON or native Hermes tool call | frozen 100-300 observation evaluation; schema validity, action+target accuracy, latency |
| Qwen3:8B adequacy | OPEN | use as first local model only if measured | >= target action selection on easy/medium fixtures; if not, revise action space/model |
| Browser profile strategy | PROVISIONAL | dedicated Playwright-managed persistent profile | restart/auth tests; CDP remains later optional due documented lower fidelity |
| Observation invalidation | OPEN | invalidate after navigation/state-changing page events; reobserve after actions | stale-ref stress tests over SPA rerender/frame/tab/user changes |
| Ambiguous side-effect protocol | OPEN | persist intent, reconcile, no blind replay | crash injection at each state-changing boundary with zero duplicates |
| Tab ownership/page registry | PROVISIONAL | ownership at creation event; only AGENT tabs auto-close | repeated popup/manual-tab tests with zero user-tab closure |
| Human handoff/resume | PROVISIONAL | checkpoint, pause, manual action, invalidate refs, rediscover | login/MFA fixture across restart |
| Policy/security boundary | PROVISIONAL | deterministic PolicyEngine outside model | prompt-injection/cross-origin/capability fixture suite |

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
