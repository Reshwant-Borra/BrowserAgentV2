# P0 experiment index

Gate → verdict → evidence for the P0 rows in
[`../06_OPEN_QUESTIONS/DECISION_GATES_V2.md`](../06_OPEN_QUESTIONS/DECISION_GATES_V2.md).

Campaign branch: `experiment/p0-gate-campaign`, based on `main` @ `d3c9a26`.
Environment: [`ENVIRONMENT.md`](ENVIRONMENT.md), also embedded in every result
file. Process notes and known problems: [`CAMPAIGN_NOTES.md`](CAMPAIGN_NOTES.md).

## Verdicts

| Gate | Status | Experiment | Verdict | Evidence |
|---|---|---|---|---|
| Browser kernel: MCP vs direct Playwright | RESOLVED | [E1](browser_kernel/REPORT.md) | `ADOPT_DIRECT_PLAYWRIGHT` | [raw](browser_kernel/results/experiment1_raw.json) |
| Qwen output interface | RESOLVED | [E2](qwen_decision_interface/REPORT.md) | `ADOPT_STRICT_JSON` | [raw](qwen_decision_interface/results/) |
| Qwen3:8B adequacy | RESOLVED (negative) | [E3](qwen_adequacy/REPORT.md) | **`QWEN3_8B_INADEQUATE`** | [raw](qwen_adequacy/results/experiment3_adequacy_withoptions.json) |
| Observation invalidation | RESOLVED | [E4](observation_invalidation/REPORT.md) | `INVALIDATION_RESOLVED` | [raw](observation_invalidation/results/experiment4_raw.json) |
| Tab ownership / page registry | RESOLVED | [E5](page_registry/REPORT.md) | `PAGE_REGISTRY_RESOLVED` | [raw](page_registry/results/experiment5_raw.json) |
| Ambiguous side-effect protocol | RESOLVED | [E6](side_effect_recovery/REPORT.md) | `SIDE_EFFECT_RECOVERY_RESOLVED` | [raw](side_effect_recovery/results/experiment6_raw.json) |
| Human handoff / resume | RESOLVED | [E7](human_handoff/REPORT.md) | `HANDOFF_RESOLVED` | [raw](human_handoff/results/experiment7_raw.json) |
| Policy / security boundary | RESOLVED | [E8](security_policy/REPORT.md) | `POLICY_BOUNDARY_RESOLVED` | [raw](security_policy/results/experiment8_raw.json) |
| Browser profile strategy | RESOLVED | [Profile](profile_strategy/REPORT.md) | `DEDICATED_PROFILE_RESOLVED` | [raw](profile_strategy/results/profile_strategy_raw.json) |

Overall: **`P0_COMPLETE_WITH_PROVISIONAL_ITEMS`** —
[`p0_summary/P0_CONSOLIDATION.md`](p0_summary/P0_CONSOLIDATION.md).
Frozen architecture:
[`../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md`](../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md).

## Scale of evidence

| Experiment | Runs | Invariant | Violations |
|---|---:|---|---:|
| E1 kernel spike | 210 | no unsafe execution | **0** |
| E4 invalidation | 672 | no wrong-target execution (safe policies) | **0** |
| E5 page registry | 220 | no user tab closed | **0** |
| E6 crash recovery | 60 trials / 32 crashes | no duplicate side effect (reconcile) | **0** |
| E7 handoff | 90 | no stale target trusted | **0** |
| Profile | 36 | persistence and isolation | **0** |
| E8 arm A | 272 | no capability escalation | **0** |
| E8 arm B | 16 | model resists hostile pages | **0** obeyed |
| E8 arm C | 25 | no false block of benign work | **0** |
| E2 interface | 432 model calls | hallucinated target on an action | **0** |
| E3 adequacy | 166 model calls | pre-registered adequacy bar | **missed** |

## Controls that were supposed to fail

A suite where everything passes proves nothing about which mechanism did the
work.

| Control | Experiment | Result | What it established |
|---|---|---|---|
| `UNSAFE_NAME_RESOLVE` | E4 | **84 wrong-target executions** | re-resolving by accessible name is catastrophic, on ordinary pages |
| `blind_replay` | E6 | **20 duplicate side effects** | the reconciliation protocol is doing real work |
| `UNSAFE_URL_ONLY` | E4 | **0 wrong-target** | it *changed the conclusion*: safety comes from node binding, not the invalidation rule |

## Headline numbers

```text
kernel          direct Playwright 105/105   |  Playwright MCP 90/105
invalidation    0 wrong targets / 336       |  unsafe control: 84
page registry   220/220                     |  0 user tabs closed
crash safety    32 crashes, 0 duplicates    |  blind-replay control: 20
handoff         90/90                       |  0 stale targets trusted
profile         36/36
policy          272 probes, 0 bypasses      |  0 false blocks / 25
interface       tie on quality (75.00%)     |  decided on 100% vs 90.74% schema
model           INADEQUATE                  |  PROVISIONAL missed by 0.78 points
```

## Reading order

1. [`README.md`](README.md) — setup, ground rules, reproduction
2. [`CAMPAIGN_NOTES.md`](CAMPAIGN_NOTES.md) — how it was run, and what went wrong
3. [E1](browser_kernel/REPORT.md) — which runtime
4. [E4](observation_invalidation/REPORT.md) — target freshness
5. [E5](page_registry/REPORT.md) — page identity and ownership
6. [Profile](profile_strategy/REPORT.md) — persistence and isolation
7. [E6](side_effect_recovery/REPORT.md) — crash safety
8. [E7](human_handoff/REPORT.md) — pause and resume
9. [E2](qwen_decision_interface/REPORT.md) — how the model speaks
10. [E3](qwen_adequacy/REPORT.md) — whether the model is good enough
11. [E8](security_policy/REPORT.md) — the policy boundary
12. [`p0_summary/P0_CONSOLIDATION.md`](p0_summary/P0_CONSOLIDATION.md) — go / no-go
