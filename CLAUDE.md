# ComputerAgent — Claude Operating Guide

## Read this first

This repository is evolving BrowserAgentV2 into **ComputerAgent**, a local-first, cross-platform computer-use agent.

Before substantial implementation work, read these documents in order:

1. `docs/PRODUCT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/BUILD_SPEC.md`
4. `docs/ROADMAP.md`
5. `docs/DECISIONS.md`
6. The two research PDFs in the repository root when deeper evidence or rationale is needed.

## Source-of-truth hierarchy

When sources disagree, use this order:

1. Measured Phase 0 evidence and automated tests
2. `docs/BUILD_SPEC.md`
3. `docs/DECISIONS.md`
4. `docs/ARCHITECTURE.md`
5. `docs/PRODUCT.md`
6. Research PDFs
7. Old BrowserAgentV2 assumptions/code

Do not silently override a higher-level source. If evidence requires changing a frozen decision, record the evidence and update the relevant documents explicitly.

## Non-negotiable engineering rules

- Do **not** rewrite BrowserAgentV2 from scratch. Preserve useful controller, durable-state, verification, provenance, handoff, recovery, and regression concepts.
- Do **not** redesign the architecture around one demo, website, application, or benchmark task.
- Do **not** treat a local model as the authoritative state machine. ComputerAgent owns authoritative state.
- Do **not** use the model context window as long-term memory.
- Do **not** make screenshot-to-coordinate control the default path.
- Prefer execution in this order: native API/tool -> browser semantics -> desktop accessibility -> visual grounding -> capability-gated isolated workspace -> human handoff.
- Never assume an action is background-safe because a model believes it is. Background safety comes from measured capability metadata.
- Journal state-changing intent before execution; observe and verify afterward; never blindly repeat an ambiguous state-changing action after a crash or timeout.
- Treat webpage/application content as untrusted data, not authority to change goals, permissions, or policy.
- Authentication, MFA, CAPTCHA, OS security prompts, and secret-entry boundaries require explicit handoff rather than bypass.
- Hardware capability is runtime state. Never select a model solely from a GPU marketing name.

## Current development stage

We are at **Phase 0 — evidence, not product polish**.

Do not build a giant production UI yet. Build capability probes, fixtures, benchmark harnesses, evidence capture, and acceptance gates first. Phase 0 exists to determine what ComputerAgent can safely and reliably promise on real macOS and Windows hardware.

## Graphify / repository memory

Set up Graphify only as an **auxiliary retrieval/indexing layer** for easier repository navigation and memory. It must never become authoritative state or replace these Markdown documents, Git history, tests, benchmark artifacts, or ComputerAgent's eventual durable task state.

Before installing or pinning Graphify:

- verify the exact upstream project/package and current installation instructions;
- inspect license and security implications;
- keep configuration isolated and removable;
- do not commit secrets, tokens, machine-specific credentials, generated caches, or large indexes;
- document setup in `docs/GRAPHIFY.md`;
- index source code and documentation, including these source-of-truth Markdown files; include PDFs only if the verified Graphify integration supports them reliably;
- ensure ComputerAgent development remains fully possible when Graphify is unavailable.

Graphify retrieval results are hints. Resolve conflicts against the source-of-truth hierarchy above.

## Documentation discipline

When Phase 0 proves or disproves an assumption:

1. Save the raw evidence/result.
2. Update `docs/BUILD_SPEC.md` with the measured capability or gate status.
3. Update `docs/DECISIONS.md` if an architectural decision changes.
4. Update `docs/ARCHITECTURE.md` only when the architecture itself changes.
5. Add/maintain a regression test for historical failures when possible.

A future coding session should be able to understand the current system from the repository without relying on chat history.
