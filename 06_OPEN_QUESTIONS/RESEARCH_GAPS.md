# Open Research Questions and Decision Gates

**Status:** NOT READY FOR FINAL ARCHITECTURE FREEZE.

The repository now contains a strong working architecture, but several questions must be resolved by evidence before implementation is considered fully planned.

## P0 — Must resolve before implementation freeze

### 1. Playwright MCP vs direct Playwright

Run the deterministic adoption spike. We need actual evidence for:

- typing/fill reliability on dynamic apps;
- stale-ref semantics;
- popup/tab behavior;
- persistent profile behavior;
- process restart/reconnect;
- human takeover/resume;
- error classification quality.

**Decision:** use MCP if it passes; otherwise implement direct Playwright behind the same `BrowserKernel`.

### 2. Qwen decision interface

Compare native tool/function calling with strict structured `Decision` output on a frozen observation dataset.

Need measured schema-validity and correct-target rates before selecting the interface.

### 3. Ambiguous side effects

Define and test exactly what happens when a state-changing operation may have succeeded but the client lost confirmation. Examples include form submission, sending, and workflow transitions.

Rule is already clear: no blind replay. The unresolved part is the generic evidence/reconciliation protocol.

### 4. Observation invalidation policy

Determine precisely which events create a new incompatible observation version:

- DOM mutation;
- route/URL change;
- navigation;
- tab switch;
- dialog;
- user manual action;
- dynamic subtree update.

Over-invalidation increases model calls; under-invalidation risks stale targets.

### 5. Old BrowserAgent audit

Inspect the actual old repository/code rather than relying on remembered architecture. Classify modules:

```text
KEEP
ADAPT
REWRITE
DELETE
```

Look specifically for useful test fixtures, SQLite/event-store code, browser-session utilities, and proven primitives. Do not import recovery complexity merely because it exists.

## P1 — Resolve during/after kernel spike

### 6. Downloads and uploads

Define safe first-version semantics:

- download destination;
- completion detection;
- filename collisions;
- file provenance;
- upload selection and confirmation;
- preventing arbitrary page instructions from choosing sensitive local files.

### 7. Iframe strategy

Confirm how Playwright MCP exposes nested/cross-origin frames and whether our target schema needs explicit frame ids.

### 8. Visual fallback

Determine the smallest fallback needed for canvas/custom controls. Do not build a full vision-first agent unless real tasks require it.

### 9. Research fact retrieval

Define relevance selection and deduplication for hundreds/thousands of facts without introducing premature vector-memory complexity.

### 10. Progress/loop detection

Define deterministic/model-assisted signals for:

- same action repeated;
- same observation repeated;
- oscillating between pages;
- no new facts gathered;
- repeated postcondition failure.

## P2 — Later architecture research

### 11. Progressive determinism/cache

Research whether successful observed actions should be converted into deterministic reusable recipes similar to Stagehand-style observe → replay patterns.

### 12. External connectors/APIs

Define routing policy for tasks where direct APIs/connectors are more reliable than browser UI automation, such as Calendar or email. The browser kernel should remain useful for discovery/authenticated navigation while deterministic integrations perform structured actions.

### 13. Existing browser attachment

Dedicated BrowserAgent profile is the MVP default. Research optional attachment to a user's existing browser later, with strict tab ownership and privacy boundaries.

### 14. Long-running research

Test hundreds-of-page research with bounded context, provenance, resume, deduplication, and source revisit. This should happen only after the short/medium task loop is stable.

## Research completion definition

Research is “complete enough to build” when:

1. all P0 questions are resolved with tests/data;
2. architecture documents are internally consistent;
3. every major component has an explicit responsibility and interface;
4. failure ownership is clear;
5. Day 1/Day 2 gates are executable tests, not vague goals;
6. Codex can receive bounded implementation tasks without inventing architecture.

Until then, this repository remains an active research knowledge base.
