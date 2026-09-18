# Local Model and Inference Strategy

## Decision
Do not design BrowserAgentV2 around an always-on multi-model ensemble. Establish one local multimodal generalist baseline, then add specialists only behind measured escalation gates.

### Baseline candidate
Benchmark **Qwen3-VL-8B-Instruct** first as the general decision/proposal model. This is not a permanent lock-in. It is the highest-information baseline because it combines text reasoning, screenshots, OCR/spatial perception, computer-use grounding and tool/function-call support in one 8B-class model. The official Qwen3-VL project explicitly targets computer-use agents and exposes a computer-use tool interface; an official 8B Instruct checkpoint and GGUF Q4_K_M path exist.

Why this changes the earlier plan: the current BrowserAgentV2 architecture already obtains most actions from deterministic semantics (Playwright/CDP/AX/UIA). The model does not need to be the primary pixel controller. A competent multimodal 8B can therefore propose plans/targets and interpret hard observations while the controller and verifier retain correctness authority.

## Model roles
### General decision model — baseline, always available
Inputs: bounded state projection, semantic observation, optional screenshot/crop, capability summary, allowed action schema.
Outputs: structured proposal only: next semantic action, TargetSpec, arguments, or replan proposal.

It never owns policy, action completion, retries, durable state, or final verification.

### GUI grounder — optional escalation
Benchmark UI-TARS-2B, ZonUI-3B, and UGround-V1-2B only on cases where semantic resolution fails or is ambiguous. Do not keep one resident unless it materially lowers wrong-target/abstention error at acceptable memory/latency.

Published evidence is strong enough to justify testing but not architectural commitment. ZonUI-3B reports 86.4 ScreenSpot-v2 average and 93.8/75.0 desktop text/icon; UI-TARS-2B reports 84.7 average and 90.7/68.6 desktop text/icon in the same table. UGround-V1-2B reports strong ScreenSpot grounding. These are benchmark claims, not BrowserAgentV2 reliability measurements.

### Critic/verifier model — no permanent model initially
Deterministic typed predicates remain primary. Invoke a model critic only when deterministic evidence is unavailable/inconclusive and the action risk permits probabilistic verification. Do not run a critic on every step.

## Hardware strategy
### RTX 4070 12 GB
Start with one Q4 8B-class generalist resident. Avoid simultaneously pinning generalist + 3B grounder until measured. If specialist escalation is rare, load/unload or run the specialist on demand. A community UI-TARS-2B server reports ~4.1 GB VRAM and ~1.2 s element lookup, but this must be reproduced locally before budgeting around it.

### Apple Silicon 24 GB
Prefer MLX/MLX-VLM where model support is correct and benchmark against llama.cpp GGUF for portability. Unified memory makes 8B Q4 feasible, but the relevant limit is weights + KV + vision/activation workspace + OS headroom, not weights alone. Do not inflate context to model-advertised maxima simply because they are supported.

## Context and KV policy
BrowserAgentV2's architecture should make long context unnecessary for ordinary control. Use the bounded state projection from LONG_HORIZON_STATE.md and target a small stable working window.

Rules:
1. Keep a stable prefix: system/controller contract, compact tool schemas, skill metadata, and policy summary should change rarely so prompt/KV caching can help.
2. Put volatile observation/current-step material after the stable prefix.
3. Do not resend full screenshots or full semantic trees when a delta/crop/filtered subtree suffices.
4. Cap reasoning/output budgets by decision class. Simple target selection should not consume long chain-of-thought budgets.
5. Test KV quantization/cache reuse only after output-quality baselines. MLX-LM exposes prompt-cache support and quantized KV behavior; newer edge work shows substantial KV compression is possible but may change token trajectories.
6. Treat cache as performance state, never correctness state. A cache miss must only cost latency.

## Routing policy
Use deterministic routing before learned/model routing.

1. Known deterministic skill with satisfied preconditions -> execute skill/controller path without planner call when safe.
2. Semantic action obvious from current plan and one unambiguous candidate -> small generalist proposal or deterministic binding depending on skill contract.
3. Semantic ambiguity/plan change -> generalist.
4. Visual-only target -> optional grounder escalation.
5. Deterministic verifier unavailable -> optional critic only if risk permits.
6. Repeated uncertainty/high-impact ambiguity -> handoff, not more model layers.

Do not train a learned router initially. Log routing decisions and counterfactual availability first; train/learn only if deterministic thresholds are a measurable bottleneck.

## Structured-output reliability
Tool-call/schema reliability is a release criterion, not assumed from model cards. Qwen's own ecosystem supports tool/function calling, but historical Qwen-VL issue reports show complex tool templates can fail in practice. BrowserAgentV2 should therefore use narrow JSON schemas, parser validation, one bounded repair attempt for `MODEL_INVALID`, and deterministic rejection after that. Never interpret malformed free text as an action.

## Common-fixture model benchmark
Use the same 200-500 fixtures for every candidate/configuration:
- semantic next-action selection
- duplicate-label TargetSpec selection
- screenshot text/icon grounding
- absent-target abstention
- ambiguous-target abstention
- tool/schema emission
- failure classification
- replan suffix generation
- adversarial untrusted UI text that asks for authority expansion

Measure exact schema validity, semantic action accuracy, wrong-target rate, false-success tendency, abstention precision/recall, p50/p95 prefill/decode latency, tokens/s, peak RAM/VRAM, cold load, warm latency, and result variance across repeated trials.

### Configurations to compare
A. Qwen3-VL-8B generalist only.
B. Generalist + UI-TARS-2B escalation.
C. Generalist + ZonUI-3B escalation.
D. Generalist + UGround-V1-2B escalation.
E. Best of B-D + critic-on-inconclusive only.

A specialist survives only if it materially improves verifier-confirmed task success or wrong-target safety, not just ScreenSpot accuracy.

## Initial acceptance targets
These are engineering gates to tune, not claims about current models:
- >=99.5% schema-valid proposals after at most one repair on controlled fixtures.
- zero policy-authority expansion accepted from adversarial UI text.
- absent/ambiguous target false-click rate <0.5% on controlled fixtures.
- specialist must reduce visual wrong-target rate by >=25% relative or recover >=10 percentage points of visual-only tasks to justify permanent integration.
- model choice must not increase false-success rate versus the baseline controller/verifier contract.

## Rejected designs
- Always-on planner + grounder + critic ensemble: premature memory/latency/context overhead.
- Text-only planner as the sole generalist: forces a second model whenever semantic observations are insufficient.
- Frontier-sized context as memory: conflicts with bounded-state architecture and local latency.
- Model-selected authority/routing without deterministic gates: unnecessary security/reliability coupling.
- Optimize tokens/s before proposal correctness and abstention: wrong objective.

## Confidence
**88%** for one multimodal 8B-class generalist baseline plus measured specialist escalation. **76%** that Qwen3-VL-8B-Instruct will be the final generalist; hardware/common-fixture measurement is required. **90%** that an always-on critic should not be in v1.

## Sources checked
- QwenLM/Qwen3-VL official repository and official Qwen3-VL-8B-Instruct/GGUF model pages: computer-use/grounding/tool support and local deployment paths.
- Qwen/Qwen3-8B model card: 8.2B parameters, GQA, native 32K context / longer YaRN support; useful as text-only control comparator, not the chosen multimodal baseline.
- Apple MLX-LM `cache_prompt.py`: reusable prompt-cache implementation and quantized-KV threshold support.
- 2026 Agent Memory Below the Prompt implementation: persistent Q4 KV cache demonstrates prefix reuse opportunity but also documents tool-choice and synchronous-persistence limitations.
- ZonUI-3B official repository; UGround official repository; UI-TARS community inference server for benchmark/runtime hypotheses.