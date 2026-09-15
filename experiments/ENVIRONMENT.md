# Campaign environment

Every `results/*.json` embeds its own environment capture. This is the shared
summary for the whole P0 campaign. Machine-readable copy:
[`_env/campaign_environment.json`](_env/campaign_environment.json).

## Machine

| | |
|---|---|
| OS | Windows 11, build 10.0.26200 (AMD64) |
| CPU | Intel Core, 28 logical processors |
| GPU | NVIDIA GeForce RTX 4070, 12282 MiB, driver 610.60 |
| Python | 3.13.2 |
| Node | v24.15.0 |

## Browser runtime

| | |
|---|---|
| Playwright (Python) | 1.62.0 |
| Chromium | 151.0.7922.34 (Playwright-bundled, `chromium-1234`) |
| `@playwright/mcp` | 0.0.81 (pinned in [`package.json`](package.json)) |
| MCP server identity | `Playwright 1.64.0-alpha-2026-09-14` |
| Profile | dedicated Playwright-managed persistent context, fresh per case |
| Headless | yes, for every experiment |

## Local model

| | |
|---|---|
| Runtime | Ollama 0.34.0, `http://127.0.0.1:11434` |
| Model tag | `qwen3:8b` |
| Digest | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` |
| Parameters | 8.2B (`general.parameter_count` 8,190,735,360) |
| Quantization | Q4_K_M, GGUF |
| Architecture | qwen3 — 36 blocks, 4096 embedding, 32 heads, 8 KV heads |
| Native context length | 40960 |
| Declared capabilities | `completion`, `tools`, `thinking` |

No cloud model was used for any decision or for any grading anywhere in this
campaign. Every score is produced by
[`common/grading.py`](common/grading.py), which is deterministic.

## Inference settings

Identical across both interface arms; the only variable is the output mechanism
and, where stated, thinking mode.

```json
{
  "temperature": 0.0,
  "seed": 7,
  "top_p": 1.0,
  "top_k": 0,
  "num_ctx": 8192,
  "num_predict": 300
}
```

`num_ctx` is 8192 rather than the model's full 40960 because the ContextBuilder
budget caps the packet well below that (median prompt ~944 tokens), and a
smaller window keeps KV-cache pressure off the 12 GB card.

## Thinking mode

Qwen3 supports an extended-reasoning mode, exposed by Ollama as `think`. It is
not a free knob here:

**Native tool calling does not work at all with `think: false`.** The model
returns `done_reason: stop` with an empty `content` and an empty `tool_calls`
array after ~49 tokens. With `think: true` the same prompt produces a valid tool
call. This is measured, not inferred — see
[E2](qwen_decision_interface/REPORT.md).

Experiment 2 therefore runs a 2×2 dev matrix (interface × thinking) rather than
a single comparison, and reports the cost each interface needs to work.

## Determinism

`temperature: 0` with a fixed `seed` does not guarantee bit-identical output
across runs on a GPU. Decision stability across repeats is therefore
**measured** rather than assumed, and reported as a metric in E2 and E3.

## Fixture server

Two origins so cross-origin policy and cross-origin iframes can be tested
without touching the public internet:

| | |
|---|---|
| primary | `http://127.0.0.1:<base>` |
| secondary | `http://localhost:<base+1>` |
| default base | 8799, overridable with `BAV2_PORT_BASE` |

The cluster mints a nonce at startup and refuses to start if another process
answers on its ports — a stale server shadowing a port via Windows
`SO_REUSEADDR` silently corrupted one round of Experiment 1 results before this
check existed.

## Git

| | |
|---|---|
| Branch | `experiment/p0-gate-campaign` |
| Base | `main` @ `d3c9a26` |
| Remote | `https://github.com/Reshwant-Borra/BrowserAgentV2.git` |
