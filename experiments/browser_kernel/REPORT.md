# Experiment 1 — BrowserKernel adoption spike

**Gate:** `Browser kernel: MCP vs direct Playwright` (P0, was `OPEN`)
**Verdict:** `ADOPT_DIRECT_PLAYWRIGHT`
**Evidence:** [`results/experiment1_raw.json`](results/experiment1_raw.json)
**Reproduce:** `python -m experiments.browser_kernel.run_spike --passes 3`

## Question

Which runtime should implement `BrowserKernel`: Playwright MCP, or direct
Playwright?

## Method

Both candidates implement the identical [`BrowserKernel`](../common/kernel.py)
interface and run the identical 35-case suite, 3 passes each (105 graded runs
per candidate). Every case gets a fresh kernel instance and a fresh browser
profile, so no case can contaminate another.

Ground truth for "what the page actually did" comes from the fixture server's
out-of-band effect log — the page reports each handler firing with a synchronous
XHR before the handler returns. **The kernel under test never grades itself.**
Field values are measured twice and reported separately:

- `delivered` — did the text reach the page? (oracle)
- `verifiable` — could the kernel read the value back? (kernel's own channel)

Case coverage follows [`MASTER_VALIDATION_PLAN.md`](../../04_TESTING/MASTER_VALIDATION_PLAN.md)
section 2: navigation (6), element targeting (8), text entry (7), tabs and
popups (6), frames (3), dialogs (4), large-page observation (1).

Outcomes are graded `PASS` / `FAIL_SAFE` / `FAIL_UNSAFE` / `UNSUPPORTED` /
`HARNESS_ERROR`. The distinction matters: a runtime that cannot do something but
fails closed is usable; a runtime that does the wrong thing quietly is not.

## Results

| | direct Playwright | Playwright MCP |
|---|---:|---:|
| graded runs | 105 | 105 |
| PASS | **105** | 90 |
| FAIL_SAFE | 0 | 12 |
| FAIL_UNSAFE | **0** | **0** |
| UNSUPPORTED | 0 | 3 |
| HARNESS_ERROR | 0 | 0 |
| pass rate | **100.0%** | 85.7% |
| inconsistent across passes | 0 | 0 |

Neither runtime produced a single unsafe outcome. Both correctly refused the
adversarial identical-node replacement, the removed element, the disabled
control, the overlay-covered control, and the detached frame. Both clicked
exactly the right one of three byte-identical `Submit` buttons.

### Latency (median / p95, ms)

| operation | direct | MCP |
|---|---:|---:|
| kernel start | 368 / 384 | 1022 / 1150 |
| observe | 40 / 321 | 7 / 14 |
| click | **43** / 4012 | **600** / 5021 |
| navigate | 62 / 127 | 135 / 470 |
| type | 20 / 130 | 30 / 1053 |
| handle dialog | **1** / 2 | **1024** / 1027 |
| back | 7 | 31 |

MCP's `observe` is faster because the snapshot is produced in-process by the MCP
server; our direct implementation pays a round trip per frame. Every *action*,
though, costs roughly an order of magnitude more through MCP — a click is 600 ms
versus 43 ms — because each one is a JSON-RPC call that also regenerates page
state. Dialog handling is ~1 s versus ~1 ms.

The p95 click figures (4.0 s / 5.0 s) are both dominated by the deliberately
unactionable cases (disabled and overlay-covered controls), which run to the
configured timeout by design.

## Where MCP falls short

All four gaps are capability gaps, not correctness failures. None of them caused
a wrong action.

1. **No page-creation event and no opener → tab ownership cannot be established.**
   `browser_tabs` returns an ordered list of tabs. There is no creation event,
   no opener reference, and no stable page identity. A popup can only be
   discovered after the fact by diffing the list, so its owner is `UNKNOWN`.
   Cases `TAB-02`, `TAB-03`.

2. **No document identity.** MCP exposes no token that changes when a document
   is replaced. A same-URL reload and a SPA route change are indistinguishable
   through the interface, so the smallest safe invalidation policy cannot be
   expressed on top of it. Case `NAV-03` (`UNSUPPORTED`).

3. **Navigation timeout is not bounded through the interface.** `/slow?ms=9000`
   returns success after 9.1 s rather than a typed timeout at our configured
   4 s budget. Case `NAV-06`.

4. **`contenteditable` values cannot be read back.** The text is delivered
   correctly (`delivered=True`), but the accessibility snapshot does not expose
   the content, so the kernel cannot verify its own write. Case `TXT-03`.

Gap 1 is decisive on its own. [`MASTER_VALIDATION_PLAN.md`](../../04_TESTING/MASTER_VALIDATION_PLAN.md)
section 2 states the spike pass rule in advance:

> "inability to guarantee target freshness, tab ownership, typed errors, or
> pause/resume is disqualifying."

MCP cannot guarantee tab ownership, so it fails a rule written before the
experiment ran. Gap 2 independently blocks Experiment 4's invalidation policy.

## Harness bugs found and fixed (not charged to either candidate)

The first runs produced several dramatic-looking failures that were mine, not
the runtimes'. Recording them because the distinction is the point:

| Symptom | Actual cause |
|---|---|
| MCP "targets are not frame-scoped" (FAIL_UNSAFE) | MCP *does* encode frame scope in the ref (`f1e3`); my parser discarded it. Verified by direct probe: `f1e3`/`f2e3`/`f3e3` hit child / cross-origin / nested frames respectively. |
| MCP "cannot type" | `browser_type` returns only the generated Playwright code, no page state. The adapter had to re-snapshot before reading the value back. |
| MCP "alert not surfaced as state" | The `### Modal state` section lives in the tool result envelope; the adapter was replacing it with the snapshot file contents. |
| MCP hydration reset undetected | The adapter fell back to the accessible *name* when a value was absent, reporting the label as the field's contents — which would turn an empty field into a false verification pass. |
| Both runtimes "text never reached the page" | A stale fixture server from a killed run was still bound to port 8799. Windows `SO_REUSEADDR` lets two sockets listen on one port and which one answers is undefined. The cluster now mints a nonce and refuses to start if anything else replies. |
| Both runtimes hung on the dialog case | `frame.evaluate()` has no timeout and blocks forever behind a native dialog. |

## Defects this experiment found in our own kernel

1. **`textContent` assignment for contenteditable** bypassed `input`/
   `beforeinput`, so the page's own listeners never fired. Replaced with a real
   selection + keyboard insertion.
2. **A pending dialog must gate every path that touches the page**, not just
   actions — otherwise `evaluate()` deadlocks. This turned "dialog is an
   explicit kernel state" from tidy design into a correctness requirement.
3. **Closing the active tab left `_active_page_id` dangling**, so the next
   unqualified call failed with `PAGE_CLOSED` on a page nobody asked about.
4. **The initial page of a browser we launched was being marked `USER`.** For a
   dedicated profile that we start ourselves, it is ours. The `USER` rule
   belongs to the deferred attach-to-existing-browser mode, which is now an
   explicit `initial_pages_owner` parameter.

## Verdict

```text
ADOPT_DIRECT_PLAYWRIGHT
```

Direct Playwright passes 105/105 with zero unsafe outcomes and zero
inconsistency, supports every invariant the architecture depends on, and is
roughly an order of magnitude faster per action. Playwright MCP is safe — it
never did the wrong thing — but it cannot express page ownership or document
identity, which are load-bearing for gates 4, 5 and 7.

This confirms [ADR-002](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md)'s documented
fallback path. The `BrowserKernel` abstraction did its job: the candidate was
swapped without touching anything above the interface, which is the reason
[ADR-001](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md) exists.

## What this does not establish

- MCP was tested at version `0.0.81` only. Gaps 1 and 2 are interface-shape
  issues rather than bugs, but a later version could close them.
- Everything here is controlled localhost fixtures. No claim is made about live
  websites.
- Downloads and uploads were not exercised; they remain P1 in
  [`DECISION_GATES_V2.md`](../../06_OPEN_QUESTIONS/DECISION_GATES_V2.md).
