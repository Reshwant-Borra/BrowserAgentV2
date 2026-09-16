# Observation Contract V1

**Status:** FROZEN
**Date:** 2026-09-16
**Branch:** `implementation/observation-contract-v1`, from
`implementation/verifier-v1` @ `213779b`
**Scope lock:** [`../experiments/observation_contract/SCOPE_LOCK.md`](../experiments/observation_contract/SCOPE_LOCK.md)

This document defines what a BrowserAgentV2 observation *means*. It corrects
three defects that were documented before this branch existed and had been
deliberately left open; it introduces nothing else.

**After this freeze, a Qwen evaluation may not modify this contract.** If the
model fails a held-out benchmark, we evaluate the model. We do not tune the
observation to individual evaluation failures — that is the pattern this
repository exists to avoid.

---

## 1. Observation identity

```text
observation_id   "obs_00042"   monotonic per kernel instance
```

An observation is an immutable snapshot of one page at one moment. Every
observation carries `document_token` (a per-document random token, so a new
document is detectable even at an identical URL), `document_generation`, and a
`state_fingerprint` over its own content.

Observation ids are strictly increasing, which is what lets the Verifier reject
evidence that does not post-date the action it is verifying.

## 2. Target identity

```text
target = "<observation_id>:<frame_id>:e<N>"
         e.g. "obs_00042:fr_7:e17"
```

A target names **one live DOM node**, held by handle. It is never a selector, a
name, a position or a URL ([ADR-012](ARCHITECTURE_DECISIONS.md)). Its string
form carries the observation that minted it and the frame it lives in, so a
target is self-describing and cannot be silently reinterpreted against a
different observation or frame.

Evidence: [E4](../experiments/observation_invalidation/REPORT.md) — 0
wrong-target executions in 336 runs; the control that re-resolved by accessible
name produced 84.

## 3. Freshness and invalidation

A target resolves only while **all** of these hold:

```text
the node is still connected to its document
the frame's document_token is unchanged
the frame is still attached
the page is still open
the observation has not been explicitly invalidated
```

Policy: `NODE_IDENTITY` — the most permissive rule that never permits incorrect
stale targeting. Plus an unconditional `invalidate_all_observations(reason)`
that outranks the policy and is used at handoff, resume and reconnect
([ADR-013](ARCHITECTURE_DECISIONS.md)); it exists because a human typing into a
field changes nothing a DOM inspection could detect.

## 4. Page identity

```text
page_id   "page_3"   minted at the page-creation event
```

Never a title, never a URL, never a tab index. Ownership (`AGENT` / `USER` /
`EXTERNAL` / `UNKNOWN`) is decided once at creation and never revisited; a popup
inherits its opener's owner. Only `AGENT` pages may be closed automatically.

Evidence: [E5](../experiments/page_registry/REPORT.md) — 220/220, zero user tabs
closed, including three tabs at a byte-identical URL and title.

## 5. Frame identity — **corrected in V1**

```text
frame_id   "fr_7"   minted at the frame's `frameattached` event
MAIN_FRAME "main"   sentinel meaning "this page's main frame"
```

`Observation.main_frame_id` gives the minted id of the page's main frame, and
`Observation.frames` lists every observed frame as a `FrameRecord`
(`frame_id`, `page_id`, `parent_frame_id`, `is_main`, `url`, `name`,
`detached`).

**The invariant:**

> A frame identifier assigned to frame A must never later identify frame B.

### What was wrong

Frame ids were positional — `f{index}` over `page.frames`. Detaching a frame
renumbered the rest, so an id silently transferred. On the frames fixture `f1`
meant the same-origin child before a detach and the **cross-origin** child
after, while `frame_tree_version` stayed at 3 — so even a frame-count guard
would not have caught it. Both frames contain a control named "Confirm".

### Why the fix is sound

Measured directly against Playwright rather than assumed
([probe](../experiments/observation_contract/SCOPE_LOCK.md)):

| behaviour | observed |
|---|---|
| Frame object identity across reload | stable, same object |
| across in-frame navigation | stable, same object |
| on detach | removed from `page.frames`, `is_detached()` true |
| new frame at the vacated index | brand-new object, never recycled |
| `frameattached` / `framedetached` / `framenavigated` | all fire reliably |

So the Frame object *is* the identity; the registry only gives it a name. The
kernel holds a strong reference to each Frame, which also prevents Python from
recycling its `id()` onto a later object.

Explicitly **not** used for identity: frame index, DOM order, title, URL alone,
name alone. The adversarial fixture makes url, name, index and DOM order all
useless by construction — two child frames share a `src` and a `name`.

Evidence: 120 adversarial transitions across detach / reinsert / reload /
in-frame navigation / new-frame-at-old-index / iframe-element replacement —
**0 identity transfers**, 252 stale detections.

## 6. Semantic hierarchy — **corrected in V1**

```text
ObservedGroup(group_id, kind, frame_id, label, cells)
ObservedElement.group_id -> the enclosing group, or ""
```

`kind` is `row` (a `<tr>` or `[role=row]`) or `listitem` (an `<li>` or
`[role=listitem|treeitem|option]`). `cells` maps **column header → cell text**
when the table has headers, else positional keys `"1"`, `"2"`, …; `label` is a
compact one-line rendering of the same thing.

### What was wrong

An actionable control inside a table row carried no row context. Three
identical `button 'Open'` entries were indistinguishable, and the row content
(`REF-1002`, `B. Lindqvist`) appeared only as unattached page text. The
observation literally could not express "the Open button in B. Lindqvist's
row". This is AD-M22, documented in
[E3](../experiments/qwen_adequacy/REPORT.md).

### Rules

- Groups are stored **once per group**, not repeated per element, so a ten-button
  row costs one entry.
- `group_id` is frame-qualified (`fr_7:g2`), so a row index in one frame can
  never collide with one in another.
- A cell containing the row's own controls is **omitted** from `cells`: those
  controls are already listed as elements, with targets. Otherwise every row
  would carry `Actions=Open Archive` for no information.
- Header association uses ordinary HTML/ARIA semantics (`thead`, `th`,
  `role=columnheader`). No selector for any particular site.

Deterministic, model-free evidence: 14 association tests and 130 row
associations verified across standard tables, a second table with identical
rows, headerless tables, a row with a missing cell, links in cells, an ARIA
grid, list items, row reorder, and wholesale row replacement.

## 7. Text representation — **corrected in V1**

```text
ObservedText(text, frame_id)
```

Each element contributes its **own direct text nodes** — not `textContent`, and
not a fixed tag whitelist.

### What was wrong

Text came from `h1,h2,h3,p,li,td,label,span` via `textContent`. That (a) missed
ordinary `<div>` content and (b) double-counted, because a container's
`textContent` repeats every descendant's text.

Measured on the investigation fixture: the old strategy captured **5 of 16**
marked signal lines; on a realistic page shape it captured **2 of 5**, missing
order status, amount due and payment due — the three most task-relevant lines
on the page. It is a genuine defect, not a stylistic preference.

This is also why `submit_op.html`'s confirmation was unverifiable by text, and
therefore why **Experiment 6's worker could never record a SATISFIED
verification** — its check was `f"Reference {op}" in text_blocks`. E6's verdict
is unaffected: that rested on server-side duplicate counts.

### Rules

Included: any visible element's own direct text nodes.
Excluded, and why:

| excluded | reason |
|---|---|
| `script`, `style`, `noscript`, `template`, `title` | not page content |
| anything inside `[aria-hidden="true"]` | hidden from assistive technology |
| invisible elements (`display:none`, zero box, …) | describes a state that is not on screen |
| a line identical to a control's accessible name | already in the element list, with a target |
| an exact repeat of an earlier line | do not state the same thing twice |
| blocks under 2 or over 400 characters | noise and runaway blobs |

There is **no relevance filtering**. Guessing that nav or footer text is
unimportant would be exactly the site-shaped heuristic this project refuses.

### Cost

| page | old blocks / chars | new blocks / chars | signal recall |
|---|---|---|---|
| text_variants | 6 / 110 | 16 / 350 | 5 → 15 of 16 |
| text_noise (realistic) | 9 / 97 | 35 / 613 | 2 → 5 of 5 |
| verify_records (table) | 17 / 209 | 16 / 143 | — |

Total +169.5% characters across the three fixtures. On table-heavy pages it is
a **net reduction**, because the duplication is gone.

## 8. Actionability

Per element: `role`, accessible `name`, `value`, `enabled`, `visible`, `tag`,
`section` (nearest preceding heading), `options` (for a combobox: every
selectable `value` and `label`), and `attrs` (`id`, `type`, `href`).

`enabled` is false for `disabled` or `aria-disabled="true"`. `visible` is false
for `display:none`, `visibility:hidden`, `opacity:0` or a zero-size box. Neither
is inferred from appearance.

## 9. Scope

Every piece of observation content is scoped:

```text
element    -> page_id + frame_id (both in the target string)
group      -> frame_id, and group_id is frame-qualified
text block -> frame_id
tab        -> page_id
```

There is no unscoped content. A postcondition may name `MAIN_FRAME`, a concrete
minted `frame_id`, or `None` for "any frame on this page".

## 10. Schema

```python
Observation(
    observation_id, page_id, url, title,
    document_token, document_generation, frame_tree_version,
    main_frame_id,                 # V1
    frames:      [FrameRecord],    # V1
    tabs:        [TabSummary],
    modal,
    elements:    [ObservedElement],
    groups:      [ObservedGroup],  # V1
    text_blocks: [ObservedText],   # V1 (was [str])
    change_summary, state_fingerprint,
)

FrameRecord(frame_id, page_id, parent_frame_id, created_event_id,
            is_main, url, name, detached)
ObservedGroup(group_id, kind, frame_id, label, cells)
ObservedText(text, frame_id)
ObservedElement(target, role, name, value, frame_id, enabled, visible, tag,
                section, group_id, options, attrs)
```

Definitions: [`../experiments/common/contracts.py`](../experiments/common/contracts.py).
Production consumers use the structural protocols in
[`../browser_agent_v2/verification/evidence.py`](../browser_agent_v2/verification/evidence.py).

## 11. Effect on the Verifier

The Verifier's defensive workaround is **removed**. It previously refused any
non-main frame scope that was not pinned by a content anchor, because a
positional id could transfer. With minted identity a `frame_id` is trusted
directly, and a detached frame simply yields no elements — so the postcondition
is false rather than answerable by a different frame.

Frame-scoped `TextPresence` also works now; it previously returned `AMBIGUOUS`
because text existed only for the main frame. See
[ADR-016](ARCHITECTURE_DECISIONS.md).

## 12. Known limitations

1. **Frame ids do not survive a controller restart.** They are minted per kernel
   instance. The contract requires stability for the live session only; a
   restart re-mints, and rediscovered frames are new identities.
2. **The ContextBuilder caps model-facing text at 12 blocks in document order.**
   With richer text extraction, a task-relevant line beyond that cap can be
   truncated away. The cap lives in the prompt-rendering layer, is **not** part
   of this contract, and was deliberately left unchanged here.
3. **No relevance ranking.** Nav and footer text is observed like any other.
4. **Groups cover rows and list items only.** Definition lists, card grids and
   other implicit groupings are not represented.
5. **Cell text is truncated at 80 characters** and a row label at 200.
6. **Frozen E2/E3 datasets are pre-V1 artefacts.** They remain valid historical
   evidence and are unmodified; regenerating them is the next gate's business.
7. **Controlled localhost fixtures only.** Nothing here is evidence about live
   websites.

## 13. What this does not claim

This gate proves the observation contract is *technically stronger and
deterministic*. It makes **no claim** about Qwen's adequacy. No adequacy
evaluation was run, no dataset was generated, and no prompt text changed — the
policy and output-format blocks are byte-identical to `213779b`, asserted by
test.
