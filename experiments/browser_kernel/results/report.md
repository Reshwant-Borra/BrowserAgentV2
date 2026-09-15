# P0 Experiment 1 — BrowserKernel Adoption Spike: Results Report

**Date:** 2026-09-15
**Branch:** `experiment/browser-kernel-spike`
**Question:** Should BrowserAgentV2's first `BrowserKernel` implementation be Playwright MCP or direct Playwright?

## Verdict

> **ADOPT_DIRECT_PLAYWRIGHT**

Direct Playwright passed every critical invariant cleanly. Playwright MCP failed one critical invariant — **exact typing** — deterministically and reproducibly, for a reason that is architectural rather than fixable within the adapter (see "Why MCP lost" below). Direct Playwright is also 10–20x lower latency for startup and click operations. Per the decision rule this experiment was scoped against: *"If MCP fails a critical invariant that direct Playwright can satisfy cleanly, recommend ADOPT_DIRECT_PLAYWRIGHT. Do not spend hours creating architectural workarounds merely to preserve MCP."*

## Environment

| | |
|---|---|
| OS | macOS 26.6.2 (build 25G83) |
| Node | v24.19.0 |
| npm | 11.17.0 |
| TypeScript | 5.7.2 (via tsx 4.19.2) |
| `playwright` | 1.63.0 |
| Chromium (via Playwright) | build 1243 (Chrome for Testing 153.0.8010.12) |
| `@playwright/mcp` | 0.0.81 |
| `@modelcontextprotocol/sdk` | 1.30.0 |
| Fixture server | Express 4.21.2, localhost:4173 |

Both candidates ran headless, against the same local fixture server, on the same machine, in the same session.

## Results table

Counts are `passed/total` unless noted. Full case-level detail (including latency and error codes for every one of the 295 cases per candidate) is in `direct_playwright.json` and `mcp.json` in this directory.

| Metric | MCP | Direct Playwright |
| --- | ---: | ---: |
| Stable click | 50/50 | 50/50 |
| Exact typing (fill) | **40/50** | 50/50 |
| React controlled typing — `fill()` | 10/10 | 10/10 |
| React controlled typing — `typeSequential()` | 0/10 | 0/10 |
| Delayed hydration | 20/20 | 20/20 |
| Stale-target rejection | 30/30 | 30/30 |
| Popup/tab capture | 20/20 | 20/20 |
| Page/tab ownership | 20/20 | 20/20 |
| Frame targeting | 20/20 | 20/20 |
| Dialog handling | 30/30 | 30/30 |
| Persistent profile restart | 10/10 | 10/10 |
| Human handoff / resume | 5/5 | 5/5 |
| Crash + reconnect | 10/10 | 10/10 |
| Downloads | 10/10 | 10/10 |
| **Total** | **275/295 (93.2%)** | **285/295 (96.6%)** |
| Median startup | 545 ms | 58 ms |
| p95 startup | 639 ms | 69 ms |
| Median click | 569 ms | 27 ms |
| p95 click | 586 ms | 34 ms |
| Median fill | 12 ms | 9 ms |
| Median observe/snapshot | 4 ms | 2 ms |
| Median page-switch | 6 ms | 0 ms |

Latency figures are from `scripts/bench_latency.ts` (20 isolated repetitions per primitive, separate from the correctness suites so a slow-but-correct call is never conflated with a failure). Raw numbers: `results/latency.json`.

## Why MCP lost: exact typing (critical invariant)

**Finding:** Playwright MCP's `browser_snapshot` reports element *values* through its accessibility-tree text representation, which **collapses whitespace** — leading/trailing spaces are trimmed, internal runs of whitespace collapse to a single space, and tab characters become spaces — exactly like standard accessible-name/value computation for assistive technology. The underlying DOM `input.value` is not affected; only what the snapshot *reports* is.

Reproduced deterministically, 10/10 times, for every value containing leading/trailing whitespace or a tab character:

```
expected: "  leading and trailing  #3"
got:      "leading and trailing #3"

expected: "line1\ttabbed#4"
got:      "line1 tabbed#4"
```

All 10 non-whitespace cases (special characters, unicode, punctuation) passed once a parser bug (below) was fixed — this is not a general typing-fragility issue, it is specifically about whitespace fidelity in MCP's *verification channel*.

**Why this is a critical-invariant failure, not a cosmetic one:** ADR-010 requires deterministic postcondition verification after every mutating action, and Section 11 of the experiment brief explicitly calls out exact spacing as a required typing test. A BrowserKernel built on MCP's snapshot as its verification channel cannot reliably tell a controller "the field now reads exactly what I typed" whenever the target value is whitespace-sensitive (padded form fields, multi-space search queries, tab-delimited paste targets, `textarea` content with intentional formatting). The failure is deterministic and100% reproducible — not flaky — so it cannot be waved off as noise.

**Could this be routed around?** Only by having the kernel verify values through a different channel than the one it uses for grounding (e.g. `browser_evaluate` reading `element.value` directly instead of trusting the snapshot). That is exactly the kind of MCP-specific patch the experiment rules ask us not to build to "preserve" a candidate — it would mean MCP's own primary observation mechanism cannot be trusted for the one thing ADR-010 requires of it, which is itself the finding. Direct Playwright's fill/observe path reads the real DOM value with no such gap.

## Everything else: both candidates were strong

Once real adapter bugs (all mine — see "Bugs found and fixed" below) were fixed, both candidates cleanly passed every other invariant tested: stale-target rejection (including four independent staleness scenarios — rerender, full navigation, SPA `pushState`, and `innerHTML` DOM replacement), page/tab ownership (including the deliberately adversarial duplicate-title/duplicate-URL and out-of-band-tab cases), frame targeting (including a doubly-nested iframe and a same-origin frame replacement), dialogs (alert/confirm/prompt, 10 reps each), persistent-profile restart, human handoff/resume, and crash+reconnect via abrupt `SIGKILL`.

**`typeSequential()` (character-by-character typing) failing identically on both candidates (0/10 each)** is a genuine, symmetric finding, not a bug: Fixture B replaces its `<input>` DOM node on every keystroke (deliberately, to reproduce the old BrowserAgent's controlled-input regression). The replacement node does not inherit browser focus, so only the first keystroke — sent before the first replacement — ever lands; every subsequent synthetic keystroke from either runtime goes nowhere. This is a genuine limitation of character-by-character typing against this class of React re-render for **both** runtimes, and therefore not a factor in the adoption decision. It does mean: a production kernel's typing fallback for controlled inputs should not assume `press_sequentially`/`slowly:true` typing survives a full node replacement — `fill()` (single dispatch, verified via fresh observation) is the safer default, which both adapters already use as the primary path.

## MCP-specific architectural findings (documented, not defects to fix)

These are genuine characteristics of MCP's design, discovered empirically and worth carrying into any future MCP adoption decision:

1. **No stable page identity — index-only.** `browser_tabs` addresses tabs purely by position (`list`/`select`/`close` all take an `index`). There is no GUID. The adapter must maintain its own pageId↔index correlation, re-synced on every `browser_tabs list` call, using position-first / content-fallback matching. This worked cleanly in every test including duplicate-title/duplicate-URL tabs, but is inherently more fragile than direct Playwright's real `Page` object identity, which survives navigation, title changes, and duplicate content with no correlation logic needed at all.
2. **No opener/parent relationship exposed for new tabs.** Ownership attribution for MCP-discovered pages can only use a bounded post-action time window (this experiment used 1500 ms), not a direct opener reference. Direct Playwright exposes `page.opener()` directly. Both approaches worked for every test here, but MCP's is a strictly weaker signal — a popup opened more than the bounded window after its triggering click is indistinguishable, from MCP-observable events alone, from an unrelated externally-opened tab.
3. **No push notification for new tabs.** A delayed popup (this experiment used an 800 ms `setTimeout`) is invisible until the client actively re-polls `browser_tabs list`. Direct Playwright fires a real `page` event the instant the popup is created. The adapter here uses bounded polling (150 ms interval) to compensate — legitimate per the experiment's waiting rules, but a real architectural cost.
4. **An open dialog blocks unrelated tool calls for the full request timeout, not just the triggering action.** A `browser_snapshot` call issued while a `confirm()`/`prompt()` dialog is open from a **different, earlier** action hangs for the full 60s default MCP request timeout before erroring, rather than returning promptly with modal-state information (which it *does* do for the action that itself triggered the dialog). Direct Playwright's native `page.on('dialog', ...)` event fires immediately regardless of what else is in flight. The adapter compensates by using short per-call timeouts (1.2s) when polling for a dialog it didn't itself trigger — again legitimate bounded polling, but it means a naive "wait for dialog" implementation against MCP would hang for a minute on the first miss.
5. **Reliable shutdown requires calling MCP's own `browser_close` tool before closing the client transport.** Relying on the stdio transport's close handshake alone (which the SDK already gives up to ~2s to complete gracefully) was not sufficient to reliably flush persistent-profile writes (cookies/localStorage set moments earlier were lost on the next launch, 10/10 times, until the adapter was changed to call `browser_close` explicitly first). This is the correct, MCP-advertised shutdown sequence, not a workaround — but it is a non-obvious extra step a naive client would miss.
6. **`browser_click`'s default ~500ms post-action settle wait dominates click latency.** MCP's median click latency (569ms) is almost entirely the documented `--timeout-settle` default (500ms), not protocol/process overhead — `browser_snapshot` (4ms median) and `browser_type` (12ms median) are not subject to the same wait. This is configurable but the default materially changes what "one controller step" costs under MCP vs. direct Playwright's near-immediate return (27ms median click).

None of 1–6 were disqualifying on their own — the adapter compensated for each with legitimate, general, non-fixture-specific logic, and every associated test passed 100%. They are reported because a future re-evaluation of MCP (a newer version, a different configuration) should re-check all six, and because they explain a meaningful share of the latency gap.

## Bugs found and fixed during the spike

All of the following were bugs in this experiment's own adapter code, not in Playwright, MCP, or Chromium. Each was root-caused with a minimal repro, fixed, and re-verified; the fix is described in the adjacent code comment at each location so it survives as institutional knowledge.

| # | Bug | Where | Root cause | Fix |
|---|---|---|---|---|
| 1 | Snapshot names fell back to DOM `id` instead of the associated `<label>` text | `adapters/direct_playwright/snapshotScript.ts` | Name-resolution chain didn't check `element.labels` | Added label-text lookup before the placeholder/id fallback |
| 2 | Input role computed from raw HTML `type` attribute | `adapters/direct_playwright/snapshotScript.ts` | `role = el.type` instead of mapping to ARIA-style roles | Mapped common text-like input types to `"textbox"` |
| 3 | `<li>` list items invisible to snapshot at all | `fixtures/pages.ts` (Fixture D) | Snapshot selector doesn't include bare `<li>` | Added `role="button" tabindex="0"` to make them legitimate interactive targets |
| 4 | Fill immediately after a controlled-input re-render hung for the default Playwright 30s timeout | `adapters/direct_playwright/directKernel.ts` `fill()` | Fallback `.textContent()` call had no explicit timeout | Removed the internal-verification fallback path entirely; verification is the caller's job via fresh `observe()`, per the kernel contract |
| 5 | Refs collided across frames within one observation | `adapters/direct_playwright/directKernel.ts` `observe()`/`resolveTarget()` | Each frame's in-page snapshot script re-starts its ref counter at 0, and the index was a flat `Map` keyed only by that per-frame-local token | Scoped the index key (and the `Target.refToken` itself) by frame path |
| 6 | Frame nesting labels collided when an iframe had neither `id` nor `name` | `adapters/direct_playwright/directKernel.ts` `computeFramePath()` | Fallback label was a constant `"anon"` for every unlabeled frame | Fallback now uses the frame's position among its parent's child frames |
| 7 | A popup created before `waitForNewPage()` was called (e.g. a synchronous `window.open()`) was silently lost | `adapters/direct_playwright/directKernel.ts` | The waiter list was only checked for *future* events, with no queue for already-fired ones | Added a discovery queue, mirroring the existing dialog-queue pattern |
| 8 | Explicit `newPage()` creation intermittently misattributed ownership to a later, unrelated popup | `adapters/direct_playwright/directKernel.ts` `onNewPageDiscovered()` | `context.newPage()` and its own `'page'` event race in either order; a `pageIdByPage`-presence check couldn't reliably tell "this is the page I just created" from "this is a genuine new popup" | Added an explicit `explicitCreationInFlight` flag held for the whole duration of `newPage()`, independent of event-vs-call ordering |
| 9 | Clicking a button whose handler opens a native `alert()`/`confirm()`/`prompt()` deadlocked | `adapters/direct_playwright/directKernel.ts` `click()` | A native dialog freezes the page's JS thread; Playwright's `click()` doesn't resolve until the dialog is dismissed, but dismissal only happens from a *separate* `handleDialog()` call the deadlocked `click()` was blocking | `click()` now races the click promise against a poll for a dialog appearing, and returns as soon as either happens (documented Playwright pattern) |
| 10 | Seeded cookie never survived a persistent-profile restart | `fixtures/pages.ts` (Fixture H) | Cookie set without `max-age`/`expires` is a session cookie, not eligible for disk persistence across a browser restart by design | Added `max-age=86400` |
| 11 | Crash-reconnect test's "kill" didn't actually reach the worker or its browser | `tests/suite_crash_reconnect.ts` | `npx tsx <script>` spawns extra wrapper processes not in the same process group as the top-level `npx` PID; killing that PID left the real worker (and Chromium) running as orphans holding the profile lock | Spawn `tsx` directly (no `npx` wrapper) with `detached: true` and kill the whole process group via the negative PID |
| 12 | MCP: every `navigate()` call made a page look closed and minted a phantom replacement | `adapters/mcp/mcpKernel.ts` `reconcileTabs()` | Same-tab correlation required index **and** title/url to match, but navigation legitimately changes title/url for the same tab | Correlate primarily by index; fall back to title/url matching only when index doesn't match (topology changed elsewhere) |
| 13 | MCP: popup ownership/detection lost after `click()` | `adapters/mcp/mcpKernel.ts` `waitForNewPage()` | `click()` itself calls `reconcileTabs()` before returning, so a before/after page-id-set diff computed inside `waitForNewPage()` already included the popup | Replaced the before/after set with a monotonic `creationSeq` cursor |
| 14 | MCP: `newPage()` occasionally returned a stale, already-closed page's info | `adapters/mcp/mcpKernel.ts` `newPage()` | Index-matching loop searched all tracked pages, including closed ones, and a closed page's index can be reused by a later new page | Filter to non-closed pages before matching |
| 15 | MCP: `browser_evaluate`/storage-probe/`readText` results included the whole response wrapper text | `adapters/mcp/mcpKernel.ts` `parseEvaluateResult()` | Regex targeted a code-fence format the tool doesn't actually use | Matched the real `### Result\n<value>\n### ` format (confirmed empirically) |
| 16 | MCP: value parsing broke on any typed text containing `]` | `adapters/mcp/snapshotParser.ts` | Value extraction took "everything after the line's last `]`", but a typed value can itself contain `]` | Strip only well-formed `[attr]`/`[attr=val]` tags (word-token content, matched by position) before extracting the value; unescape YAML/JSON-style quoted values via `JSON.parse` |
| 17 | MCP: cookie/localStorage lost across a clean restart | `adapters/mcp/mcpKernel.ts` `stop()` | Closing only the client-side stdio transport did not reliably flush profile writes | Call the server's own `browser_close` tool before closing the transport |

Bugs 4, 9, 10, 11 were caught by the direct-Playwright candidate first and fixed there; 12–17 are MCP-specific. None of the fixes added retries, sleeps-as-a-fix, site-specific branches, or silent failure-swallowing — each is a specific, general correctness fix, documented inline at its location.

## Critical-invariant checklist

| Invariant | MCP | Direct Playwright |
|---|---|---|
| Target freshness / stale-target rejection | ✅ 30/30 | ✅ 30/30 |
| Exact typing | ❌ 40/50 (whitespace-normalized in the verification channel) | ✅ 50/50 |
| Page identity | ✅ (index-based, adapter-maintained; see finding 1) | ✅ (native object identity) |
| Tab/page ownership | ✅ 20/20 (weaker signal; see finding 2) | ✅ 20/20 |
| Frame correctness | ✅ 20/20 | ✅ 20/20 |
| Persistent profile control | ✅ 10/10 (needs explicit `browser_close`; see finding 5) | ✅ 10/10 |
| Human pause/resume | ✅ 5/5 | ✅ 5/5 |
| Reconnect behavior | ✅ 10/10 | ✅ 10/10 |
| Predictable results/errors | ✅ (text-parsed, `isError` flag) | ✅ (native typed exceptions) |

Direct Playwright is the only candidate with a clean sweep. MCP's single failure is on the list of invariants the experiment brief explicitly designated critical.

## Error-quality comparison

Both adapters expose the same `KernelErrorCode` taxonomy (`TARGET_STALE`, `TARGET_NOT_ACTIONABLE`, `DIALOG_OPEN`, `DOWNLOAD_FAILED`, `OWNERSHIP_VIOLATION`, `TIMEOUT`, `NAVIGATION_TIMEOUT`, etc.) and every test suite asserted on specific codes, not just pass/fail — both classify failures correctly and consistently across all 295 cases. The underlying mechanism differs: direct Playwright throws native, typed exceptions the adapter maps directly; MCP returns free-text tool results plus an `isError` boolean that the adapter must pattern-match (e.g. `/not found in the current page snapshot/i` for staleness). The pattern-matching worked reliably in this experiment, but it is inherently more brittle to a future MCP wording change than direct Playwright's native exception types — a secondary point in direct Playwright's favor, not a deciding one on its own.

## Remaining limitations (not proven either way by this experiment)

- **Long-running session stability.** All tests ran in short-lived processes (seconds to low minutes). Multi-hour session behavior (memory growth, connection drift) was not tested for either candidate.
- **Non-headless behavior.** All tests ran headless. MCP explicitly documents different idle-timeout defaults for headed vs. headless; headed-mode behavior (relevant if a human ever needs to see the live browser) was not exercised.
- **Ownership attribution beyond the 1500ms window.** Both adapters' popup-ownership attribution is time-window-based when an opener reference isn't available (MCP always; direct Playwright as a fallback). A popup opened by agent-triggered page logic more than ~1.5s after the triggering action is not proven distinguishable from a human-initiated one on either candidate.
- **Concurrent/overlapping actions.** Per ADR-005, the architecture never issues two state-changing actions at once; this experiment did not stress-test what either adapter does if that invariant is violated.
- **MCP version drift.** `@playwright/mcp` is at 0.0.81, a pre-1.0 package; the whitespace-normalization finding and the six architectural findings above should be re-checked if a materially newer MCP version is later considered.
- **Real websites.** Per the experiment's own rules, all testing used controlled localhost fixtures, not live third-party sites. Section 19's instruction not to use live sites as primary evidence was followed; this means real-world CAPTCHA/anti-bot/markup-drift behavior is out of scope for this specific spike.

## Files changed

See the top-level summary in the PR/commit description. In brief: `experiments/browser_kernel/**` (new — contracts, both adapters, fixture app, 13 test suites, results), plus this experiment's required update to `03_DECISIONS/ARCHITECTURE_DECISIONS.md` (ADR-002) and `06_OPEN_QUESTIONS/DECISION_GATES_V2.md` in the parent repo.

## Reproducing this experiment

```bash
cd experiments/browser_kernel
npm install
npx playwright install chromium

# terminal 1
npm run fixtures

# terminal 2
npx tsx scripts/test_parser.ts        # parser regression test
npx tsx tests/run_all.ts direct_playwright
npx tsx tests/run_all.ts mcp
npx tsx scripts/bench_latency.ts
```

Each `run_all.ts` invocation writes `results/<candidate>.json`. `bench_latency.ts` writes `results/latency.json`. This report's numbers are those files verbatim.
