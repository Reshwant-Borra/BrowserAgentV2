# Graphify Integration for ComputerAgent

## Purpose

Graphify is an auxiliary repository knowledge graph for Claude Code. It helps Claude recover code structure, dependencies, documentation relationships, and architectural rationale across sessions without repeatedly reconstructing the repository from raw search.

Graphify is **not** authoritative project state. The source-of-truth order remains the one defined in `CLAUDE.md`: measured Phase 0 evidence/tests first, then `BUILD_SPEC.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `PRODUCT.md`, research, and finally legacy assumptions/code.

## Verified upstream

Use the current Graphify Labs open-source project and its `graphifyy` Python package. As verified on 2026-09-17, the project supports Claude Code, deterministic AST extraction for code, semantic ingestion of documentation/PDFs, persistent graph output, and Claude integration.

Before installation, re-check upstream installation instructions and release/security notes rather than relying indefinitely on this snapshot.

## Local setup

Prerequisites:

- Python 3.10+
- Claude Code
- this repository cloned locally

Recommended setup from the repository root:

```bash
uv tool install graphifyy
# If uv is unavailable, use an isolated Python tool installer supported by your machine.

graphify install
```

Then, from Claude Code in this repository:

```text
/graphify .
```

After the first successful graph build, enable Claude integration:

```bash
graphify claude install
```

This is intended to make the graph an early navigation aid for Claude instead of forcing every session to rediscover the repository through raw file searches.

## What to index

Index:

- source code
- tests and fixtures
- `CLAUDE.md`
- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/BUILD_SPEC.md`
- `docs/ROADMAP.md`
- `docs/DECISIONS.md`
- `docs/GRAPHIFY.md`
- research PDFs when Graphify's installed version successfully supports PDF ingestion
- Phase 0 harness definitions and human-readable result summaries as they are added

Do not treat generated benchmark blobs, caches, model weights, secrets, virtual environments, dependency trees, build products, or machine-local state as project knowledge.

## Suggested `.graphifyignore`

Create or maintain a `.graphifyignore` with high-noise/generated paths appropriate to the repository. At minimum consider:

```gitignore
.git/
.venv/
venv/
node_modules/
dist/
build/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.pyc
*.log
.env
.env.*
models/
weights/
phase0/results/raw/
```

Do not ignore source-of-truth docs, fixtures, tests, or concise benchmark summaries.

## Expected outputs

Depending on the installed Graphify version, the graph output includes a persistent graph, a human-readable graph report, and an interactive visualization. Generated cache/index material should remain reproducible and must not become the only place architectural knowledge exists.

Before deciding whether any Graphify output belongs in Git, inspect its size, stability, contents, and whether it may contain machine-specific or sensitive material. Prefer keeping disposable caches untracked.

## Claude operating protocol

For architecture, refactoring, implementation, or debugging work:

1. Read `CLAUDE.md` and the relevant source-of-truth documents.
2. If a current Graphify graph exists, use it to locate relevant components, dependencies, tests, rationale, and likely blast radius.
3. Open the authoritative source files before making consequential edits. A graph relationship is navigation/evidence, not permission to change behavior.
4. Resolve any graph/document disagreement using the source-of-truth hierarchy in `CLAUDE.md`.
5. Implement the smallest coherent change.
6. Run the relevant tests and Phase 0 gates.
7. Update source-of-truth documentation when measured evidence changes a capability or decision.
8. Refresh the graph after meaningful structural code/document changes when appropriate.

## Phase 0 use

Graphify should make Phase 0 easier to reason about, but it must not change Phase 0's purpose. The capability harness still has to measure the system directly.

Useful Graphify questions during Phase 0 include:

- What code paths can cause host pointer or keyboard injection?
- Which modules depend on Playwright/browser lifecycle code?
- What state-changing paths lack an independent verifier?
- Which historical BrowserAgent regression tests exercise tab binding, typing, refresh loops, ambiguous side effects, recovery, and resume behavior?
- What components would be affected by changing the `InteractionRouter` or adapter contracts?
- Which requirements in `BUILD_SPEC.md` do not yet have a test or harness implementation?

The answers help Claude navigate. Passing tests and recorded measurements decide whether a capability is accepted.

## Security and privacy

- Never commit API keys, tokens, credentials, cookies, session material, or `.env` contents into Graphify inputs or outputs.
- Inspect generated graph artifacts before committing them.
- Keep Graphify removable. ComputerAgent development, tests, and runtime must not depend on Graphify being installed.
- Treat inferred graph edges as hypotheses until verified against source code, documentation, or measured evidence.

## Success criterion

Graphify is successful here if a fresh Claude Code session can rapidly identify the relevant architecture, implementation paths, dependencies, tests, and rationale while still obeying the repository's explicit source-of-truth hierarchy. It should reduce rediscovery, not introduce a second architecture.