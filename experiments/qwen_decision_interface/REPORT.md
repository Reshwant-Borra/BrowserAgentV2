# Experiment 2 — Qwen decision interface

**Gate:** `Qwen output interface` (P0, was `OPEN`)
**Verdict:** `ADOPT_STRICT_JSON`
**Evidence:** [`results/`](results/)
**Reproduce:**
```bash
python -m experiments.qwen_decision_interface.capture_observations
python -m experiments.qwen_decision_interface.build_dataset
python -m experiments.qwen_decision_interface.run_interface_experiment --split dev  --reps 1 --interfaces STRICT_JSON  --num-predict 300
python -m experiments.qwen_decision_interface.run_interface_experiment --split eval --reps 2 --interfaces STRICT_JSON  --num-predict 300
python -m experiments.qwen_decision_interface.run_interface_experiment --split eval --reps 2 --interfaces NATIVE_TOOLS --think --num-predict 1600
```

## Question

Which interface should BrowserAgentV2 use for Qwen decisions: strict structured
JSON, or native Qwen/Ollama tool calling?

## Dataset

**166 frozen cases** built from **35 real observations** captured from the
BrowserKernel against the fixture site — not hand-written approximations, so the
experiment tests the system we are about to build.

| split | cases |
|---|---:|
| dev (iteration allowed) | 58 |
| eval (looked at once) | 108 |

| difficulty | cases |
|---|---:|
| easy | 53 |
| medium | 113 |

15 families: simple clicks, exact typing, exact select arguments, duplicate
labels, frame scope, page selection, stale refs, disabled controls, human
handoff, confirmation, completion, no-valid-action, replan-after-failure,
extraction, and 32 prompt-injection cases.

`dataset_v1.json` sha256 `b2d23290aa3f09f5…`, observations sha256
`13cfa1f4afab5abc…`.

## Fairness

Identical across arms: model (`qwen3:8b` Q4_K_M, digest `500a1f067a9f…`),
`num_ctx`, temperature 0, seed 7, hardware, goal text, observation text, and the
byte-identical policy block. Only the output mechanism differs, plus the minimal
"how to answer" paragraph each needs. Both are normalised onto the same
canonical `Decision` before scoring, and scoring is deterministic
([`grading.py`](../common/grading.py)) — no model grades a model.

### Native tool calling does not work without thinking mode

Discovered on the dev split: with `think: false`, Qwen3:8B answers a tool-calling
prompt with `done_reason: stop`, empty `content` and an empty `tool_calls` array
after ~49 tokens. It emits nothing at all. With `think: true` the same prompt
produces a valid tool call.

This makes a single-configuration comparison impossible, so a **2×2 dev matrix**
was run (interface × thinking) and each interface was then evaluated in its own
best configuration. Anything else would have measured a setting, not an
interface.

An earlier dev pass also had to be discarded: both thinking arms hit
`num_predict: 300` (median completion exactly 300), so their schema failures
were truncation rather than model behaviour. The thinking arms were re-run at
1600.

## Dev matrix (58 cases, 1 rep)

| configuration | end-to-end | schema valid | target acc | halluc. on action | latency median |
|---|---:|---:|---:|---:|---:|
| **STRICT_JSON, no thinking** | **72.22%** | **100.00%** | **72.22%** | 0 | **812 ms** |
| NATIVE_TOOLS, thinking | 72.22% | 94.83% | 62.75% | 0 | 4 721 ms |
| NATIVE_TOOLS, no thinking | 64.81% | 81.03% | 57.45% | 0 | 765 ms |
| STRICT_JSON, thinking | 61.11% | 93.10% | 66.00% | 0 | 4 672 ms |

Thinking mode made **strict JSON worse** (72.22% → 61.11%) while costing 5.7×
the latency. It is not a free quality knob at this model size.

Best configuration per interface: strict JSON without thinking; native tools
with thinking.

## Eval results (108 held-out cases × 2 reps = 216 runs per arm)

| metric | STRICT_JSON | NATIVE_TOOLS |
|---|---:|---:|
| **end-to-end usable decision** | **75.00%** | **75.00%** |
| schema-valid output | **100.00%** | 90.74% |
| decision accuracy (of valid decisions) | 75.00% | **82.98%** |
| action accuracy | 77.88% | **86.17%** |
| target accuracy | **75.96%** | 67.02% |
| argument accuracy | 91.35% | **93.09%** |
| hallucinated target **on a targeted action** | **0** | **0** |
| hallucinated target, any slot | **0** | 28 |
| forbidden decisions | 12 (5.56%) | **6 (2.78%)** |
| multiple-action violations | **0** | 2 |
| consistency across reps (temp 0) | **100.00%** | 98.15% |
| latency median | **811 ms** | 4 377 ms |
| latency p95 | **976 ms** | 22 312 ms |
| prompt tokens (median) | **929** | 1 358 |
| completion tokens (median) | **55** | 315 |
| total completion tokens | **11 186** | 112 478 |

### The headline metric, and why it was corrected

`full_decision_accuracy` is computed over decisions that *parsed*. An interface
that fails to emit a decision therefore shrinks its own denominator and scores
better for failing. `end_to_end_usable_decision_pct` — parseable **and** correct,
over every case that has a right answer — is the metric the controller actually
experiences. On that measure the two interfaces are an exact tie at 75.00%.

### The hallucination number was corrected too

Native tool calling's 28 "hallucinated targets" are **all** `EXTRACT` decisions
carrying `target: "page_1"` — a page id placed in an optional slot. **Zero**
occurred on a CLICK, TYPE, SELECT or PRESS. Reporting one combined number
misrepresented tool calling, so the metric is now split by severity. On the
safety-critical measure both interfaces score zero.

## Where each interface is genuinely better

Native tool calling is not the loser everywhere, and the differences are real:

| family | STRICT_JSON | NATIVE_TOOLS |
|---|---:|---:|
| injection (32 cases) | 66.67% | **95.24%** |
| human handoff | 40.00% | **60.00%** |
| disabled control | 50.00% | **75.00%** |
| no valid action | 50.00% | **66.67%** |
| duplicate labels | **90.91%** | 54.55% |
| exact select argument | **50.00%** | 0.00% |
| extraction | **100.00%** | 66.67% |
| completion | **75.00%** | 50.00% |
| replan after failure | **50.00%** | 25.00% |

Tool calling — which here means *with thinking enabled* — is better at deciding
**whether to act at all**: resisting injections, deferring to the human, and
recognising that nothing on the page helps. Strict JSON is better at **picking
the right thing** once acting: the correct duplicate, the correct argument, the
correct read.

That is a plausible consequence of thinking mode rather than of the output
format, and the dev matrix supports it: `NATIVE_TOOLS` without thinking scored
only 64.81% end-to-end. The confound is not fully separable here, and saying so
is more useful than pretending the format alone explains it.

## Verdict

```text
ADOPT_STRICT_JSON
```

Decision quality is a **tie** (75.00% both). The choice is therefore made on the
properties the architecture depends on, where it is not close:

1. **Schema validity 100% vs 90.74%.** 20 of 216 tool-calling turns produced no
   decision at all. Each is a wasted controller cycle and a re-prompt.
2. **Determinism 100% vs 98.15%.** A policy that does not reproduce cannot be
   regression-tested, and regression tests are the point of this repository.
3. **Zero multiple-action violations vs 2.**
   [ADR-005](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md) is one state-changing
   action per step; tool calling broke it twice.
4. **5.4× median and 23× p95 latency, and 10× completion tokens**, because tool
   calling only works with thinking enabled. Under the
   [VISION_AND_SCOPE](../../00_PROJECT/VISION_AND_SCOPE.md) priority order,
   correctness-then-recoverability comes first — but between two options of
   equal correctness, a 23× p95 difference decides.
5. **Fewer input tokens** (929 vs 1358 median): tool definitions cost ~430
   tokens of the context budget on every call.

The one metric favouring tool calling — 6 forbidden decisions vs 12 — matters
and is recorded. It is a model-behaviour difference attributable mostly to
thinking mode, and it is addressed by the deterministic PolicyEngine rather than
by the interface: [Experiment 8](../security_policy/REPORT.md) shows all of those
classes are blocked outside the model regardless.

## Defects this experiment found in the representation

Both diagnosed on **dev** and fixed there; the eval split above was scored on
the representation it was run with.

1. **Target ids were being over-copied.** Rendering an element as
   `obs_00001:f0:e2 link 'Next page'` led the model to copy the whole line as
   the target. Re-rendered as `target=obs_00001:f0:e2 | link | 'Next page'`,
   with the prompt stating the id ends at the first ` | `. Hallucinated targets
   went to zero.
2. **Dropdown options were invisible.** All three dev `SELECT` cases failed with
   CLICK-instead-of-SELECT because the observation showed that a combobox
   existed but never which values it accepted — the model could not have
   produced a correct argument.
   [END_TO_END_SYSTEM_SPEC](../../02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md)
   section 7 already listed "select options" as Tier 3 enrichment; we had simply
   not implemented it. Fixed, and carried into
   [Experiment 3](../qwen_adequacy/REPORT.md).

## What this does not establish

- One model (`qwen3:8b` Q4_K_M) on one machine. A larger or differently
  quantized model could reorder these results.
- `@playwright/mcp`-style tool calling from other runtimes was not tested; this
  is Ollama's tool-calling implementation for this model.
- 75% end-to-end is an *interface* result, not a verdict on whether the model is
  good enough. That is [Experiment 3](../qwen_adequacy/REPORT.md).
- The thinking-mode confound in the tool-calling arm is real and unresolved. If
  the interface question is ever reopened, the cleanest next experiment is
  strict JSON *with* a separate reasoning pass, which is not the same as strict
  JSON with thinking enabled.
