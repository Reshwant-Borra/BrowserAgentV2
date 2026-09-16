# Observation Contract V1 — correction gate

Corrects three defects that were documented before this branch and deliberately
left open, then freezes the contract.

- Scope, fixed before any code was written: [`SCOPE_LOCK.md`](SCOPE_LOCK.md)
- Frozen contract: [`../../03_DECISIONS/OBSERVATION_CONTRACT_V1.md`](../../03_DECISIONS/OBSERVATION_CONTRACT_V1.md)

## Reproduce

```bash
# contract + verifier suites (one browser session; they cannot run in parallel
# processes because Playwright forbids two live sync instances)
python -m pytest tests -q

# text recall / noise measurement, old strategy vs new
python -m experiments.observation_contract.measure_text
```

## P0 regression

Run against the corrected kernel. Outputs are kept in
[`results/p0_regression/`](results/p0_regression/) rather than overwriting the
original campaign evidence, which stays byte-identical to `213779b`.

```bash
BAV2_PORT_BASE=8810 python -m experiments.observation_invalidation.run_invalidation --reps 4
BAV2_PORT_BASE=8820 python -m experiments.page_registry.run_page_registry --reps 8
BAV2_PORT_BASE=8830 python -m experiments.side_effect_recovery.run_side_effects --reps 2
BAV2_PORT_BASE=8840 python -m experiments.human_handoff.run_handoff --reps 5
BAV2_PORT_BASE=8850 python -m experiments.profile_strategy.run_profile --reps 3
python -m experiments.browser_kernel.run_spike --passes 1
python -m experiments.security_policy.run_policy --no-model
```

These use smaller repetition counts than the original campaign: they are a
compatibility check against a changed contract, not a re-derivation of the P0
verdicts.
