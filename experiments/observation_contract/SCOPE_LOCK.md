# Observation Contract V1 — scope lock

**Recorded before any implementation.** Frozen at the moment of writing.
Branch: `implementation/observation-contract-v1`, from
`implementation/verifier-v1` @ `213779b` (verified clean, remote in sync).

The point of this file is to make it impossible to quietly widen the work in
response to whatever the tests turn up. If something new appears, it gets
documented below under "found but not fixed" — not fixed.

## Admitted scope

Only defects that were **documented before this branch existed**, are
**observation representation or identity** defects, and are **not Qwen reasoning
mistakes**.

| # | Defect | Documented in | Class |
|---|---|---|---|
| A | Frame identity is positional (`f{index}`); detaching a frame renumbers the others, so an id can transfer from one frame to another | [ADR-015](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md), [Verifier README](../../browser_agent_v2/verification/README.md) limitation 3 | identity |
| B | Elements inside a table row carry no row context (AD-M22) | [E3 report](../qwen_adequacy/REPORT.md), [Freeze §3 defect 1](../../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md) | representation |
| C | Observation text excludes bare `<div>` content | [Freeze §3 defect 2](../../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md), [Verifier README](../../browser_agent_v2/verification/README.md) limitation 1 | representation |

## Fourth item: admitted, with justification

| # | Defect | Documented in | Class |
|---|---|---|---|
| D | Observation text is collected for the main frame only (`fi == 0`), so no text evidence exists for any child frame | [Verifier README](../../browser_agent_v2/verification/README.md) limitation 2 (committed at `213779b`, i.e. before this branch) | representation |

All three admission conditions hold: documented before this branch, a text
**representation** defect, and nothing to do with model reasoning.

It is admitted for one further reason. Issue A gives frames a real identity and
the contract must state how page/frame scope attaches to observation content. If
elements were frame-scoped while text silently remained main-frame-only, the
frozen contract would contradict itself on its own central question. D is
therefore a consequence of doing A and C properly rather than an independent
enhancement, and it is bounded to *scoping existing text collection*, not to new
collection rules.

## Explicitly out of scope

Not touched, regardless of what testing reveals:

- Qwen prompts, model, parameters, thresholds, datasets, adequacy evaluation
- the controller, planner, memory, autonomous loop
- retries, refresh recovery, site-specific logic, additional agents
- the page registry (unless a scoped change forces a compatibility fix)
- the PolicyEngine
- anything found *during* this work that is not already listed above

## Considered and rejected as in-scope

- **The four kernel defects in the [E1 report](../browser_kernel/REPORT.md)** —
  already fixed during the P0 campaign; nothing outstanding.
- **The six Qwen failures in [E3](../qwen_adequacy/REPORT.md) other than
  AD-M22** — E3 states explicitly that the information was fully present in the
  observation for all six. Judgment failures, not representation defects.
- **No production ArtifactStore** (Verifier README limitation 4) — a missing
  component, not an observation-contract defect.
- **Page ownership cannot be reconstructed after controller restart**
  ([Freeze §5](../../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md)) — page registry,
  and a genuine limit rather than a defect.

## Found but not fixed

Anything discovered during this work that is out of scope is recorded here
rather than acted on.

Two things surfaced during the work and were **not** acted on.

1. **The ContextBuilder caps model-facing text at 12 blocks, in document order.**
   With richer text extraction, a task-relevant line beyond that cap can be
   truncated away — on the realistic fixture the three signal lines land at
   positions 10-12, which is uncomfortably close. The cap lives in the
   prompt-rendering layer, not in the observation, and changing it would be
   prompt tuning. Recorded for the next gate, which sets up a fresh benchmark
   anyway.

2. **The frozen dataset builders still reference the pre-V1 contract.**
   `qwen_decision_interface/build_dataset.py` and
   `qwen_adequacy/build_adequacy_set.py` filter on `frame_id == "f0"` and index
   text blocks as strings. They were deliberately left untouched: they were not
   run, the datasets they produced are byte-identical to `213779b` (asserted by
   test), and the next gate regenerates datasets against the new contract.

Neither blocks the three scoped corrections.
