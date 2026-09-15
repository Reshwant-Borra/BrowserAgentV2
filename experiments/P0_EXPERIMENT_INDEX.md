# P0 experiment index

Gate → verdict → evidence for the P0 rows in
[`../06_OPEN_QUESTIONS/DECISION_GATES_V2.md`](../06_OPEN_QUESTIONS/DECISION_GATES_V2.md).

Campaign branch: `experiment/p0-gate-campaign`.
Environment is captured inside every `results/*.json`; the shared summary is in
[`ENVIRONMENT.md`](ENVIRONMENT.md).

## Verdicts

| Gate | Status | Experiment | Verdict | Evidence | Commit |
|---|---|---|---|---|---|
| Browser kernel: MCP vs direct Playwright | RESOLVED | [E1](browser_kernel/REPORT.md) | `ADOPT_DIRECT_PLAYWRIGHT` | [raw](browser_kernel/results/experiment1_raw.json) | `9024aed` |
| Qwen output interface | RESOLVED | [E2](qwen_decision_interface/REPORT.md) | `ADOPT_STRICT_JSON` | [raw](qwen_decision_interface/results/) | `_E2_` |
| Qwen3:8B adequacy | RESOLVED | [E3](qwen_adequacy/REPORT.md) | `_E3_VERDICT_` | [raw](qwen_adequacy/results/) | `_E3_` |
| Observation invalidation | RESOLVED | [E4](observation_invalidation/REPORT.md) | `INVALIDATION_RESOLVED` | [raw](observation_invalidation/results/experiment4_raw.json) | `8d2d81b` |
| Tab ownership / page registry | RESOLVED | [E5](page_registry/REPORT.md) | `PAGE_REGISTRY_RESOLVED` | [raw](page_registry/results/experiment5_raw.json) | `8d2d81b` |
| Ambiguous side-effect protocol | RESOLVED | [E6](side_effect_recovery/REPORT.md) | `SIDE_EFFECT_RECOVERY_RESOLVED` | [raw](side_effect_recovery/results/experiment6_raw.json) | `8d2d81b` |
| Human handoff / resume | RESOLVED | [E7](human_handoff/REPORT.md) | `HANDOFF_RESOLVED` | [raw](human_handoff/results/experiment7_raw.json) | `8d2d81b` |
| Policy / security boundary | RESOLVED | [E8](security_policy/REPORT.md) | `POLICY_BOUNDARY_RESOLVED` | [raw](security_policy/results/experiment8_raw.json) | `_E8_` |
| Browser profile strategy | RESOLVED | [Profile](profile_strategy/REPORT.md) | `DEDICATED_PROFILE_RESOLVED` | [raw](profile_strategy/results/profile_strategy_raw.json) | `8d2d81b` |

## Scale of evidence

| Experiment | Runs | Key invariant | Violations |
|---|---:|---|---:|
| E1 kernel spike | 210 (105 per candidate) | no unsafe execution | 0 |
| E4 invalidation | 672 (168 per policy) | no wrong-target execution (safe policies) | 0 |
| E5 page registry | 220 | no user tab closed | 0 |
| E6 crash recovery | 60 | no duplicate side effect (reconcile) | 0 |
| E7 handoff | 90 | no stale target trusted | 0 |
| Profile | 36 | persistence and isolation | 0 |
| E8 policy arm A | 272 | no capability escalation | 0 |
| E8 policy arm C | 25 | no false block of benign work | 0 |

## Controls that were supposed to fail, and did

A suite where everything passes proves nothing about which mechanism did the
work. These arms exist to show the safe mechanisms are load-bearing.

| Control | Experiment | Result |
|---|---|---|
| `UNSAFE_NAME_RESOLVE` — re-resolve targets by role + accessible name | E4 | **84 wrong-target executions** across 7 scenarios |
| `blind_replay` — retry the intent on restart | E6 | **20 duplicate side effects** |
| `UNSAFE_URL_ONLY` — invalidate only on URL change | E4 | 0 wrong-target — see [E4](observation_invalidation/REPORT.md); it changed the conclusion |

## Reading order

1. [`README.md`](README.md) — setup, ground rules, reproduction commands
2. [E1](browser_kernel/REPORT.md) — which runtime
3. [E4](observation_invalidation/REPORT.md) — target freshness
4. [E5](page_registry/REPORT.md) — page identity and ownership
5. [Profile](profile_strategy/REPORT.md) — persistence and isolation
6. [E6](side_effect_recovery/REPORT.md) — crash safety
7. [E7](human_handoff/REPORT.md) — pause and resume
8. [E2](qwen_decision_interface/REPORT.md) — how the model speaks
9. [E3](qwen_adequacy/REPORT.md) — whether the model is good enough
10. [E8](security_policy/REPORT.md) — the policy boundary
11. [`p0_summary/P0_CONSOLIDATION.md`](p0_summary/P0_CONSOLIDATION.md) — go / no-go
