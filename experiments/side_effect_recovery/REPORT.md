# Experiment 6 — ambiguous side-effect and crash recovery

**Gate:** `Ambiguous side-effect protocol` (P0, was `OPEN`)
**Verdict:** `SIDE_EFFECT_RECOVERY_RESOLVED`
**Evidence:** [`results/experiment6_raw.json`](results/experiment6_raw.json)
**Reproduce:** `BAV2_PORT_BASE=8830 python -m experiments.side_effect_recovery.run_side_effects --reps 4`

## Question

Can BrowserAgent survive a crash around a state-changing operation without
blindly performing it twice?

Critical invariant: **zero duplicate side effects caused by blind retry.**

## Method

The fixture server is deliberately a **worst-case web application**: it runs
with `dedupe=false`, so submitting the same `operation_id` twice really performs
the effect twice. Server-side idempotency would mask an agent-side double
submit, so it is switched off. Effects are counted from the server's durable
SQLite ledger, never from the agent's own logs.

Crashes are real. The worker calls `os._exit(70)`, which skips every `finally`
block, `atexit` hook, buffer flush and destructor. Anything not already
committed to the journal is gone. Recovery then runs in a **separate process**
with nothing in memory.

Seven boundaries, 4 repetitions, two recovery policies:

```text
1  before intent commit
2  after intent commit, before execution
3  during execution
4  after the server committed, before the browser result returned
5  after the result, before the ActionResult commit
6  after the ActionResult commit, before verification
7  during reconciliation itself
```

Boundary 4 uses a `post_delay_ms` on the endpoint: the ledger write has already
happened while the HTTP response is still open, so the controller dies knowing
nothing while the world has already changed. Boundary 7 crashes the *recovery*
process after it has classified but before it persists anything.

## Results

| policy | trials | crashes injected | **duplicate side effects** |
|---|---:|---:|---:|
| `reconcile` (architecture under test) | 32 | 32 | **0** |
| `blind_replay` (forbidden control) | 28 | 28 | **20** |

Final effect counts per operation:

| policy | 0 effects | 1 effect | 2 effects |
|---|---:|---:|---:|
| `reconcile` | 4 | 28 | **0** |
| `blind_replay` | 4 | 4 | **20** |

`reconcile` recovery decisions:

| decision | n |
|---|---:|
| `RECORD_AS_DONE_NO_REPLAY` | 20 |
| `SAFE_TO_EXECUTE` | 8 |
| `ESCALATE_TO_USER_WAITING_FOR_CONFIRMATION` | 4 |

The control arm duplicated at exactly the four boundaries where the effect had
already landed (`during_execute`, `after_server_committed_before_result`,
`after_result_before_result_commit`,
`after_result_commit_before_verification`) plus `during_reconciliation`. That is
the evidence that the safe policy is doing real work rather than the crash
points being harmless.

## The one ordering rule everything rests on

```text
INTENT_DISPATCHED is committed to the journal BEFORE the browser is touched.
```

Without it, a `PREPARED` intent and an executed one are indistinguishable after
a crash, and *every* crash would be ambiguous. With it, the post-crash state
machine is decidable:

| journal state | conclusion | basis |
|---|---|---|
| no open intent | `DEFINITELY_NOT_EXECUTED` | nothing was ever dispatched |
| `PREPARED` | `DEFINITELY_NOT_EXECUTED` | the ordering rule guarantees the browser was never touched |
| `RESULT_RECORDED` / `VERIFIED` | `DEFINITELY_EXECUTED` | the result is already durable |
| `DISPATCHED` | **unknown from memory alone** | must be resolved externally |

## Resolving the genuinely ambiguous case

A `DISPATCHED` intent is the interesting one, and the agent's own state cannot
settle it. It is resolved by **durable external evidence**: the intent carries an
`operation_id` written into the request, so recovery asks the world
(`GET /api/op?operation_id=...`) rather than guessing.

```text
durable record found      -> DEFINITELY_EXECUTED    -> record it, never replay
durable record absent     -> DEFINITELY_NOT_EXECUTED -> safe to execute
evidence channel down     -> AMBIGUOUS              -> WAITING_FOR_CONFIRMATION
```

The `evidence=unavailable` variant is run explicitly, four times. In every one,
recovery chose `ESCALATE_TO_USER_WAITING_FOR_CONFIRMATION` and produced zero
duplicates. **Unresolvable ambiguity becomes a human decision, not a retry.**

Boundary 7 confirms reconciliation is itself restartable: the crashed pass
persisted nothing, so the second pass reached the same conclusion from the same
durable evidence.

## What this requires of the rest of the system

This result is contingent on a property the agent must *create*, not one it
gets for free: **a correlatable operation id must be attached to the request
before it is sent.** The fixture form has an explicit field for it. On a real
site with no such field, the equivalent evidence must come from somewhere else —
a confirmation number, an idempotency header, a distinguishing record in a list
view — and if no such channel exists, every interrupted submission on that site
is permanently ambiguous and must go to the human.

That is a genuine limit of the protocol and belongs in the freeze document, not
in a footnote.

## Verdict

```text
SIDE_EFFECT_RECOVERY_RESOLVED
```

32 injected crashes across all seven boundaries, zero duplicate side effects,
against a server that does not deduplicate. The forbidden control produced 20
duplicates under identical conditions.

## What this does not establish

- One state-changing operation was tested (a form POST with an explicit
  operation id). Multi-step transactions were not.
- The browser process survived every crash; a simultaneous browser + controller
  crash was not exercised.
- Sites that offer no correlatable identifier will produce permanent ambiguity.
  That is by design, but it means the protocol's usefulness is site-dependent in
  a way the controlled fixture flatters.
