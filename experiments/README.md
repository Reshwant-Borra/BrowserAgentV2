# P0 experiment campaign

Controlled experiments that resolve the P0 rows in
[`../06_OPEN_QUESTIONS/DECISION_GATES_V2.md`](../06_OPEN_QUESTIONS/DECISION_GATES_V2.md)
before the architecture is frozen. Nothing here is production code. These are
harnesses whose only job is to make a decision gate answerable with evidence.

Start at [`P0_EXPERIMENT_INDEX.md`](P0_EXPERIMENT_INDEX.md) for gate → verdict →
evidence.

## Ground rules these harnesses follow

1. **The kernel under test never grades itself.** "What the page actually did"
   comes from the fixture server's out-of-band effect log, written by the page
   with a synchronous XHR before the click handler returns.
2. **Unsafe controls are included on purpose.** Experiments 4 and 6 run the
   forbidden policies (`UNSAFE_URL_ONLY`, `UNSAFE_NAME_RESOLVE`, `blind_replay`)
   alongside the safe ones. A suite where everything passes cannot show which
   mechanism did the work.
3. **Harness bugs are not runtime failures.** Every runner has a
   `HARNESS_ERROR` outcome, counted separately and never charged to a candidate.
   Several findings during this campaign turned out to be adapter bugs; those
   were fixed and re-run rather than reported as results.
4. **Localhost only.** No experiment performs a real-world write. The mutation
   endpoint is a local SQLite ledger.
5. **Raw evidence is preserved.** Every runner writes a `results/*.json`
   containing full environment capture, every row, and the failures.

## Setup

```bash
python -m pip install playwright pytest
python -m playwright install chromium
cd experiments && npm install        # pins @playwright/mcp for Experiment 1
ollama serve                         # Experiments 2, 3 and 8 arm B
```

## Reproduce

Each experiment is one command. `BAV2_PORT_BASE` lets independent runs proceed
concurrently without colliding (or silently sharing a stale server — the fixture
cluster refuses to start if another process answers on its ports).

```bash
# E1 — BrowserKernel: Playwright MCP vs direct Playwright
python -m experiments.browser_kernel.run_spike --passes 3

# frozen inputs for E2 (regenerate only with a version bump)
python -m experiments.qwen_decision_interface.capture_observations
python -m experiments.qwen_decision_interface.build_dataset

# E2 — decision interface: strict JSON vs native tool calling
python -m experiments.qwen_decision_interface.run_interface_experiment --split dev
python -m experiments.qwen_decision_interface.run_interface_experiment --split eval

# E3 — Qwen3:8B adequacy on a held-out set (threshold pre-registered)
python -m experiments.qwen_adequacy.build_adequacy_set
python -m experiments.qwen_adequacy.run_adequacy

# E4 — observation invalidation
BAV2_PORT_BASE=8810 python -m experiments.observation_invalidation.run_invalidation --reps 12

# E5 — page registry and tab ownership
BAV2_PORT_BASE=8820 python -m experiments.page_registry.run_page_registry --reps 20

# E6 — ambiguous side-effect / crash recovery
BAV2_PORT_BASE=8830 python -m experiments.side_effect_recovery.run_side_effects --reps 3

# E7 — human handoff and resume
BAV2_PORT_BASE=8840 python -m experiments.human_handoff.run_handoff --reps 10

# profile strategy
BAV2_PORT_BASE=8850 python -m experiments.profile_strategy.run_profile --reps 6

# E8 — policy boundary and prompt injection
python -m experiments.security_policy.run_policy
```

## Layout

```text
common/            shared contracts, kernels, policy, grading, fixture server
fixtures/pages/    plain readable HTML; no site-specific logic anywhere
browser_kernel/    E1  MCP vs direct Playwright
qwen_decision_interface/  E2  strict JSON vs native tool calling (+ frozen dataset)
qwen_adequacy/     E3  held-out adequacy set and pre-registered threshold
observation_invalidation/ E4  stale-target safety
page_registry/     E5  tab ownership
side_effect_recovery/     E6  crash injection and reconciliation
human_handoff/     E7  pause and resume
security_policy/   E8  injection corpus and policy boundary
profile_strategy/  dedicated persistent profile confirmation
p0_summary/        consolidated verdicts
```

## Shared pieces, deliberately not duplicated

- [`common/contracts.py`](common/contracts.py) — Observation, Decision,
  ActionIntent, ActionResult, PageRecord, typed kernel errors.
- [`common/kernel.py`](common/kernel.py) — the `BrowserKernel` interface both
  Experiment 1 candidates implement.
- [`common/context_builder.py`](common/context_builder.py) — the one prompt
  packet used by E2, E3 and E8 arm B.
- [`common/grading.py`](common/grading.py) — deterministic scoring. No model
  grades another model anywhere in this campaign.
- [`common/policy.py`](common/policy.py) — the deterministic PolicyEngine.
- [`common/fixture_server.py`](common/fixture_server.py) — two origins, the
  durable operation ledger, and the effect oracle.
