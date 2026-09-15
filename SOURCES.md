# BrowserAgentV2 Research Sources

**Snapshot:** 2026-09-15

This ledger tracks primary sources used to shape BrowserAgentV2. Prefer original papers, official documentation, source repositories, and benchmark maintainers over secondary summaries.

## Source-quality rules

1. Prefer official/current primary sources.
2. Record version/date when behavior is version-sensitive.
3. Distinguish documented behavior from our architectural inference.
4. Turn important claims into BrowserAgentV2 tests whenever possible.
5. If documentation conflicts with reproducible live behavior, preserve the experiment and document the discrepancy.
6. A benchmark score supports feasibility/comparison; it does not prove production reliability on arbitrary websites.

---

# Web-agent research papers and benchmarks

## Mind2Web — Towards a Generalist Agent for the Web

- Paper: https://arxiv.org/abs/2306.06070
- Repository: https://github.com/OSU-NLP-Group/Mind2Web

Findings used:
- 2,000+ tasks across 137 websites and 31 domains establish broad web-task diversity;
- raw HTML from real sites is often too large for an LLM;
- candidate-element filtering improves efficiency/effectiveness;
- cross-website/domain generalization is substantially harder than seen-site performance.

BrowserAgentV2 implication: compact/retrieved semantic observation rather than raw page dumps.

## WebArena

- Paper: https://arxiv.org/abs/2307.13854
- Project/repository: https://webarena.dev/ and https://github.com/web-arena-x/webarena

Findings used:
- realistic, reproducible, long-horizon web tasks are much harder than toy browsing;
- reported GPT-4 baseline task success was 14.41% compared with 78.24% human performance in the original paper.

Implication: end-to-end success must be measured independently from primitive success; one good demo has little evidentiary value.

## WebArena-Verified

- Repository: https://github.com/ServiceNow/webarena-verified

Findings used:
- audited tasks and deterministic scoring help reduce benchmark ambiguity;
- useful as a later external regression target once internal controlled tasks are stable.

## SeeAct — GPT-4V is a Generalist Web Agent, if Grounded

- Paper: https://arxiv.org/abs/2401.01614
- Repository: https://github.com/OSU-NLP-Group/SeeAct

Findings used:
- manual grounding substantially improves task completion relative to automatic grounding;
- grounding is a separable bottleneck from high-level planning/reasoning;
- combining textual/HTML and visual information can improve grounding.

Implication: target grounding receives a dedicated deterministic contract/test layer; vision is a fallback, not assumed default.

## WebVoyager

- ACL 2024 paper: https://aclanthology.org/2024.acl-long.371/
- Repository: https://github.com/MinorJerry/WebVoyager

Findings used:
- demonstrates useful end-to-end multimodal operation on real websites;
- supports keeping a future screenshot/vision fallback for controls not represented semantically.

## Agent-E

- Paper: https://arxiv.org/abs/2407.13032
- Repository: https://github.com/EmergenceAI/Agent-E

Findings used:
- hierarchical task reasoning;
- DOM distillation/denoising;
- observing changes after actions;
- reported improvements over previous methods on WebVoyager categories.

Implication: coarse plan/subgoal state + one immediate action; change summaries instead of repeated whole-history prompts.

## AgentOccam

- ICLR 2025 project/repository: https://github.com/amazon-science/AgentOccam

Findings used:
- comparatively simple observation/action-space alignment can produce a strong web-agent baseline;
- more reflection/multi-agent machinery is not automatically better.

Implication: BrowserAgentV2 defaults to one controller and one model rather than a planner/executor/verifier agent team.

## WebLINX

- ICML 2024 paper: https://proceedings.mlr.press/v235/lu24e.html
- Repository: https://github.com/McGill-NLP/weblinx

Findings used:
- 100K interactions over 150+ websites;
- real page context requires retrieval/pruning for practical processing;
- smaller fine-tuned models can be competitive on appropriate distributions;
- unseen-site generalization remains difficult.

Implication: context retrieval is a required architecture concern; local-model generalization must be measured rather than assumed.

## BrowserGym / AgentLab

- BrowserGym: https://github.com/ServiceNow/BrowserGym
- AgentLab: https://github.com/ServiceNow/AgentLab
- Ecosystem paper: https://arxiv.org/abs/2412.05467

Findings used:
- standardized observation/action spaces;
- reproducible trajectories/traces and benchmark infrastructure;
- systematic experiment harnesses are part of agent research, not an afterthought.

Implication: BrowserAgentV2 testing/trace schema is designed alongside the runtime.

## WorkArena / WorkArena++

- WorkArena repository: https://github.com/ServiceNow/WorkArena
- WorkArena++ paper: https://arxiv.org/abs/2407.05291

Findings used:
- compositional knowledge-work tasks expose weaknesses in planning, retrieval, contextual understanding, arithmetic and memory;
- real workflows require more than individual clicks.

Implication: explicit PlanState/subgoals and structured facts are necessary for complex tasks.

## AssistantBench

- Paper: https://arxiv.org/abs/2407.15711
- Project: https://assistantbench.github.io/

Findings used:
- realistic information-seeking/assistant tasks remain difficult for web agents;
- planning and memory improve performance on long, time-consuming tasks.

Implication: long research is a dedicated controller mode with evidence gaps/completeness rather than an oversized normal prompt.

## WebChoreArena

- Paper: https://arxiv.org/abs/2506.01952

Findings used:
- long tasks stress observation memory, calculation and long-term memory;
- strong models still have substantial room to improve.

Implication: 100+ page research should use structured external state and deterministic calculation rather than prompt accumulation.

## Online-Mind2Web

- Repository: https://github.com/OSU-NLP-Group/Online-Mind2Web

Findings used:
- live website tasks require ongoing maintenance;
- tasks can become invalid and CAPTCHAs/site changes alter evaluation;
- live-web success must distinguish agent failure from task/site invalidity.

Implication: internal controlled fixtures + separately classified live canaries.

## BrowserArena (2025)

- Paper: https://arxiv.org/abs/2510.02418

Findings used:
- live open-web head-to-head evaluation with step-level human feedback;
- recurring real-world failures include CAPTCHAs, pop-up/banner handling and direct navigation behavior;
- modern web agents remain brittle on mundane environment interactions.

Implication: live canaries, explicit pop-up/banner fixtures, CAPTCHA as human handoff, and typed step-level failure traces.

## WEBSERV (2025)

- Paper: https://arxiv.org/abs/2510.16252

Findings used:
- identifies noisy/excessive context and non-deterministic UI/network waiting as important web-agent environment problems;
- proposes compact site-agnostic browser representation and scalable controlled environments.

Implication: direct support for BrowserAgentV2's compact observation + deterministic BrowserKernel design and future resettable training environment.

## Web Agents with World Models

- Paper: https://arxiv.org/abs/2410.13232

Findings used:
- action-consequence awareness can improve web policy selection;
- transition-focused observation abstraction highlights state differences rather than huge repeated raw page states.

Implication: BrowserAgentV2 `change_summary` is both a context optimization and a useful decision signal; high-impact action consequence reasoning may become a later extension if deterministic policy/verification is insufficient.

---

# Open/local model evidence and training

## Qwen3

- Repository: https://github.com/QwenLM/Qwen3
- Function calling documentation: https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md

Findings used:
- tool/function calling is supported;
- Hermes-style tool interfaces are preferred in relevant deployments;
- stopword-based free-form ReAct parsing is explicitly problematic for reasoning models;
- thinking/non-thinking modes can be evaluated separately.

Implication: compare native tool calling vs one strict structured `Decision` schema; no regex/free-form action parsing.

## Ollama structured outputs

- Documentation: https://docs.ollama.com/capabilities/structured-outputs
- Blog/reference: https://ollama.com/blog/structured-outputs

Findings used:
- JSON Schema constrained outputs are supported;
- Pydantic/typed validation is practical;
- low/zero temperature can improve determinism for extraction/structured decisions.

Implication: strict model-output contract is practical locally.

## WebRL

- Paper: https://arxiv.org/abs/2411.02337

Findings used:
- web-specific reinforcement learning can dramatically improve open 8–9B-class models;
- reported WebArena-Lite improvements demonstrate that small/open web agents are trainable, but zero-shot competence should not be assumed.

Implication: Qwen3:8B has an explicit evaluation gate and a later fine-tuning/RL upgrade path.

## WebAgent-R1 (2025)

- Paper: https://arxiv.org/abs/2505.16421

Findings used:
- end-to-end multi-turn RL for web agents;
- reported Qwen-2.5-3B improvement from 6.1% to 33.9% and Llama-3.1-8B from 8.5% to 44.8% on WebArena-Lite;
- warm-up/behavior cloning and thinking/test-time interaction choices matter.

Implication: local small-model web competence can be trained substantially; poor zero-shot Qwen results should trigger model/policy improvement rather than browser-runtime hacks.

## AgentTrek

- Paper: https://arxiv.org/abs/2412.09605

Findings used:
- trajectory synthesis through guided replay of web tutorials can create useful GUI-agent training data;
- training on synthesized trajectories improves grounding/planning.

Implication: BrowserAgentV2 trace schema should support later safe/redacted trajectory export and tutorial/fixture-based data generation.

## DynaWeb (2026)

- Paper: https://arxiv.org/abs/2601.22149

Findings used:
- model-based RL can train/improve open web agents partly through a learned web world model and simulated rollouts;
- real expert trajectories can be mixed with synthetic/on-policy rollouts.

Implication: recording `observation_before -> action -> observation_after/change -> verification/reward` from day one preserves a future scalable training path.

---

# Playwright / browser runtime

## Playwright actionability

- https://playwright.dev/docs/actionability

Findings used:
- locator actions auto-wait for conditions such as visibility, stability, event reception and enabled/editable state;
- deterministic browser mechanics should use these semantics instead of arbitrary sleeps.

## Playwright locators

- https://playwright.dev/docs/locators

Findings used:
- role/label/text-oriented locators are generally preferred over brittle DOM paths;
- locators are re-resolved rather than storing long-lived element handles.

## Playwright authentication

- https://playwright.dev/docs/auth

Findings used:
- persisted authentication state can contain sensitive cookies/headers capable of impersonating a user;
- auth/profile artifacts must remain outside git/model context.

## Playwright pages/popups

- https://playwright.dev/python/docs/pages

Findings used:
- multiple pages/popups are first-class context events;
- page registry can capture new pages deterministically rather than relying on tab-order guessing.

## Playwright frames

- https://playwright.dev/docs/frames

Findings used:
- frame scope should be explicit in target identity;
- frame locators are required for nested content.

## Playwright dialogs

- https://playwright.dev/python/docs/dialogs

Findings used:
- modal dialogs can block browser execution;
- dialogs need explicit runtime state/handling rather than generic click retries.

## Playwright downloads

- https://playwright.dev/python/docs/downloads

Findings used:
- downloads are temporary and are removed when browser context closes unless explicitly saved;
- artifact persistence is a BrowserAgent responsibility.

## Playwright CDP attachment

- https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp

Critical finding:
- Playwright documents `connect_over_cdp()` as significantly lower fidelity than the Playwright protocol;
- it is Chromium-only and advanced behavior may be affected by how the browser was launched.

Implication: existing/daily-driver Chrome attachment is not the MVP default; use a dedicated Playwright-managed persistent profile first.

---

# Playwright MCP

- Introduction: https://playwright.dev/mcp/introduction
- Snapshots: https://playwright.dev/mcp/snapshots
- Forms: https://playwright.dev/mcp/tools/forms
- Tabs: https://playwright.dev/mcp/tools/tabs
- Dialogs: https://playwright.dev/mcp/tools/dialogs
- Files: https://playwright.dev/mcp/tools/files

Findings used:
- structured accessibility snapshots with interaction refs;
- refs are snapshot-scoped/stale refs fail rather than silently retargeting;
- fresh state follows actions;
- tabs/dialogs/forms/files are exposed as tools;
- frame-qualified refs can be represented;
- find/subtree operations can reduce page context.

Implication: Playwright MCP is the first BrowserKernel candidate, tested behind an adapter.

Security note:
- MCP convenience origin/file controls are useful guardrails but are not treated as the only security boundary;
- BrowserAgentV2 still applies its own PolicyEngine and constrained action schema.

Unsafe capabilities such as arbitrary browser code/evaluate are not exposed to the model in the MVP.

---

# Browser-agent implementation references

## Browser Use

- Repository: https://github.com/browser-use/browser-use

Finding used:
- modern browser grounding can combine accessibility, DOM/CDP, frames, visibility/layout and metadata rather than raw HTML alone.

## Stagehand

- Repository: https://github.com/browserbase/stagehand

Finding used:
- AI observation/discovery can coexist with deterministic action execution/replay;
- repeated successful workflows can trend toward determinism later.

Implication: progressive deterministic caching is a later optimization, not an MVP dependency.

---

# Security and indirect prompt injection

## AgentDojo

- Paper: https://arxiv.org/abs/2406.13352

Findings used:
- tool-using agents need both utility and security evaluation;
- indirect prompt injection is a concrete agent/tool threat, not a hypothetical prompt problem.

## InjecAgent

- ACL Findings paper: https://aclanthology.org/2024.findings-acl.624/
- arXiv: https://arxiv.org/abs/2403.02691

Findings used:
- tool-integrated agents are vulnerable to injected external instructions;
- stronger attacks materially increase success rates.

## BIPIA

- Paper: https://arxiv.org/abs/2312.14197

Findings used:
- LLMs often fail to distinguish trusted instructions from untrusted external content;
- boundary/reminder defenses help but do not establish complete security.

## OpenAI prompt-injection overview

- https://openai.com/safety/prompt-injections/

Finding used:
- layered defense, least privilege, and architecture-level boundaries are preferable to prompt-only mitigation.

BrowserAgentV2 implication across all security sources:
- webpage content cannot authorize new capabilities;
- action policy exists outside the model;
- secrets/filesystem are minimized;
- consequential actions and unexpected cross-origin disclosure are gated;
- security requires adversarial fixtures and cannot be declared solved by one benchmark.

---

# BrowserAgent old repository evidence

- Repository: https://github.com/Reshwant-Borra/BrowserAgent

Files directly audited:
- `README.md`
- `browser/playwright_backend.py`
- `memory/event_store.py`
- `agent/context_builder.py`
- `agent/verifier.py`
- `agent/loop_detector.py`
- `agent/security_policy.py`
- unit/integration/model test directories and benchmark fixtures

Old tests inspected include:
- `tests/unit/test_agent_loop_tab_wiring.py`
- `tests/integration/test_phase1_browser_actions.py`
- `tests/integration/test_cdp_attach.py`
- `tests/integration/test_phase2_verification_recovery.py`
- `tests/integration/test_phase3_crash_recovery.py`
- `tests/integration/test_phase4_long_horizon.py`

Findings recorded in:
- `01_RESEARCH/OLD_BROWSERAGENT_AUDIT.md`
- `04_TESTING/OLD_FAILURE_REGRESSION_MATRIX.md`

---

# Research interpretation rule

No paper or framework is copied wholesale. BrowserAgentV2 uses converging evidence to choose interfaces and experiments:

```text
paper/documented behavior
        ↓
architecture hypothesis
        ↓
controlled BrowserAgentV2 experiment
        ↓
recorded ADR/decision
        ↓
implementation + permanent regression test
```

That chain is required for any major architecture choice.
