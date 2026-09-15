# Architecture Decision Records

This file records current decisions and their confidence. A decision can change only when new evidence or a reproducible test justifies it.

## ADR-001 — Browser kernel abstraction

**Decision:** ACCEPTED.

All browser operations go through a `BrowserKernel` interface. No controller/model code depends directly on Playwright MCP/CDP internals.

**Reason:** protects the architecture from a bad browser-runtime choice and lets us evaluate MCP vs direct Playwright without rewriting upper layers.

## ADR-002 — BrowserKernel implementation: direct Playwright

**Decision:** ACCEPTED. First (and current) `BrowserKernel` implementation is **direct Playwright**, launched via `chromium.launchPersistentContext`. Playwright MCP was tested first, per the original plan, and rejected based on evidence.

**Experiment:** P0 Experiment 1, `experiments/browser_kernel/`, run 2026-09-15. Full report: `experiments/browser_kernel/results/report.md`; raw results: `experiments/browser_kernel/results/{direct_playwright,mcp}.json`.

**Environment:** macOS 26.6.2, Node v24.19.0, `playwright` 1.63.0 (Chromium build 1243 / Chrome for Testing 153.0.8010.12), `@playwright/mcp` 0.0.81, `@modelcontextprotocol/sdk` 1.30.0. Both candidates tested headless against the same local fixture app, same machine, same session.

**Fixture/test counts:** 13 controlled fixtures (normal typing, controlled/rerendering input, delayed hydration, 4 independent stale-target scenarios, popups/tabs, frames incl. nested, dialogs, persistence, human handoff, downloads, tab/page ownership incl. duplicate-title/duplicate-URL cases), 295 test cases per candidate, run to completion for both.

**Results:** direct Playwright 285/295 (96.6%); Playwright MCP 275/295 (93.2%). Every invariant both candidates were tested against, they both passed 100% — *except* exact typing, where MCP scored 40/50 against direct Playwright's 50/50.

**Why MCP was rejected — the deciding failure:** MCP's `browser_snapshot` reports element values through its accessibility-tree text representation, which collapses whitespace (trims leading/trailing spaces, collapses internal whitespace runs, converts tabs to spaces) — deterministically and 100% reproducibly for every whitespace-sensitive value tested, unrelated to any adapter bug (a separate value-parsing bug was found and fixed first; the whitespace behavior is what remained after that fix). This is MCP's *verification channel* itself, not a fixable client-side workaround: reading the true DOM value would require bypassing the accessibility snapshot MCP is built around, defeating the point of using it. Exact typing is one of this project's explicitly critical invariants (ADR-010's postcondition-verification requirement; this project's own prior typing/search regressions per `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md` and `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md` Regression R3). Direct Playwright's fill/observe path reads the real DOM value with no such gap and passed 50/50.

**Other MCP-specific findings** (documented for any future re-evaluation, none individually disqualifying but all compounding the case): no stable per-tab identity (index-only addressing — the adapter must self-maintain pageId↔index correlation); no opener/parent relationship exposed for new pages (ownership attribution falls back to a bounded time-window heuristic, a strictly weaker signal than direct Playwright's `page.opener()`); no push notification for new tabs (requires polling); an open dialog blocks *unrelated* tool calls for the full request timeout rather than surfacing promptly; reliable shutdown requires explicitly calling MCP's own `browser_close` tool rather than relying on transport close alone; and `browser_click`'s default ~500ms post-action settle wait dominates click latency (MCP median 569ms vs. direct Playwright 27ms; startup 545ms vs. 58ms).

**A symmetric, non-deciding finding:** character-by-character typing (`typeSequential`/`press_sequentially`) failed identically on both candidates (0/10 each) against a fixture that replaces its `<input>` DOM node on every keystroke (deliberately, to reproduce the old BrowserAgent's controlled-input regression) — the replacement node doesn't inherit focus on either runtime, so only the first keystroke lands. This is a genuine limitation of that typing method against that DOM pattern for both runtimes, not a factor in the MCP-vs-direct decision. Practical implication: a controlled-input typing fallback should prefer single-dispatch `fill()` (verified via fresh observation) over sequential keystroke simulation.

**Rationale for the decision:** direct Playwright passed every critical invariant cleanly (target freshness, exact typing, page identity, tab/page ownership, frame correctness, persistent profile control, human pause/resume, reconnect behavior, predictable typed errors) and is 10–20x lower latency for startup and click. MCP failed one of those critical invariants deterministically, for a structural reason, not a bug. Per the experiment's own decision rule: *if MCP fails a critical invariant that direct Playwright can satisfy cleanly, adopt direct Playwright rather than spend time building architectural workarounds to preserve MCP.*

**Known limitations of this experiment** (not proven either way, should inform any later re-evaluation): long-running session stability (all tests were short-lived processes); non-headless/headed-mode behavior; popup-ownership attribution beyond the ~1.5s bounded window used by both adapters; behavior under concurrent/overlapping actions (never exercised, since ADR-005 forbids them anyway); and all testing used local fixtures rather than live third-party sites, per the experiment's own instruction not to use live sites as primary evidence. `@playwright/mcp` is pre-1.0 (0.0.81) — the whitespace-normalization and other MCP-specific findings above should be re-checked if a materially newer MCP version is later considered.

**Fallback:** none needed — direct Playwright is adopted outright, not as a fallback.

## ADR-003 — Dedicated browser profile

**Decision:** ACCEPTED for MVP.

Use a BrowserAgent-owned persistent Chromium profile rather than attaching to arbitrary user Chrome tabs by default.

**Reason:** reduces tab-ownership ambiguity, keeps login state, and makes browser lifecycle reproducible.

Existing-browser attachment can be revisited later as an optional mode.

## ADR-004 — Structured model decisions

**Decision:** ACCEPTED in principle; exact mechanism OPEN.

No free-form action parsing. Compare native Qwen/Ollama tool calling against a strict structured `Decision` schema using a frozen evaluation set.

## ADR-005 — One state-changing action per controller step

**Decision:** ACCEPTED for MVP.

**Reason:** any state change can invalidate the observation and its targets. This rule maximizes debuggability and prevents stale action sequences.

## ADR-006 — No model-callable refresh

**Decision:** ACCEPTED.

Reload/refresh is not in the normal model action schema. If a very specific runtime failure later requires reload, it belongs in deterministic recovery policy with a reproducible test.

## ADR-007 — SQLite first

**Decision:** ACCEPTED.

Use SQLite for task state, facts, checkpoints, and trace metadata. Do not add a vector database until a demonstrated retrieval problem requires it.

## ADR-008 — Human handoff is a runtime state

**Decision:** ACCEPTED.

Password, MFA, CAPTCHA, ambiguous account choice, consent, and high-impact submission use explicit `WAITING_FOR_USER` / `WAITING_FOR_CONFIRMATION` states.

## ADR-009 — Accessibility-first grounding

**Decision:** ACCEPTED for primary path.

Use semantic/accessibility observation by default, with selective DOM/CDP enrichment and visual fallback rather than full DOM/screenshot-first operation.

## ADR-010 — Deterministic verification after state change

**Decision:** ACCEPTED.

Every mutating browser action requires a postcondition result. Browser API success alone is insufficient.

## ADR-011 — No site-specific architecture

**Decision:** ACCEPTED.

Do not add `CanvasAgent`, `TravelAgent`, etc. as core architectural branches. Different tasks should compose the same primitives. Specialized connectors/adapters may be added later when they provide clear deterministic value.

## Rejected approaches for the MVP

- giant one-shot prompt that plans and executes a full web task;
- raw DOM in every model prompt;
- unrestricted JavaScript generated by Qwen;
- shell execution as a browser fallback;
- automatic refresh as generic recovery;
- arbitrary action retries;
- treating browser history as model memory;
- large site-specific skill library;
- multi-agent manager/worker architecture;
- vision-first coordinate clicking for normal DOM controls.

## Decision discipline

When implementation evidence conflicts with an ADR:

1. capture a minimal reproduction;
2. identify which assumption is false;
3. update the ADR/research document;
4. change the smallest relevant layer;
5. add a regression test.

Do not silently patch prompts or add another fallback layer.
