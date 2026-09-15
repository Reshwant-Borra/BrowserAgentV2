# P0 Experiment 1 — BrowserKernel Adoption Spike

Playwright MCP vs. direct Playwright, tested against a shared `BrowserKernel`
contract and a deterministic local fixture app, to resolve ADR-002 and the
"Browser kernel: MCP vs direct Playwright" row of `06_OPEN_QUESTIONS/DECISION_GATES_V2.md`.

**Verdict: `ADOPT_DIRECT_PLAYWRIGHT`.** Full evidence, tables, and rationale: [`results/report.md`](results/report.md).

This is a standalone spike, not part of BrowserAgentV2 itself. It does not
implement the agent, planner, model integration, memory, or controller —
only the deterministic browser substrate the real architecture depends on.

## Layout

```text
contracts/kernel.ts          shared BrowserKernel interface + typed errors both
                              adapters implement (NOT the production API — see
                              its header comment)
adapters/direct_playwright/  candidate A: in-process Playwright, stamped-attribute
                              observation/targeting
adapters/mcp/                candidate B: @playwright/mcp over stdio, parses its
                              text/YAML snapshot + tab-list protocol
fixtures/                    Express app serving fixtures A-L (typing, controlled
                              rerenders, hydration, stale targets, popups, frames,
                              dialogs, persistence, handoff, downloads, ownership)
                              plus an out-of-band control channel used to simulate
                              human/external browser events (see below)
tests/                       13 test suites + orchestrator (run_all.ts) + harness
scripts/                     smoke tests, latency benchmark, parser regression test
results/                     direct_playwright.json, mcp.json, latency.json, report.md
```

## Design notes worth knowing before reading the code

- **Both adapters expose the same contract**, but each mints and resolves
  `Target`s its own way: the direct-Playwright adapter stamps
  `data-bk-obs`/`data-bk-ref` attributes on elements at observation time and
  re-queries by that selector; the MCP adapter uses MCP's own snapshot refs
  directly. Both are observation-scoped and both reject stale reuse — see
  `resolveTarget()` in each adapter.
- **The control channel (`fixtures/controlChannel.ts`) simulates human/external
  browser events** — a login completing, an out-of-band tab opening — via an
  HTTP-triggered, page-polled event system, *without* going through the
  kernel under test. This makes handoff/resume and ownership-of-externally-created-tabs
  fully automated and repeatable while still producing the real browser-level
  events (real DOM mutation, real `window.open()`) the kernel must react to.
  It is not a claim that a human clicking is identical to a script doing it —
  see `results/report.md`'s "Remaining limitations" for what this does and
  doesn't prove.
- **`OWNERSHIP_ATTRIBUTION_WINDOW_MS` (1500ms, in both adapters)** is a
  deliberate, documented, bounded heuristic for attributing a newly-discovered
  page to the agent action that likely caused it, used identically by both
  candidates for a fair comparison. See the report's architectural findings
  for its limits.
- **Crash/reconnect tests run each kernel instance in a separate OS process**
  (`tests/crashWorker.ts`, spawned by `tests/suite_crash_reconnect.ts`) so the
  test can `SIGKILL` it for real, rather than simulating a crash in-process.

## Running it

```bash
npm install
npx playwright install chromium

# terminal 1: fixture server
npm run fixtures

# terminal 2
npx tsx scripts/test_parser.ts            # fast: MCP snapshot-parser regression test
npx tsx tests/run_all.ts direct_playwright
npx tsx tests/run_all.ts mcp
npx tsx scripts/bench_latency.ts
```

`tests/run_all.ts both` runs both candidates back to back. Each candidate's
full run (all 13 suites, 295 cases) takes roughly 1.5–5 minutes depending on
the candidate (MCP is slower — see the report's latency section).

## What's NOT here

Per the experiment's scope: no autonomous agent, no Qwen/model integration,
no planner, no ContextBuilder, no SQLite task memory, no long-term memory,
no site-specific handlers. Those are later phases, gated on this decision.
