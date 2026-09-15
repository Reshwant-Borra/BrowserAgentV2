# Local Model Strategy and Training Upgrade Path

**Primary question:** can Qwen3:8B be the intelligence layer for BrowserAgentV2 without forcing browser/runtime complexity to compensate for weak action selection?

**Current answer:** plausible, but unproven. The architecture must measure this directly and preserve an upgrade/training path.

---

# 1. Why Qwen3:8B is still a reasonable first model

Practical reasons:
- already runs locally on the target machine;
- avoids per-call API cost and privacy dependence;
- Qwen3 supports structured/function/tool-style interaction;
- Ollama supports JSON-schema structured outputs;
- the runtime is intentionally designed to reduce model burden by making browser mechanics deterministic.

Research reasons:
- WebRL reports large improvements for open 8–9B web agents after web-specific training;
- WebAgent-R1 reports Llama-3.1-8B reaching 44.8% on WebArena-Lite after multi-turn RL, and even Qwen-2.5-3B improving from 6.1% to 33.9%;
- AgentTrek shows synthesized GUI trajectories can improve planning/grounding;
- DynaWeb shows web world-model training can improve open web agents without requiring all rollouts on the live internet.

The lesson is **not** that Qwen3:8B will automatically be good enough. The lesson is that local small-model web competence is an improvable variable rather than a reason to redesign the entire runtime around a frontier model.

---

# 2. Separate model ability from browser reliability

We need independent metrics.

## BrowserKernel reliability

Measured with scripted decisions and no live model:
- target validity;
- action execution;
- stale-ref handling;
- tabs/frames/dialogs;
- typing;
- verification;
- crash recovery.

## Model policy quality

Measured on frozen Observation -> Decision examples without a browser:
- correct action;
- correct target;
- correct arguments;
- schema validity;
- safe ask/replan behavior.

## End-to-end agent quality

Measured only after both components meet individual gates.

This separation prevents a bad browser primitive from being mistaken for weak reasoning and prevents a weak model from being disguised by recovery heuristics.

---

# 3. Qwen interface experiment

Evaluate the same frozen examples using:

## Candidate A — strict single Decision JSON

Ollama schema constrains output to one Pydantic-compatible object.

Advantages:
- simple parsing;
- easy replay/evaluation;
- one canonical action contract independent of provider;
- no free-form action extraction.

Potential issue:
- schema may become large if too many action variants are exposed.

## Candidate B — native/Hermes-style tool calling

Advantages:
- model is explicitly trained/familiar with tool-call structure;
- arguments can be naturally typed.

Potential issue:
- runtime/provider-specific behavior may be harder to normalize.

## Rejected

Free-form ReAct text parsed with regex/stopwords.

Qwen's own documentation warns against stopword-based ReAct templates for reasoning models.

---

# 4. Action-space design matters more than prompt cleverness

AgentOccam, WEBSERV and broader web-agent research support keeping the action space compact.

Initial model-visible actions should be close to:

```text
NAVIGATE(url)
CLICK(target)
TYPE(target, text, submit?)
SELECT(target, option)
PRESS(target/page, key)
SCROLL(direction/amount)
BACK()
SWITCH_TAB(page_id)
FIND(query)
EXTRACT(target/query)
ASK_USER(question)
REQUEST_CONFIRMATION(summary)
REPLAN(reason)
FINISH(result)
```

Do not expose separate low-level actions for:
- mouse coordinates;
- JS evaluate;
- DOM query language;
- browser process lifecycle;
- refresh/reload recovery;
- raw filesystem paths.

Every extra action increases selection entropy and security surface.

---

# 5. Observation-space design for an 8B model

The model should not need to understand a raw browser DOM.

Preferred packet:

```text
TASK / SUCCESS CRITERIA
ACTIVE SUBGOAL
RELEVANT FACTS
LAST VERIFIED TRANSITION
PAGE URL / TITLE / TABS
CHANGE SUMMARY
RELEVANT SEMANTIC ELEMENTS
SMALL RELEVANT TEXT BLOCKS
AVAILABLE DECISION SCHEMA
```

Use stable, concise IDs and predictable ordering.

This makes the model task closer to **classification + bounded reasoning** than open-ended GUI interpretation.

---

# 6. Thinking vs non-thinking policy

Qwen3 can operate with thinking enabled/disabled depending on serving configuration.

Experiment with three modes:

### Mode 1 — non-thinking action policy
Use for obvious local choices such as clicking a uniquely named button or filling a field.

Goal: low latency, less verbose internal reasoning.

### Mode 2 — thinking for replan/ambiguity
Use only when:
- multiple plausible paths;
- task decomposition;
- contradictory facts;
- repeated failure/replan;
- consequential decision preview.

### Mode 3 — always thinking baseline
Needed for comparison.

Choose using measured end-to-end accuracy/latency rather than intuition.

---

# 7. Frozen decision dataset

Before browser autonomy, create 100-300 examples.

Each case stores:

```json
{
  "case_id":"...",
  "task":"...",
  "subgoal":"...",
  "facts":[],
  "observation":{},
  "allowed_actions":[],
  "gold_decisions":[...],
  "unsafe_decisions":[...],
  "difficulty":"easy|medium|hard"
}
```

Allow multiple gold decisions when several safe next moves are equivalent.

Categories:
- click/navigation;
- forms/search;
- extraction;
- tabs/frames;
- login handoff;
- stale/no target;
- ask clarification;
- replan;
- finish;
- malicious prompt injection;
- consequential confirmation.

---

# 8. Model thresholds and response to failure

Initial controlled threshold before autonomous rollout:

```text
schema validity            >= 99%
nonexistent target output   0% after validation
correct action+target       >= 90% easy/medium set
policy bypass success       0% security set
```

These are engineering starting thresholds, not universal scientific thresholds.

## If schema validity is poor

Fix serving/schema/tool interface.
Do not alter BrowserKernel.

## If target/action accuracy is poor

Try, in order:
1. simplify observation;
2. improve element names/roles/context;
3. reduce action space;
4. compare tool calling vs JSON schema;
5. tune thinking mode/prompt examples;
6. evaluate a somewhat larger local model;
7. begin trajectory fine-tuning.

## If planning is poor but local action selection is good

Keep one action model but consider separate/coarser planning invocation or stronger model for plan creation only.
Do not immediately create multiple autonomous agents.

---

# 9. Trajectory data collection from day one

Every successful/failed run should produce a training-friendly redacted record:

```text
task/subgoal
observation_before
relevant fact context
model Decision
policy result
action execution result
observation_after/change summary
verification result
final task success
failure classification
```

Important:
- secrets/cookies/passwords/private page data must not be exported into training sets by default;
- training export is an explicit separate pipeline;
- raw local traces remain private runtime data.

---

# 10. Stage 1 model improvement — supervised decision tuning

If enough high-quality decisions exist, first try supervised fine-tuning/LoRA on:

```text
(context packet) -> Decision
```

This is simpler and safer than RL initially because:
- gold outputs are clear;
- evaluation is offline/reproducible;
- browser environment does not need thousands of live rollouts.

Collect hard-negative cases from model failures:
- wrong target;
- premature finish;
- unsafe action;
- repeated action;
- failure to ask user.

---

# 11. Stage 2 — trajectory synthesis

AgentTrek suggests web tutorials/instructions can seed multi-step training trajectories.

Potential BrowserAgentV2 version:

1. collect tutorials/test workflows for controlled/local web apps;
2. turn them into task goals;
3. execute with a stronger teacher or scripted solution;
4. verify deterministically;
5. retain only successful/valid trajectories;
6. train Qwen policy on observation/action sequences.

Keep this in controlled environments first; do not scrape private authenticated user activity into training data.

---

# 12. Stage 3 — reinforcement learning

WebRL and WebAgent-R1 provide evidence that multi-turn web RL can substantially improve small/open models.

Prerequisites before BrowserAgentV2 RL:
- stable resettable environment;
- deterministic task reward/success evaluation;
- action/observation schema frozen enough to train against;
- trajectory logging;
- many controlled tasks;
- compute budget defined.

Potential rewards:

```text
+ task success
+ correct subgoal completion
- unsafe/policy action
- invalid target
- unnecessary repeated action
- excessive steps (small penalty)
```

Avoid shaping the reward so strongly that the model learns benchmark-specific shortcuts.

---

# 13. Stage 4 — world-model / simulated rollout research

DynaWeb and world-model web-agent work show a future path where transitions can be modeled and training can happen partly in simulated web state.

BrowserAgentV2's `observation_before -> action -> change_summary/observation_after` records are intentionally compatible with this future direction.

This is research-level work and **not** part of the two-day build.

---

# 14. Model escalation without architecture rewrite

Possible deployment ladder:

```text
Qwen3:8B local
   |
   +--> optimized/fine-tuned Qwen3:8B
   |
   +--> larger local model on capable hardware
   |
   +--> optional stronger remote model for difficult planning (user-configured)
```

All use the same `ModelAdapter -> Decision` contract.

A model change should not touch:
- BrowserKernel;
- state/event store;
- verifier;
- policy engine;
- FactStore;
- human handoff.

---

# 15. Avoid model overfitting to our fixtures

The user's concern about training on a small set of example tasks is correct.

Mitigation:
- train/evaluate on mechanisms, not named sites;
- generate many layout/content variants per fixture;
- hold out whole sites/templates;
- randomize labels/order/data;
- maintain unseen-task validation set;
- include live canaries separately;
- never add prompt examples solely for benchmark test cases after seeing failures without adding equivalent held-out evaluation.

The goal is a policy that understands browser primitives and task decomposition, not one that memorizes “Canvas workflow” or “Japan travel workflow.”

---

# 16. Model-related architecture risk ranking

| Risk | Severity | Detection | Countermeasure |
|---|---:|---|---|
| zero-shot action accuracy insufficient | high | frozen Decision eval | simplify state/action; fine-tune/upgrade |
| unseen-site generalization weak | high | held-out/live suite | diverse trajectory data; training |
| hallucinated target/action | medium-high | schema/target validation | fail closed + reobserve/redecide |
| slow inference | medium | latency metrics | non-thinking mode, compact context, caching |
| repeated loops | medium | progress detector | replan then fail/ask user |
| prompt injection follows page text | high | adversarial fixtures | PolicyEngine/capability isolation |
| premature finish | high | success-criteria verifier | controller rejects unsupported FINISH |
| overfitting to fixtures | high | held-out templates/live canaries | randomized broad dataset |

---

# Final model strategy

Treat the local model as a replaceable **decision policy**, not as the operating system of the agent.

The two-day project should answer:

> “Can Qwen3:8B reliably choose the next bounded action given a good observation?”

If yes, build on it.

If no, improve or train the model policy while keeping the deterministic BrowserAgentV2 runtime intact.

That is a much more stable development path than reshaping the browser architecture every time the model makes a mistake.
