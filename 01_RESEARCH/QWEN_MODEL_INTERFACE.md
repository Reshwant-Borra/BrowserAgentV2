# Qwen / Local Model Interface Research

**Status:** active research; final interface must be benchmarked before architecture freeze.

## Baseline

The existing local target is Qwen3 8B through Ollama. The browser architecture must not assume that an 8B local model can reliably reason over huge DOMs, long transcripts, or an unrestricted action space.

That means model quality is improved partly by system design: compact observations, small schemas, explicit state, and deterministic execution.

## Do not parse free-form ReAct text

Qwen's function-calling documentation warns about fragile stopword/template-based tool parsing for reasoning models. BrowserAgentV2 should use either native tool/function calling or one strict structured-output schema.

Source:
- https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md

## Proposed `Decision` schema

The model should produce exactly one decision per controller step. Conceptually:

```json
{
  "kind": "browser_action | extract | replan | ask_user | finish | fail",
  "action": "click | fill | press | select | navigate | scroll | back | switch_tab | ...",
  "target": "observation-scoped ref or null",
  "text": "optional",
  "reason": "short machine-visible rationale",
  "expected_outcome": "short postcondition"
}
```

The exact schema should remain deliberately small. Unsupported fields/actions are rejected before browser execution.

## One state-changing action per turn

For the MVP, Qwen should select at most one state-changing browser action per controller cycle. This avoids planning against refs that may become stale after the first action.

Read-only extraction may later be batched if all targets belong to the same observation.

## Thinking mode

Qwen3 supports different reasoning behavior. We should benchmark two operating modes rather than assume one is best:

- routine action selection with minimal/disabled extended thinking;
- higher-reasoning mode for replanning, ambiguous pages, or research synthesis.

The controller can eventually escalate reasoning only when needed, but that is an optimization after correctness.

## Required model evaluation before integration

Create a frozen dataset of 50–100 browser observations with known correct next decisions. Include:

- search fields;
- duplicate buttons;
- stale refs;
- tabs;
- dialogs;
- forms;
- results pages;
- pages with irrelevant prompt-like text;
- cases requiring `ask_user`;
- cases where the correct action is to stop/replan.

Compare:

1. native Qwen/Ollama tool calling;
2. strict JSON/structured `Decision` output.

Measure:

- schema-valid rate;
- correct action rate;
- correct target rate;
- unsupported-action hallucinations;
- accidental high-impact actions;
- latency;
- prompt size sensitivity.

Pick the interface based on data.

## Invalid output policy

Invalid model output must never partially execute. The controller should:

1. parse/validate;
2. reject if invalid;
3. provide a compact validation error;
4. allow a bounded re-decision;
5. fail/replan if repeated invalid outputs continue.

## Model independence

The `ModelAdapter` should isolate Qwen/Ollama from the rest of the application. A later model swap must not change BrowserKernel, StateStore, verifier, or task-state schemas.

## Main principle

Do not compensate for a local model by making the browser layer more permissive. Make the environment easier to reason about and the allowed decisions harder to misuse.
