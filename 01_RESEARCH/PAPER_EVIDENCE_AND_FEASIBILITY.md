# Paper Evidence and Feasibility

**Status:** research-backed design evidence, not a claim that the final system is solved.

## Executive conclusion

A general browser agent is technically feasible, but the research literature strongly argues against treating it as "one LLM prompt plus Playwright." The evidence supports a layered design with compact observations, constrained actions, deterministic execution, explicit verification, bounded memory, and human intervention for authentication/security boundaries.

The literature also gives an important warning: impressive offline or curated benchmark results do not imply robust live-web performance. Real websites drift, authentication expires, DOMs change, CAPTCHAs appear, and long-horizon tasks amplify small errors. BrowserAgentV2 therefore needs both an architecture and a validation discipline.

## Evidence map

| Research | What it demonstrates | Direct implication for BrowserAgentV2 |
|---|---|---|
| Mind2Web (NeurIPS 2023) | General web tasks span many sites/domains; raw HTML is too large and element filtering improves effectiveness/efficiency. | Do not feed whole pages to Qwen. Build a compact semantic observation and retrieval layer. |
| WebArena (2023) | Realistic long-horizon web tasks are much harder than toy tasks; early GPT-4 agent success was 14.41% vs 78.24% human. | Treat end-to-end reliability as the real metric; one successful demo proves little. |
| SeeAct (ICML 2024) | GPT-4V could complete 51.1% of live tasks when textual plans were manually grounded; automatic grounding remained the bottleneck. | Grounding/action targeting deserves deterministic infrastructure and dedicated tests. |
| WebVoyager (ACL 2024) | A multimodal real-web agent reached 59.1% on its benchmark, showing useful end-to-end web automation is possible. | Vision should exist as a fallback for visual-only controls, not necessarily the primary action mode. |
| Agent-E (2024) | Hierarchical control, DOM distillation, and change observations improved web-agent performance by 10-30% over several prior systems on WebVoyager categories. | Separate task/subgoal reasoning from browser mechanics; surface changes rather than repeatedly dumping full history. |
| AgentOccam (ICLR 2025) | A comparatively simple agent became a strong baseline by aligning observation/action spaces with what LLMs handle well. | Prefer a small, clear action/observation contract over adding agent roles and recovery subsystems. |
| WebLINX (ICML 2024) | 100K interactions over 150+ sites; retrieval-style pruning of HTML is needed for real-time context. Smaller fine-tuned models can beat zero-shot models on seen distributions, but generalization to unseen sites is hard. | Compact retrieval is essential; do not assume a small local model generalizes without measured evaluation. |
| BrowserGym/AgentLab (2024) | Standard observation/action spaces and reproducible experiment infrastructure enable meaningful web-agent evaluation. | Testing/trace schema is part of the product architecture, not a later QA add-on. |
| AssistantBench (2024) | Realistic, time-consuming web research tasks remain difficult; prior web agents were near zero and planning/memory improved performance. | Long research needs dedicated planning, provenance, memory, and completeness checks after the navigation loop is stable. |
| WorkArena++ (NeurIPS 2024) | 682 compositional knowledge-work tasks expose planning, retrieval, arithmetic, contextual understanding, and memory weaknesses. | Complex workflows should be decomposed into explicit subgoals with typed completion criteria. |
| WebRL (2024) | Web-specific training improved open 8-9B models dramatically on WebArena-Lite (e.g. Llama-3.1-8B 4.8% -> 42.4%). | A local model is plausible, but Qwen3:8B zero-shot is a hypothesis. Preserve an upgrade/fine-tune path. |
| Online-Mind2Web (COLM 2025) | Live-web evaluation requires task maintenance; tasks became invalid or hit CAPTCHAs as sites changed. | A real-world regression suite must distinguish agent failure from website/benchmark invalidity. |
| WebChoreArena (2025) | Massive observation memory, calculation, and long-term memory make browser tasks substantially harder even for strong models. | Do not build "100-page research" by stuffing more text into context. Use structured facts and external computation. |
| WebArena-Verified (2025/2026) | Audited tasks and deterministic scoring reduce benchmark/evaluator ambiguity. | Prefer deterministic task-specific evaluation where possible instead of letting the agent judge itself. |
| AgentDojo / InjecAgent / BIPIA | Tool agents are materially vulnerable to indirect prompt injection from untrusted external content. | Web content must never gain instruction authority. Add capability/policy boundaries outside the model. |

## What the papers support strongly

### 1. Compact observations are necessary

Mind2Web reports that raw HTML from real pages is often too large for an LLM, and that filtering with a smaller model improves effectiveness and efficiency. WebLINX independently uses retrieval-style element ranking because entire real pages cannot be processed efficiently in real time.

**Architecture consequence:** BrowserAgentV2 should make the `ContextBuilder` responsible for selecting a bounded slice of the current observation. The browser runtime may collect rich state, but the model should receive only relevant semantic elements, page metadata, changes, and task facts.

### 2. Grounding is a first-class problem

SeeAct is especially relevant: the model could plan substantially better than it could reliably ground plans to live page actions. With manual grounding, the live success rate was much higher, demonstrating that model reasoning and browser targeting are separable failure sources.

**Architecture consequence:** the model should select from observation-scoped targets; it should not invent CSS/XPath or hold stale element handles. Grounding failures must be measurable independently of planning failures.

### 3. Simplicity can outperform agent-system complexity

AgentOccam is evidence against assuming that more planner roles, reflection loops, or search branches automatically improve performance. Its core contribution is aligning observations and actions with forms the model can process reliably.

**Architecture consequence:** start with one controller and one model decision per step. Add a subsystem only when a reproducible failing test establishes the need.

### 4. Hierarchical task decomposition is useful for genuinely compositional work

Agent-E and WorkArena++ show the value/necessity of reasoning over larger task structure. This does not require a multi-agent architecture. A single controller can maintain a typed plan/subgoal list while still requesting one immediate browser decision at a time.

**Architecture consequence:** maintain two levels:

```text
Task plan / subgoal state
        ↓
one immediate browser/read decision
```

Do not make the browser-execution model simultaneously regenerate the entire task plan every action.

### 5. Change observations are useful

Agent-E explicitly identifies change observation as a design improvement. This matches BrowserAgentV2's need to avoid feeding repeated full-page text after every click.

**Architecture consequence:** store full observations for debugging, but construct a change summary for the model: URL/title changes, new/removed semantic nodes, changed field values, new tabs/dialogs, and important text deltas.

### 6. An open/local model can be viable, but training matters

WebRL is the strongest evidence for the local-model direction. It demonstrates that open 8-9B-class models can achieve substantial browser competence after task-specific reinforcement learning. It does **not** show that any off-the-shelf 8B model will be strong enough without training.

**Architecture consequence:** Qwen3:8B remains the first model because it is already local and fast on the target hardware, but every model dependency is behind `ModelAdapter`. If frozen action-selection evaluations show inadequate performance, the plan allows:

1. prompt/schema optimization;
2. larger local model when hardware permits;
3. fine-tuning/trajectory training later;
4. an optional stronger remote model for diagnosis, not as an architectural dependency.

### 7. Long research needs memory outside the prompt

AssistantBench and WebChoreArena directly motivate structured planning, memory, provenance, and calculation. The lesson is not "use a vector DB immediately"; it is that information must persist independently of the current chat context.

**Architecture consequence:** facts/evidence live in SQLite with provenance and structured keys. The model receives a retrieved working set, not every page visited.

### 8. Live-web evaluation is mandatory

WebArena is reproducible but simulated. Online-Mind2Web demonstrates why live evaluation matters: websites change, CAPTCHAs appear, tasks become invalid, and prior traces stop matching reality.

**Architecture consequence:** BrowserAgentV2 needs both controlled fixtures and live-web canaries. Controlled fixtures diagnose the agent; live canaries diagnose deployment realism.

## What the papers do NOT prove

The literature does **not** prove that:

- Qwen3:8B zero-shot will reliably execute arbitrary browser tasks;
- accessibility-tree-only observation covers every modern website;
- Playwright MCP is better than direct Playwright for this exact product;
- one verifier rule generalizes to every website;
- prompt injection can be solved by a system prompt;
- a browser agent can run indefinitely without human intervention;
- passing WebArena means the agent will succeed on Canvas, Google Calendar, banking-style sites, or arbitrary authenticated apps.

Those are engineering questions that must be resolved through BrowserAgentV2's own tests.

## Feasibility rating by subsystem

| Subsystem | Confidence | Reason |
|---|---:|---|
| Deterministic browser primitives | High | Mature Playwright runtime, auto-waiting, locator semantics, tabs/frames/download events. |
| Compact semantic observations | High | Supported by Playwright MCP, Mind2Web, WebLINX, BrowserGym, AgentOccam. |
| Schema-constrained action selection | High | Supported by modern function-calling interfaces and Qwen3 tooling. |
| Human login/MFA handoff | High | Straightforward state-machine behavior; avoids brittle auth automation. |
| Crash-safe state/trace | High | Ordinary SQLite/event/checkpoint engineering; previous repo already has working concepts. |
| Short multi-step tasks | Medium-high | Demonstrated broadly in research, but model quality determines success rate. |
| Arbitrary unseen website generalization | Medium | Research repeatedly shows substantial unseen-site degradation. |
| Long 100+ page research | Medium | Demonstrated as possible in specialized systems, but memory/completeness are still active research problems. |
| Zero-shot Qwen3:8B as sole intelligence layer | Medium-low until measured | Open 8B models can work when trained; no evidence yet that this exact zero-shot model meets our target. |
| Fully autonomous high-impact actions | Low / intentionally not a target | Security, ambiguity, authentication, and prompt injection require explicit boundaries. |

## Research-backed design thesis

The most defensible BrowserAgentV2 thesis is:

> **Build a deterministic browser runtime and durable task state first; use the LLM as a bounded decision policy over a carefully designed observation/action space; verify every important effect outside the LLM; escalate uncertainty to replanning or the user; treat long-memory and vision as explicit extensions rather than hidden prompt growth.**

This combines the strongest recurring patterns across Mind2Web, SeeAct, Agent-E, AgentOccam, BrowserGym, WebLINX, AssistantBench, WebRL, and the security literature.

## Primary sources

- Mind2Web: https://arxiv.org/abs/2306.06070
- WebArena: https://arxiv.org/abs/2307.13854
- SeeAct: https://arxiv.org/abs/2401.01614
- WebVoyager: https://aclanthology.org/2024.acl-long.371/
- Agent-E: https://arxiv.org/abs/2407.13032
- AgentOccam: https://github.com/amazon-science/AgentOccam
- WebLINX: https://proceedings.mlr.press/v235/lu24e.html
- BrowserGym ecosystem: https://arxiv.org/abs/2412.05467
- AssistantBench: https://arxiv.org/abs/2407.15711
- WorkArena++: https://arxiv.org/abs/2407.05291
- WebRL: https://arxiv.org/abs/2411.02337
- Online-Mind2Web: https://github.com/OSU-NLP-Group/Online-Mind2Web
- WebChoreArena: https://arxiv.org/abs/2506.01952
- WebArena-Verified: https://github.com/ServiceNow/webarena-verified
- AgentDojo: https://arxiv.org/abs/2406.13352
- InjecAgent: https://aclanthology.org/2024.findings-acl.624/
- BIPIA: https://arxiv.org/abs/2312.14197
