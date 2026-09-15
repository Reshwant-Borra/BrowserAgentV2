# BrowserAgentV2 — Research & Architecture Knowledge Base

**Research snapshot:** 2026-09-15  
**Status:** active research; implementation should not begin until the open decision gates are resolved.

## Mission

Build a small, general-purpose local browser-agent kernel whose browser mechanics are deterministic, whose model context stays bounded, whose failures are classified rather than hidden behind retries, and whose architecture can later expand toward broad Comet-like tasks without being rewritten per example.

This repository is deliberately **research-first**. It is not an implementation dump and it is not a sequence of giant Codex prompts.

## Current strongest architecture

```text
User Goal
   |
   v
TaskController <-------------------- Human Takeover / Confirmation
   |
   +--> ContextBuilder --> Qwen/Ollama ModelAdapter
   |                         |
   |                         v
   +----------------> Policy + Schema Validator
   |                         |
   |                         v
   +----------------> BrowserKernel interface
                              |
                              v
                      Playwright MCP adapter
                              |
                              v
                    dedicated persistent browser
   |
   +--> Verifier / Progress Detector
   +--> SQLite StateStore + traces + provenance facts
   +-------------------------------> next step
```

The key revision from the earlier design is that we should **test Playwright MCP as the browser kernel instead of immediately rebuilding snapshot/ref/tab/form machinery ourselves**. The application remains protected by a `BrowserKernel` abstraction so we can replace MCP with custom Playwright if the spike exposes a real blocker.

## Core rules

1. The model decides **what** to attempt; deterministic infrastructure controls **how** browser mechanics execute.
2. No model-callable refresh/reload in MVP.
3. No arbitrary browser JavaScript, shell, or unsafe code tool in MVP.
4. One state-changing model action per controller step.
5. Every target is observation-scoped; stale targets are rejected, never guessed.
6. Typing always targets an explicit element and is verified.
7. Browser/API success is not task success; postconditions are verified.
8. No blind retry of state-changing actions.
9. A dedicated persistent browser profile is the MVP default.
10. Login/MFA/CAPTCHA use human takeover and fresh observation on resume.
11. Webpage content is untrusted data, not instruction authority.
12. Full browsing history is stored for debugging but is not fed back to Qwen.
13. Research uses provenance-bearing facts rather than stuffing pages into context.
14. Generality is tested by mechanisms and diverse tasks, not by hard-coding example sites.
15. A feature is not accepted until repeated deterministic tests pass.

## Decision gates still open

Before implementation is frozen, we must resolve:

- ADR-001: Playwright MCP kernel spike.
- ADR-003: Qwen native tool calling vs structured Decision output.
- exact browser-kernel tool whitelist/version pin.
- ambiguous-side-effect resume semantics.
- first-version upload/download policy.
- old BrowserAgent audit based on its actual repository, not remembered prompts.

See `06_OPEN_QUESTIONS/RESEARCH_GAPS.md`.

## Recommended reading order

1. `00_PROJECT/VISION.md`
2. `00_PROJECT/REQUIREMENTS.md`
3. `00_PROJECT/TWO_DAY_TARGET.md`
4. `01_RESEARCH/RESEARCH_INDEX.md`
5. `01_RESEARCH/PLAYWRIGHT_MCP_AS_KERNEL.md`
6. `02_ARCHITECTURE/FINAL_RECOMMENDED_ARCHITECTURE.md`
7. `02_ARCHITECTURE/VERIFICATION_AND_RETRY_POLICY.md`
8. `03_DECISIONS/ADR-001-BROWSER-KERNEL.md`
9. `04_TESTING/TWO_DAY_EXIT_GATES.md`
10. `05_IMPLEMENTATION/TWO_DAY_EXECUTION_PLAN_V2.md`
11. `06_OPEN_QUESTIONS/RESEARCH_GAPS.md`

## Folder map

- `00_PROJECT/` — vision, requirements, non-goals, two-day product target
- `01_RESEARCH/` — frameworks, browser mechanics, model/context/memory/security research
- `02_ARCHITECTURE/` — proposed system contracts and runtime policies
- `03_DECISIONS/` — ADRs, accepted/rejected approaches
- `04_TESTING/` — deterministic fixtures, stress tests, model eval, failure injection, exit gates
- `05_IMPLEMENTATION/` — build order and two-day execution plan
- `06_OPEN_QUESTIONS/` — unresolved research/experiments before final freeze

## Philosophy

When implementation evidence contradicts a document, update the document and record the decision. Do not silently add another recovery layer or prompt patch. The purpose of this knowledge base is to keep architecture, evidence, and implementation aligned.
