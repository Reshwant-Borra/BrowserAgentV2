# P0 consolidation and go / no-go

**Campaign:** `experiment/p0-gate-campaign`
**Index:** [`../P0_EXPERIMENT_INDEX.md`](../P0_EXPERIMENT_INDEX.md)
**Freeze:** [`../../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md`](../../03_DECISIONS/ARCHITECTURE_FREEZE_V1.md)

## Outcome

```text
P0_COMPLETE_WITH_PROVISIONAL_ITEMS
```

All nine P0 gates are resolved. Eight resolved positively. One —
`QWEN3_8B_INADEQUATE` — resolved negatively, which is a resolution, not an open
question: we know the answer and we know what it constrains.

## Gate summary

| Gate | Verdict | Scale | Invariant violations |
|---|---|---:|---:|
| Browser kernel | `ADOPT_DIRECT_PLAYWRIGHT` | 210 runs | 0 unsafe |
| Observation invalidation | `INVALIDATION_RESOLVED` | 672 runs | 0 wrong-target (safe policies) |
| Page registry | `PAGE_REGISTRY_RESOLVED` | 220 runs | 0 user tabs closed |
| Side-effect recovery | `SIDE_EFFECT_RECOVERY_RESOLVED` | 60 trials, 32 crashes | 0 duplicates |
| Human handoff | `HANDOFF_RESOLVED` | 90 runs | 0 stale targets trusted |
| Profile strategy | `DEDICATED_PROFILE_RESOLVED` | 36 runs | 0 |
| Policy boundary | `POLICY_BOUNDARY_RESOLVED` | 297 probes | 0 bypasses, 0 false blocks |
| Decision interface | `ADOPT_STRICT_JSON` | 432 model calls | 0 hallucinated action targets |
| Model adequacy | **`QWEN3_8B_INADEQUATE`** | 166 model calls | misses the pre-registered bar |

Roughly 2,200 experiment runs and 1,000 model calls in total. Every raw row,
every environment capture and every failure is committed under
`experiments/*/results/`.

## What the negative controls established

Three arms were designed to fail. Two did, and the third taught us more by not
failing.

| Control | Result | What it established |
|---|---|---|
| `UNSAFE_NAME_RESOLVE` | **84 wrong-target executions** | Re-resolving a target by accessible name is catastrophic, and not only on adversarial pages — it fires on ordinary SPA routing and React rerenders. |
| `blind_replay` | **20 duplicate side effects** | The reconciliation protocol is doing real work; the crash boundaries are not harmless. |
| `UNSAFE_URL_ONLY` | **0 wrong-target** | Designed to be unsafe, wasn't — because it still held a node handle. This is what proved the mechanism is **node binding**, not the invalidation rule. |

Without the third control we would have credited the invalidation policy for
safety that node binding was providing.

## Defects the campaign found

Not confirmations — things that were wrong and are now fixed.

**In the kernel:**

1. `textContent` assignment for `contenteditable` bypassed `input` events, so
   the page's own state silently diverged from the DOM.
2. A pending native dialog deadlocked every `evaluate()`. "Dialog is an explicit
   kernel state" turned out to be a correctness requirement, not tidy design.
3. Closing the active tab left a dangling page pointer.
4. The initial page of a browser we launched was attributed to the user.
5. `invalidate_all_observations()` was silently ignored under the adopted
   policy — the handoff invariant was not actually being enforced.
6. Hidden nodes leaked into observation text, reporting a validation error that
   was not on screen.

**In the observation representation:**

7. Target ids rendered as bare leading tokens; the model copied whole lines.
8. Dropdown options were invisible, so a correct `SELECT` argument was
   impossible to produce.
9. Table-row context is still missing — **diagnosed, deliberately unfixed**, see
   below.

**In the harness** (never charged against a candidate):

10. A stale fixture server shadowed port 8799 via Windows `SO_REUSEADDR` and
    silently corrupted a round of results. The cluster now mints a nonce and
    refuses to start if anything else answers.
11. Four MCP "failures" were our adapter's bugs — MCP *does* encode frame scope
    in refs and *does* report modal state. Fixed and re-run rather than reported.
12. `full_decision_accuracy` ignored unparseable output, so an interface scored
    better for failing. Corrected, against the eventual winner.
13. 28 tool-calling "hallucinations" were a page id in `EXTRACT`'s optional
    target slot — zero on any click or type. Split by severity.

## The one thing we chose not to fix

Case AD-M22 in [E3](../qwen_adequacy/REPORT.md): a table row has no heading, so
three identical `Open` buttons cannot be distinguished by the observation. This
is a real representation defect of the same class we already fixed twice.

Fixing it would move the adequacy metric by about 1.2 points — enough to flip
`QWEN3_8B_INADEQUATE` to `QWEN3_8B_PROVISIONAL`. It was found **after** the
held-out run, so fixing it and re-running would be tuning to the evaluation set.
It is recorded as the first action of the next iteration, against a new held-out
version.

The threshold was written down in
[`ADEQUACY_THRESHOLD.md`](../qwen_adequacy/ADEQUACY_THRESHOLD.md) before the run
and has not moved. `PROVISIONAL` was missed by 0.78 points on one metric.

## Genuinely unproven

Ranked by how much it should worry an implementer.

1. **No multi-step autonomous task has ever run.** Every experiment measures one
   decision or one mechanism. Composition is unproven, deliberately — the brief
   was to resolve gates, not to build the agent.
2. **The Verifier does not exist**, and E3 showed it is the only layer that can
   catch the model's remaining failure class (clicking a legitimate control for
   the wrong reason).
3. **The model is not adequate for autonomy.** Judgment failures — sequencing
   33%, no-valid-action 57%, comparison 57%.
4. **Live websites are untested.** Everything here is localhost fixtures we
   wrote. Real sites bring CAPTCHAs, consent walls, drift and rate limits.
5. **The security corpus is a list of attacks we thought of.** Zero bypasses
   means zero bypasses for those classes.
6. **The consequential-verb matcher is English patterns**, and a miss silently
   downgrades a consequential action to an ordinary one.
7. **Ownership cannot be reconstructed after a controller restart.**
8. **Ambiguity resolution needs a correlatable identifier** the site may not
   offer.
9. Downloads, uploads, the loop detector and virtualised lists are untouched.
10. Browser-crash-with-controller-alive was not exercised.

## Recommendation

**Freeze the architecture. Do not start the autonomous build.**

The mechanical layers — kernel, target identity, page ownership, profile,
crash safety, handoff, policy — are proven to a level that justifies freezing
them, with the constraints named in the freeze document. The decision layer is
not, and the gap is specific and measured rather than vague.

The implementation order the evidence supports:

1. **Verifier first.** It is the named hole, and it does not need a better model.
2. Fix the table-row representation defect; re-measure on a new held-out set.
3. Only then the controller state machine.
4. Only then autonomy, and only if the model clears the pre-registered bar.

The two-day execution plan should be re-sequenced accordingly: it currently
assumes a Day-2 autonomous loop, and the evidence says the Verifier has to come
before that.
