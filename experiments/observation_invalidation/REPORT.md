# Experiment 4 — observation invalidation

**Gate:** `Observation invalidation` (P0, was `OPEN`)
**Verdict:** `INVALIDATION_RESOLVED`
**Evidence:** [`results/experiment4_raw.json`](results/experiment4_raw.json)
**Reproduce:** `BAV2_PORT_BASE=8810 python -m experiments.observation_invalidation.run_invalidation --reps 12`

## Question

Can BrowserAgent reliably prevent actions against stale browser state?

Required result: **zero wrong-target executions**. A stale target may safely
fail. It may never silently retarget.

## Method

14 mutation scenarios are applied between observation and action, each run under
four candidate invalidation policies, 12 repetitions each — 168 runs per policy,
672 total. Two policies are deliberately unsafe controls, present so the result
can show *which* mechanism does the work rather than merely that everything
passed.

Adversarial by construction: the replacement node in `identical-node-replacement`
has the same tag, id, class, `data-kind`, text, attributes and DOM position as
the original, and the page is at the same URL with the same title. Nothing
observable distinguishes it. `full-navigation-same-url` navigates to the *same
URL*, so a URL comparison sees no change at all.

Ground truth is the fixture server's out-of-band effect log: the original node
and its replacement report different handler names (`ORIGINAL` vs
`REPLACEMENT`), so a wrong-target execution is directly observable.

## Results

| scenario | NODE_IDENTITY | STRICT_SUPERSEDE | UNSAFE_NAME_RESOLVE | UNSAFE_URL_ONLY |
|---|---|---|---|---|
| full-navigation-same-url | refused | refused | **WRONG ×12** | refused |
| reload-same-url | refused | refused | **WRONG ×12** | refused |
| innerhtml-rerender | refused | refused | **WRONG ×12** | refused |
| identical-node-replacement | refused | refused | **WRONG ×12** | refused |
| element-removed | refused | refused | refused | refused |
| sibling-reorder-node-intact | *executed correctly* | refused | executed | executed |
| spa-route-change | refused | refused | **WRONG ×12** | refused |
| manual-human-interaction | refused | refused | **WRONG ×12** | refused |
| frame-reload | refused | refused | **WRONG ×12** | refused |
| frame-replacement | refused | harness error | refused | refused |
| popup-opened, page unchanged | *executed correctly* | refused | executed | executed |
| owning-tab-closed | refused | refused | refused | refused |
| active-tab-switched | *executed correctly* | *executed correctly* | executed | executed |
| kernel-restart-reconnect | refused | refused | refused | refused |
| **wrong-target executions / 168** | **0** | **0** | **84** | **0** |

## What the controls actually showed

The controls changed the conclusion, which is why they were worth running.

**`UNSAFE_NAME_RESOLVE` — 84 wrong-target executions in 7 scenarios.** This
policy re-resolves the target by role and accessible name at action time, which
is what an agent does when it stores "the Confirm button" rather than a node. It
clicked the replacement element every single time, and the kernel reported
success. This is the failure mode the architecture exists to prevent, and it is
not hypothetical: it fires on ordinary SPA navigation and ordinary React
rerenders, not just on the adversarial fixture.

**`UNSAFE_URL_ONLY` — 0 wrong-target executions.** This was designed as an
unsafe control and it was not unsafe, which is the most useful thing the
experiment produced. It skips the document and connectedness checks but still
holds the original **element handle**. Playwright refuses to act on a detached
node, so it fails closed by accident.

The conclusion follows directly:

> **The load-bearing mechanism is binding a target to a live DOM node, not the
> invalidation rule layered on top.** Any policy that keeps node identity is
> safe. Any policy that re-resolves from the page is not, regardless of how
> careful its invalidation rule is.

`UNSAFE_URL_ONLY` is still not shippable, for a different reason: it produced
**96 untyped `INTERNAL` errors** where `NODE_IDENTITY` produced
`DOCUMENT_CHANGED` (24), `TARGET_STALE` (72), `FRAME_DETACHED` (12),
`PAGE_CLOSED` (12) and `TARGET_NOT_FOUND` (12). Typed failure classification is
a stated architectural requirement — the controller must know *why* a target
failed to choose a transition — so an accidentally-safe policy with generic
errors does not qualify.

## Choosing between the two safe policies

[`MASTER_VALIDATION_PLAN.md`](../../04_TESTING/MASTER_VALIDATION_PLAN.md)
section 4 asks for "the most permissive policy that never permits incorrect
stale targeting in the fixture suite". Both safe policies score zero
wrong-target executions, so permissiveness decides.

`STRICT_SUPERSEDE` invalidates every observation on a page after any mutating
action. It refused three scenarios the node was still valid for
(`sibling-reorder-node-intact`, `popup-opened-page-unchanged`, and part of
`frame-replacement`). The `frame-replacement` harness error is itself the
finding: the scenario needs two clicks from one observation to set itself up,
and `STRICT_SUPERSEDE` forbids that. Under it, every single action costs a
re-observation — 40 ms and a full model context rebuild — even when nothing
relevant changed.

`NODE_IDENTITY` refuses exactly the eleven scenarios where the node, document,
frame or page genuinely changed, and permits the three where it did not.

**Adopted: `NODE_IDENTITY`.** A target is valid while its node is connected, its
document token is unchanged, its frame is attached and its page is open.

## The explicit-invalidation escape hatch

Experiment 7 found that `NODE_IDENTITY` alone is not sufficient for handoff. When
a human edits a field or opens a tab, no node is disconnected and no document is
replaced, so every pre-handoff target stayed valid. The policy is correct — the
kernel genuinely could not detect that anything changed — but trusting those
targets after a human touched the browser is wrong.

The fix is a second, orthogonal mechanism: `invalidate_all_observations(reason)`
is an explicit controller command that outranks the policy. It was previously
honoured only under `STRICT_SUPERSEDE`, which is the defect Experiment 7
surfaced. It is now unconditional.

```text
policy      -> what the kernel notices by itself
explicit    -> the controller stating the world changed underneath it
```

## Verdict

```text
INVALIDATION_RESOLVED
```

Zero wrong-target executions across 336 runs of the two safe policies, including
every adversarial identical-replacement case. The mechanism is node binding plus
document identity plus an unconditional explicit invalidation command.

## What this does not establish

- Only same-process kernel restarts were tested; a browser *crash* with the
  controller alive was not separately exercised here.
- `frame-replacement` under `STRICT_SUPERSEDE` is recorded as a harness error,
  not a policy result, because the scenario setup is incompatible with that
  policy. It is not counted for or against it.
