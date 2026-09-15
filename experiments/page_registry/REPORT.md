# Experiment 5 — page registry and tab ownership

**Gate:** `Tab ownership/page registry` (P0, was `PROVISIONAL`)
**Verdict:** `PAGE_REGISTRY_RESOLVED`
**Evidence:** [`results/experiment5_raw.json`](results/experiment5_raw.json)
**Reproduce:** `BAV2_PORT_BASE=8820 python -m experiments.page_registry.run_page_registry --reps 20`

## Question

Can BrowserAgent know which pages belong to it and avoid harming user pages?

Critical invariant: **zero user-owned tabs closed automatically.**

## Method

11 scenarios × 20 repetitions = **220 runs**, each with a fresh kernel and a
fresh profile.

The human is simulated by creating pages through the raw browser context, never
through `kernel.new_tab()`. The kernel therefore learns about those pages only
from the page-creation event, exactly as it would with a real person.

Every scenario is built so that at least one of title, URL or tab index is
ambiguous — because the rule under test is that identity comes from **the
page_id minted at the creation event** and from nothing else.

Outcomes are `PASS` / `FAIL` / `FATAL_USER_TAB_HARMED` / `HARNESS_ERROR`.

## Results

| # | scenario | result |
|---|---|---|
| PR-01 | agent-created page is `AGENT` | 20/20 PASS |
| PR-02 | pre-existing page ownership | 20/20 PASS |
| PR-03 | popup from an agent page inherits `AGENT` | 20/20 PASS |
| PR-04 | popup from a **user** page inherits `USER` | 20/20 PASS |
| PR-05 | tab the human opens during handoff is `USER` | 20/20 PASS |
| PR-06 | three tabs, identical URL and title, mixed owners | 20/20 PASS |
| PR-07 | **cleanup closes agent tabs, refuses user tabs** | 20/20 PASS |
| PR-08 | closed then reopened at same URL is a new page_id | 20/20 PASS |
| PR-09 | popup that closes itself is reflected in the registry | 20/20 PASS |
| PR-10 | navigating a user page does not convert it to `AGENT` | 20/20 PASS |
| PR-11 | browser restart does not recycle page ids | 20/20 PASS |

```text
220 runs, 220 PASS
user tabs harmed: 0
failures: 0
harness errors: 0
```

## The ownership rule that survived

Ownership is decided once, at the page-creation event, and never revisited:

```text
kernel asked for this page          -> AGENT
page has an opener                  -> inherit the opener's owner
page appeared, nobody asked for it  -> USER
```

The middle rule is what makes PR-04 pass. A popup is not the agent's because the
agent happened to be running; it is the agent's only if the page that opened it
was. A popup spawned by the human's tab stays `USER`, and cleanup then refuses
to touch it.

PR-06 is the case that rules out the tempting shortcuts. Three tabs sit at the
identical URL with the identical title; two are `AGENT` and one is `USER`.
Identity by URL, by title, or by tab index would merge them and cleanup would
close the human's tab. Identity by creation-event id keeps them distinct in all
20 runs.

PR-08 checks the inverse mistake: after an agent page is closed and a new one is
opened at the same URL, the old `page_id` must not be reused. A recycled id
would let a stale reference resolve onto a page that merely looks the same.

## A defect this experiment forced us to fix

The initial page of the browser was being registered as `USER`, on the theory
that "pages that already exist are not ours". That is right when *attaching* to
a browser someone else started, and wrong when we *launched* the browser
ourselves against a dedicated profile — which is the MVP default under
[ADR-003](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md). The consequence showed
up in Experiment 1 as popups inheriting `USER` from a mislabelled opener.

Ownership of the initial pages is now an explicit `initial_pages_owner`
parameter: `AGENT` in launch mode, `USER` in the deferred attach mode. Making it
a parameter rather than a constant is what keeps the deferred CDP mode honest
later.

## Restart behaviour, stated precisely

After a controller restart against the same persistent profile, the kernel has
no way to know who owned a rediscovered page — the creation events are gone with
the previous process. PR-11 verifies only the weaker property that actually
matters: **no page id is reused for a different page**, so nothing is silently
reclaimed as `AGENT` and then auto-closed. Rediscovered pages are not treated as
agent-owned.

This is a real limit, not a pass. Automatic cleanup after a restart is therefore
not safe without re-establishing ownership, and the architecture freeze records
that as a constraint rather than as a solved problem.

## Verdict

```text
PAGE_REGISTRY_RESOLVED
```

220/220, zero user tabs harmed, identity never derived from title, URL or index.
The gate moves from `PROVISIONAL` to `RESOLVED`, with the restart limitation
recorded explicitly.

## What this does not establish

- Ownership cannot be reconstructed after a controller restart (see above).
- `EXTERNAL` ownership is defined in the contract but unused; no external
  integration creates pages yet.
- Playwright MCP cannot satisfy this gate at all — it exposes no creation event
  and no opener, so popups can only be `UNKNOWN`. See
  [Experiment 1](../browser_kernel/REPORT.md).
