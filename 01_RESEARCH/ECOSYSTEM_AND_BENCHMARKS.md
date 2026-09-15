# Browser-Agent Ecosystem and Benchmark Research

**Status:** active research

## Why study existing systems

BrowserAgentV2 should not reimplement solved problems or copy one framework wholesale. The purpose of this survey is to identify recurring design patterns that survive across projects.

## Playwright MCP

Useful pattern: accessibility snapshot → element ref → deterministic action. This reduces the model's need to reason over raw HTML or screen coordinates and creates a narrow action surface.

Source: https://playwright.dev/mcp/snapshots

## Browser Use

Useful pattern: enrich accessibility/DOM information using CDP and frame/layout data. Browser Use demonstrates that semantic accessibility data is strong but not always sufficient on complex pages.

Source: https://github.com/browser-use/browser-use

## Stagehand

Useful pattern: mix AI discovery with deterministic execution. Stagehand exposes `observe`, `act`, and `extract`, while also allowing Playwright-style locators for repeatable actions. This supports a core BrowserAgentV2 rule: the system should become more deterministic as it learns what needs to be done.

Source: https://github.com/browserbase/stagehand

## Agent-E

Useful pattern: hierarchical reasoning and observing what changed after an action instead of repeatedly replaying all prior state to the model. BrowserAgentV2 should compute compact post-action change summaries.

Sources:
- https://arxiv.org/abs/2407.13032
- https://github.com/EmergenceAI/Agent-E

## BrowserGym and AgentLab

BrowserGym standardizes web-agent observations/actions and includes benchmark families such as MiniWoB, WebArena, WebArena-Verified, VisualWebArena, WorkArena, AssistantBench, WebLINX, OpenApps, and TimeWarp. AgentLab adds reproducible experiment execution and trace analysis.

The lesson is that **evaluation infrastructure is part of the architecture**, not something added after the demo works.

Sources:
- https://github.com/ServiceNow/BrowserGym
- https://github.com/ServiceNow/AgentLab

## Live-web benchmarks

Online-Mind2Web evaluates hundreds of tasks across live websites. Live benchmarks are important because real sites drift, add authentication, change layouts, and introduce anti-automation challenges. A task can become impossible even if the agent architecture did not regress.

Source: https://github.com/OSU-NLP-Group/Online-Mind2Web

## What benchmarks teach us

A browser agent needs several evaluation layers:

### Level 0 — deterministic primitive tests

No LLM. Navigation, fill, click, select, scrolling, tabs, popup detection, stale refs, pause/resume, and verification.

### Level 1 — stable synthetic tasks

Short 1–5 action tasks on controlled pages.

### Level 2 — controlled long-horizon tasks

10–30 actions, tabs, dynamic content, intentional failures, and state recovery.

### Level 3 — authenticated user workflows

Manual login handoff followed by ordinary extraction/navigation.

### Level 4 — sampled live-web tasks

A fixed manifest of diverse public tasks, dated and checked for validity before interpreting failures.

### Level 5 — adversarial/security tests

Prompt injection, suspicious cross-domain instructions, secret requests, and high-impact-action confirmation.

## Metrics beyond pass/fail

Track:

- task success;
- primitive action success rate;
- verified vs unverified actions;
- retries per task;
- stale-ref attempts;
- invalid model outputs;
- unnecessary navigation/refresh count;
- observation/context size;
- human handoffs;
- recovery success after injected failures;
- total steps;
- safety/policy violations.

## Architectural synthesis

Across the ecosystem, the strongest recurring pattern is not “give the model more browser freedom.” It is:

1. structured current observation;
2. constrained actions;
3. deterministic browser mechanics;
4. explicit state/checkpoints;
5. post-action verification;
6. bounded recovery;
7. strong traces/evaluation.

BrowserAgentV2 should use that as its baseline rather than optimizing around a few handpicked task examples.
