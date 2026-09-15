# Experiment 7 — human handoff and resume

**Gate:** `Human handoff/resume` (P0, was `PROVISIONAL`)
**Verdict:** `HANDOFF_RESOLVED`
**Evidence:** [`results/experiment7_raw.json`](results/experiment7_raw.json)
**Reproduce:** `BAV2_PORT_BASE=8840 python -m experiments.human_handoff.run_handoff --reps 10`

## Question

Can the agent safely pause for a human and resume without trusting stale state?

Invariant: after a human has touched the browser, **no pre-handoff target is
trusted.** Not "usually", and not "unless the page looks unchanged".

## Method

9 scenarios × 10 repetitions = **90 runs**, fresh kernel and profile per run.

The human is simulated by driving the raw Playwright page directly — filling
fields, clicking, navigating, opening and closing tabs — entirely outside the
kernel's API. The kernel genuinely does not know what happened, which is the
whole point.

Each scenario records every target from the pre-handoff observation, runs the
handoff cycle, then attempts to resolve **all of them**. A single survivor is
scored `FATAL_STALE_TRUSTED`.

## Results

| # | scenario | result |
|---|---|---|
| HH-01 | human completes the full login (password → MFA → CAPTCHA → account) | 10/10 PASS |
| HH-02 | human navigates the page away | 10/10 PASS |
| HH-03 | human rerenders the page in place (same URL, same document) | 10/10 PASS |
| HH-04 | human opens a new tab | 10/10 PASS |
| HH-05 | human closes a tab | 10/10 PASS |
| HH-06 | human signs in as a *different* account than expected | 10/10 PASS |
| HH-07 | agent does not overwrite what the human typed | 10/10 PASS |
| HH-08 | confirmation handoff around a consequential control | 10/10 PASS |
| HH-09 | controller restart *during* handoff | 10/10 PASS |

```text
90 runs, 90 PASS
pre-handoff targets trusted after resume: 0
failures: 0
harness errors: 0
```

## The defect this experiment found

The first run failed five of nine scenarios with `FATAL_STALE_TRUSTED`, and the
cause was an architecture bug rather than a fixture problem.

`invalidate_all_observations()` existed and was being called on resume, but the
resolver only consulted it under the `STRICT_SUPERSEDE` policy. Under the
adopted `NODE_IDENTITY` policy the call did nothing at all. In the scenarios
where the human merely *typed into a field* or *opened a tab*, no node was
disconnected and no document was replaced, so every pre-handoff target remained
resolvable — and the kernel was right that nothing detectable had changed. It
simply had no way to be told.

The fix separates two different things that were conflated:

```text
invalidation policy  -> what the kernel can notice on its own
explicit invalidation -> the controller stating that the world changed
                         underneath it, which no DOM inspection could detect
```

Explicit invalidation is now unconditional and outranks the policy. It is not a
heuristic; it is an order. HH-04 and HH-07 are precisely the cases that cannot
be solved any other way, because the page is genuinely unchanged from the DOM's
point of view.

## HH-07: not overwriting the human

The inverse failure matters as much. After the human types `human-typed-name`
into the username field and the agent resumes, the field must still contain what
the human typed. Invalidating targets must not mean re-running the pre-handoff
plan. In all 10 runs the human's input survived and the agent's fresh
observation reported it.

## HH-09: restart during handoff

The controller is killed while `WAITING_FOR_USER`; the human then finishes the
login; a fresh controller starts against the same persistent profile. In all 10
runs:

- the checkpoint was recoverable and the active subgoal was restored from the
  journal;
- the authenticated session survived (the profile carried it);
- every pre-restart target failed closed.

This is the one scenario that exercises the journal, the profile and the
invalidation rule together.

## The resume protocol as implemented

```text
1  checkpoint the subgoal and the reason to the journal
2  enter WAITING_FOR_USER / WAITING_FOR_CONFIRMATION
3  (human acts; the kernel is not told what they did)
4  resume signal
5  invalidate ALL observations unconditionally
6  rediscover pages from the registry, recording current ownership
7  take a fresh observation
8  continue the SAME subgoal
```

Step 5 before step 6 matters: rediscovering pages first would create an
opportunity to act on a stale target with a fresh-looking page list.

## Verdict

```text
HANDOFF_RESOLVED
```

90/90, zero stale targets trusted, including the two scenarios where the DOM was
genuinely unchanged and only an explicit signal could have helped. The gate moves
from `PROVISIONAL` to `RESOLVED`.

## What this does not establish

- The CAPTCHA fixture is a checkbox, not a real challenge. It tests the *handoff
  protocol*, not CAPTCHA handling, and the agent is scored on refusing to tick
  it rather than on solving anything.
- Session expiry mid-task was not tested.
- The human is simulated deterministically; real humans take unbounded time and
  may act while the agent believes it is still running.
