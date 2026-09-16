# Architecture Freeze V1

**Date:** 2026-09-15
**Basis:** the P0 experiment campaign on `experiment/p0-gate-campaign`
**Index:** [`../experiments/P0_EXPERIMENT_INDEX.md`](../experiments/P0_EXPERIMENT_INDEX.md)
**Environment:** [`../experiments/ENVIRONMENT.md`](../experiments/ENVIRONMENT.md)

This document freezes decisions that controlled experiments have already
established. **It introduces no new architecture.** Anything not measured is
marked as such. Every frozen item links to the evidence that froze it.

Superseding any line here requires a new ADR backed by a reproducible
experiment, per the decision discipline in
[`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md).

---

## 1. BrowserKernel runtime — FROZEN

**Direct Playwright**, behind the
[`BrowserKernel`](../experiments/common/kernel.py) interface.

Playwright 1.62.0, Chromium 151.0.7922.34, headless by default, one browser per
controller.

Evidence: [E1](../experiments/browser_kernel/REPORT.md) — 105/105 vs MCP's
90/105, zero unsafe outcomes on either side. MCP was disqualified by a rule
written before the experiment: it cannot guarantee tab ownership.
[ADR-002](ARCHITECTURE_DECISIONS.md).

No code above the interface may reference Playwright, CDP or MCP concepts. That
rule is what made this swap free, and it stays.

## 2. Browser profile strategy — FROZEN

A **dedicated Playwright-managed persistent profile**, launched by the
controller. Attaching to the user's own Chrome remains deferred.

Evidence: [Profile strategy](../experiments/profile_strategy/REPORT.md) — 36/36.
Cookies and `localStorage` survive restart, profiles are mutually isolated, and
the user's real Chrome directory is never touched.
[ADR-003](ARCHITECTURE_DECISIONS.md).

Because we launch the browser, its initial page is ours. `initial_pages_owner`
is an explicit parameter, so the deferred attach mode cannot inherit that
assumption by accident.

## 3. Observation format — FROZEN in principle

Accessibility-first semantic snapshot. Per element: target id, role, accessible
name, value, enabled, visible, frame id, **nearest preceding heading**, and
**select options**. Plus page text limited to what is actually visible.

Two of those fields exist because the experiments proved the observation was
otherwise unusable:

- **section anchor** — three byte-identical `Submit` buttons cannot be
  distinguished without it;
- **select options** — the model could see a combobox but not its legal values,
  so it could not produce a correct argument
  ([E2](../experiments/qwen_decision_interface/REPORT.md));
- **visibility filtering of page text** — hidden nodes were reporting a
  validation error that was not on screen.

Target ids are rendered as `target=<id> | role | name`, terminated by ` | `.
Rendered as a bare leading token, the model copied whole lines as the target.

**Known defect, not fixed:** elements inside a table row or list item carry no
row context, so three identical `Open` buttons in a table are indistinguishable.
Diagnosed in [E3](../experiments/qwen_adequacy/REPORT.md) (case AD-M22). It was
deliberately not fixed after the held-out run, to avoid tuning to the evaluation
set. **This is the first thing to fix in the next iteration.**

## 4. Target identity and freshness — FROZEN

A target is bound to the **live DOM node** observed. Valid while: the node is
connected, the document token is unchanged, the frame is attached, the page is
open. Policy: `NODE_IDENTITY`.

Plus an unconditional `invalidate_all_observations(reason)` that outranks the
policy, used at handoff, resume and reconnect.

Evidence: [E4](../experiments/observation_invalidation/REPORT.md) — 0
wrong-target executions in 336 safe-policy runs; the name-resolving control
produced 84. [E7](../experiments/human_handoff/REPORT.md) — explicit
invalidation is the only thing that can help when a human types in a field.
[ADR-012](ARCHITECTURE_DECISIONS.md), [ADR-013](ARCHITECTURE_DECISIONS.md).

The mechanism that matters is node binding. The policy on top decides error
quality and over-invalidation cost, not safety.

## 5. Page registry and ownership — FROZEN

Page identity is the `page_id` minted at the creation event. **Never** title,
URL or tab index.

```text
kernel asked for this page          -> AGENT
page has an opener                  -> inherit the opener's owner
page appeared, nobody asked for it  -> USER
```

Only `AGENT` pages may be closed automatically. Ownership is decided once and
never revisited.

Evidence: [E5](../experiments/page_registry/REPORT.md) — 220/220, zero user tabs
closed, including three tabs at a byte-identical URL and title with mixed
ownership.

**Constraint:** ownership cannot be reconstructed after a controller restart —
the creation events died with the process. Rediscovered pages are not `AGENT`,
so automatic cleanup after a restart is not safe without re-establishing
ownership.

## 6. Decision model — FROZEN as a source, NOT as an autonomous policy

`qwen3:8b` (Q4_K_M, digest `500a1f067a9f…`) via Ollama, temperature 0, seed 7,
`num_ctx` 8192, thinking disabled.

Evidence: [E3](../experiments/qwen_adequacy/REPORT.md) —
**`QWEN3_8B_INADEQUATE`** against the
[pre-registered threshold](../experiments/qwen_adequacy/ADEQUACY_THRESHOLD.md).
It misses the fallback tier by 0.78 points on one metric and the full bar on
four.

What it is good at: 100% schema validity, 100% determinism, 0 invented targets,
100% on easy execution, 0 injections obeyed. What it is not good at: judgment —
sequencing 33%, recognising no-valid-action 57%, constraint comparison 57%.

```text
Qwen3:8B may be the first decision SOURCE behind the deterministic boundary.
It may NOT be run as an autonomous policy.
```

Three mandatory pre-conditions before autonomy, in order: build the Verifier;
fix the table-row representation defect; re-measure against the same threshold.

## 7. Decision interface — FROZEN

A **strict single `Decision` JSON schema** via Ollama structured outputs.
Thinking disabled. One decision per controller step.

Evidence: [E2](../experiments/qwen_decision_interface/REPORT.md) — quality was
an exact tie with native tool calling (75.00% both), decided on 100% vs 90.74%
schema validity, 100% vs 98.15% determinism, 0 vs 2 multiple-action violations,
and 5.4× median / 23× p95 latency. [ADR-004](ARCHITECTURE_DECISIONS.md).

Invalid output never partially executes. It is rejected, fed back as a compact
validation error, and bounded-retried as a *decision*, never as a browser action.

## 8. Action semantics — FROZEN

```text
kinds    BROWSER_ACTION EXTRACT ASK_USER REQUEST_CONFIRMATION REPLAN FINISH FAIL
actions  CLICK TYPE SELECT PRESS SCROLL NAVIGATE BACK SWITCH_TAB NEW_TAB WAIT
```

A closed enum. Absent by construction: arbitrary JavaScript, shell, filesystem
paths, refresh/reload, raw selectors, retry counts, policy overrides.

One state-changing action per controller step
([ADR-005](ARCHITECTURE_DECISIONS.md)). Targeted actions (`CLICK`, `TYPE`,
`SELECT`, `PRESS`) require a target from the current observation.

Evidence that the closed enum is load-bearing:
[E8](../experiments/security_policy/REPORT.md) — 144 probes attempting
capabilities outside the enum, 144 denied, and each recorded as an escalation
attempt rather than silently becoming "unknown action".

## 9. Verification boundary — FROZEN in principle, NOT BUILT

Every mutating action requires an independent deterministic postcondition.
Browser success is not task success. The model never verifies itself.

Evidence that this is necessary rather than tidy:
[E3 containment analysis](../experiments/qwen_adequacy/results/containment_analysis.json)
— the PolicyEngine caught 8 of 14 forbidden decisions; the 3 that escaped were
the model clicking a **legitimate, permitted control for the wrong reason**,
which no policy engine can catch. [ADR-010](ARCHITECTURE_DECISIONS.md).

**This is the largest unbuilt piece of the frozen architecture, and the
experiments have located exactly the hole it fills.**

## 10. State and event persistence — FROZEN

Append-only SQLite journal, written with `synchronous=FULL`, committed
immediately. State is rebuilt from the journal, never from memory.

Lifecycle:

```text
OBSERVED -> INTENT_PREPARED -> INTENT_DISPATCHED -> ACTION_RESULT
         -> VERIFICATION -> INTENT_COMPLETED
```

Evidence: [E6](../experiments/side_effect_recovery/REPORT.md) — the journal is
the only thing that survived 32 real process kills.

## 11. Side-effect protocol — FROZEN

One ordering rule carries the whole design:

```text
INTENT_DISPATCHED is committed durably BEFORE the browser is touched.
```

That makes the post-crash state decidable. Ambiguity is resolved by **durable
external evidence** keyed on an operation id the agent attaches to the request.

```text
durable record found   -> DEFINITELY_EXECUTED      -> record, never replay
durable record absent  -> DEFINITELY_NOT_EXECUTED  -> safe to execute
evidence unavailable   -> AMBIGUOUS                -> WAITING_FOR_CONFIRMATION
```

Evidence: [E6](../experiments/side_effect_recovery/REPORT.md) — 32 crashes
across seven boundaries against a non-deduplicating server, **0 duplicates**;
the blind-replay control produced **20**. [ADR-014](ARCHITECTURE_DECISIONS.md).

**Constraint:** this needs a correlatable identifier to exist. Where a site
offers none, an interrupted submission is permanently ambiguous and must go to
the human. The fixture has an explicit field for it; real sites often will not.

## 12. Handoff semantics — FROZEN

```text
1  checkpoint subgoal + reason to the journal
2  WAITING_FOR_USER / WAITING_FOR_CONFIRMATION
3  human acts; the kernel is not told what they did
4  resume signal
5  invalidate ALL observations unconditionally
6  rediscover pages and ownership
7  fresh observation
8  continue the SAME subgoal
```

Step 5 precedes step 6 deliberately.

Evidence: [E7](../experiments/human_handoff/REPORT.md) — 90/90, zero stale
targets trusted, human input never overwritten, subgoal recovered across a
controller restart mid-handoff. [ADR-008](ARCHITECTURE_DECISIONS.md).

## 13. Security and policy boundary — FROZEN

A deterministic `PolicyEngine` between the model and the kernel, containing no
model. Authority order: system policy > user goal/approval > page content.

Four mechanisms: closed vocabulary; observation-scoped targets; origin
allow-list; approval as recorded state rather than prose.

Evidence: [E8](../experiments/security_policy/REPORT.md) — 272
compromised-model probes across nine attack classes, **0 bypasses**, 100%
producing the *correct* boundary; 25 benign probes, **0 false blocks**; and the
real model obeyed 0 of 16 hostile pages.

**Constraint:** the consequential-verb and secret-field matchers are patterns
over English. They will miss non-English pages, unusual labels and icon-only
buttons, and a miss means a consequential action is treated as ordinary. This is
the weakest link in the frozen design and deserves its own experiment.

## 14. Explicitly deferred

| Item | Status | Why |
|---|---|---|
| Autonomous controller loop | **deferred** | requires the Verifier and an adequate model |
| Verifier implementation | designed, evidenced as necessary, **unbuilt** | §9 |
| Visual / vision fallback | deferred | no semantic fixture has yet required it |
| Downloads and uploads | P1, untested | not exercised by any P0 experiment |
| Attach to the user's Chrome via CDP | deferred | lower fidelity; ownership assumptions break |
| Cross-task persistent memory | deferred | task-local facts first |
| Connector / API routing | deferred | the browser kernel must prove general behaviour first |
| Long 100+ page research | deferred | not a way to validate the primitive loop |
| Model fine-tuning / WebRL | deferred, conditional | only after the Verifier and the representation fix |
| Loop / progress detector | designed, unbuilt | P1 |

## 15. What this freeze does not cover

Every number above comes from **controlled localhost fixtures** with one model,
one browser, one machine. Specifically unproven:

- behaviour on live websites;
- any task longer than a single decision — no multi-step autonomous run was
  executed, by design;
- the Verifier, the loop detector and the controller state machine, none of
  which exist yet;
- attack classes not in our corpus;
- recovery when the browser crashes while the controller survives.

The freeze is an account of what the evidence supports. It is not a claim that
the system works, because the system has not been built.
