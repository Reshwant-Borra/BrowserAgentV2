# Research Sources

This file tracks primary sources used to shape the BrowserAgentV2 research documents. Prefer original project documentation, source repositories, and papers over secondary summaries.

## Playwright / Playwright MCP

- Playwright actionability: https://playwright.dev/docs/actionability
- Playwright locators: https://playwright.dev/docs/locators
- Playwright authentication/state: https://playwright.dev/docs/auth
- Playwright MCP snapshots: https://playwright.dev/mcp/snapshots
- Playwright MCP profile/state: https://playwright.dev/mcp/configuration/user-profile

Key findings used:

- browser actions should rely on locator/actionability semantics rather than arbitrary sleeps;
- MCP exposes accessibility snapshots with interaction refs;
- persistent profiles can retain cookies/login state;
- browser/profile lifecycle and stale targets need explicit ownership.

## Browser Use

- Main repository: https://github.com/browser-use/browser-use
- DOM service: https://github.com/browser-use/browser-use/blob/main/browser_use/dom/service.py

Key finding used: modern grounding can combine accessibility trees, DOM/CDP information, frames, visibility/layout, and selected metadata instead of forcing the model to consume raw HTML.

## Stagehand

- Main repository: https://github.com/browserbase/stagehand
- Python SDK README: https://github.com/browserbase/stagehand/blob/main/packages/sdk-python/README.md
- Documentation: https://github.com/browserbase/stagehand/tree/main/packages/docs

Key finding used: AI-powered observation/discovery can coexist with deterministic locator execution; repeatable workflows should trend toward determinism rather than permanently relying on natural-language actions.

## Agent-E

- Paper: https://arxiv.org/abs/2407.13032
- Repository: https://github.com/EmergenceAI/Agent-E

Key findings used: hierarchical task reasoning and observing changes after actions can reduce context bloat and improve control-loop clarity.

## BrowserGym / AgentLab

- BrowserGym: https://github.com/ServiceNow/BrowserGym
- AgentLab: https://github.com/ServiceNow/AgentLab

Key finding used: observation/action standardization, reproducible traces, and benchmark infrastructure should be designed alongside the agent rather than added later.

## Web-agent benchmarks

- WebArena paper: https://arxiv.org/abs/2307.13854
- Online-Mind2Web: https://github.com/OSU-NLP-Group/Online-Mind2Web
- WorkArena: https://github.com/ServiceNow/WorkArena
- BrowserGym benchmark ecosystem: https://github.com/ServiceNow/BrowserGym

Key findings used: live websites drift; authentication, tabs, forms, long-horizon composition, and recovery materially affect real task reliability; benchmark validity must be tracked over time.

## Qwen

- Qwen3 repository: https://github.com/QwenLM/Qwen3
- Function-calling documentation: https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md

Key findings used: browser action output should use native tools/function calling or strict structured output rather than fragile free-form ReAct parsing; local-model context/action surfaces should remain compact.

## Security / prompt injection

- ServiceNow DoomArena: https://github.com/ServiceNow/DoomArena
- WASP-related paper reference used in research: https://arxiv.org/abs/2504.18575
- OpenAI prompt-injection overview used for layered-defense framing: https://openai.com/safety/prompt-injections/

Key findings used: webpage content is untrusted input; capability minimization, explicit authority boundaries, confirmations, and secret isolation are architectural requirements rather than prompt-only mitigations.

## Source-quality rules for future research

1. Prefer official docs/current source repositories.
2. Record version/date when a behavior is version-sensitive.
3. Distinguish documented behavior from our architectural inference.
4. Convert important claims into a test whenever possible.
5. If a source conflicts with live behavior, trust the reproducible experiment and document the discrepancy.
