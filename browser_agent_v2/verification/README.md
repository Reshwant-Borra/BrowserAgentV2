# Verifier V1

Deterministic verification of browser action postconditions.

## Purpose

Distinguish

```text
the action ran
```

from

```text
the intended result actually happened
```

Neither the model nor the BrowserKernel is allowed to answer that. The model
cannot grade its own action ([ADR-010](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md)),
and `click() returned` is not evidence that the click accomplished anything.

Experiment 3's containment analysis is why this layer exists: the PolicyEngine
caught 8 of the model's 14 forbidden decisions, and the 3 that escaped were the
model clicking a **legitimate, permitted control for the wrong reason**. No
policy engine can catch that, because nothing about the action itself is
disallowed. All three are now caught here —
see [`tests/verification/test_qwen_replay.py`](../../tests/verification/test_qwen_replay.py).

## Boundary

```text
Decision → PolicyEngine → ActionIntent → BrowserKernel → ActionResult
                                                              │
                                    fresh observation / durable evidence
                                                              │
                                                          Verifier
                                                              │
                                                    VerificationResult
```

The Verifier sits after execution and before any controller decision. It
**reports**; it never acts. There is no retry, no reload, no refresh, no waiting
loop and no model call anywhere in this package — all four are asserted by
[`test_contracts_unit.py`](../../tests/verification/test_contracts_unit.py),
which greps the package's own imports and source.

Production code here imports nothing from `experiments/`, nothing from
Playwright, and nothing from any model runtime. It consumes the structural
protocols in [`evidence.py`](evidence.py); `KernelEvidenceSource` adapts any
BrowserKernel-shaped object and is the single place kernel exceptions are
translated into `EvidenceUnavailable`.

## Input and output

```python
verifier = Verifier(source, durable=..., artifacts=...)
result = verifier.verify(VerificationRequest(
    postcondition=FieldValueEquals(page_id="page_1", target="obs_42:f0:e7",
                                   expected="Tampa", name="Search"),
    observation_id_before="obs_42",     # what the decision was made against
    execution_status="OK",
    intent_id="intent_9",
))
```

`VerificationResult` carries `status`, `reason`, `verifier_type`, `checks`,
`evidence` and `confidence`. It is frozen, JSON-serialisable and deliberately
compact — a result is stored for every action, so strings are truncated at 240
characters and lists at 12 entries. It never embeds a whole observation.

## The three answers

| | meaning |
|---|---|
| `SATISFIED` | fresh evidence shows the postcondition is true |
| `NOT_SATISFIED` | fresh evidence shows it is **false** |
| `AMBIGUOUS` | evidence is insufficient or contradictory |

`AMBIGUOUS` is not a catch-all. It is reachable only through
`EVIDENCE_UNAVAILABLE`, `STALE_EVIDENCE`, `EVIDENCE_CONTRADICTORY` and
`FIELD_AMBIGUOUS`; the constructors in [`contracts.py`](contracts.py) raise
`ValueError` if a definite reason is passed to `ambiguous()` or an evidence
reason to `not_satisfied()`. A condition that is definitively false is
`NOT_SATISFIED`, never "unknown".

**`AMBIGUOUS` must never be turned into a retry.** For a consequential action
that is the whole point: the controller reconciles or asks the user
([ADR-014](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md)). The Verifier emits no
instruction of any kind, which is asserted by
`test_ambiguous_result_carries_no_retry_instruction`.

## Supported postconditions

| Postcondition | Answers |
|---|---|
| `FieldValueEquals` | does the control hold exactly this value? |
| `SelectValueEquals` | is this option **value** (not label) selected? |
| `UrlIs` | is the page at this destination? (`EXACT` / `CONTAINS` / `REGEX`) |
| `ElementPresence` | is an element with this role+name present / absent? |
| `TextPresence` | does page text contain / not contain this? |
| `PageState` | does this page exist, is it active, who opened it? |
| `DialogState` | is a dialog of this kind open, with this message? |
| `DownloadPresent` | is there a **completed** artifact matching this? |
| `OperationRecorded` | is this operation durably recorded outside the browser? |
| `AllOf` | do all of the above hold? |

`AllOf` is the only combinator. A definite failure in any part makes the whole
`NOT_SATISFIED` even if another part is unknown — a definite no outranks an
unknown. There is no `AnyOf` and no `Not`; neither has an established use and
each would be a step toward a rule DSL.

**There is no `StateChanged` type.** A no-op is detected by the postcondition
the action was supposed to satisfy being false — see `test_true_noop_is_rejected`.
Whole-page diffing would flag every irrelevant animation.

## Freshness

The Verifier takes its own observation at verification time; a caller cannot
hand it a snapshot. It additionally requires that observation to post-date
`observation_id_before`, so replaying the pre-action state is refused with
`STALE_EVIDENCE` rather than answered.

This matters because the stale snapshot often *does* contain a satisfying
state — `test_pre_action_observation_cannot_satisfy` constructs exactly that
case. `test_disabling_the_freshness_guard_produces_a_false_success` disables the
guard and shows the false success appear, which is what makes the passing test
mean something.

## Page and frame scoping

Every postcondition is scoped to a `page_id`, which is the identity minted at
the page-creation event (Experiment 5) — never a title, URL or tab index.
`PageState` can additionally assert a URL and an opener, but identity is always
the id.

Frames are minted identities under Observation Contract V1, issued at the
frame's attach event and never reused, so a `frame_id` is trusted directly:

* `frame_id=MAIN_FRAME` — this page's main frame, whatever its minted id.
* `frame_id="fr_7"` — exactly that frame. If it has detached the element is
  reported missing; another frame can never answer for it.
* `frame_id=None` — any frame on the page.

Before V1 the kernel numbered frames positionally, so detaching a frame
renumbered the rest and an id could transfer between frames. The Verifier
defended against that by refusing any unpinned non-main frame scope; that
workaround is gone because the defect is gone.

`ElementPresence.group_cells` scopes to a table row — "the Open button in
B. Lindqvist's row" — by matching the row's structured cells rather than a
rendered label.

## Field identity after a rerender

`FieldValueEquals` resolves in a fixed order:

1. the observed **node**, via the original target — strongest evidence
   ([ADR-012](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md));
2. if that node is gone, a **unique** semantic match in the fresh observation;
3. if more than one control matches, `AMBIGUOUS` — never a coin flip;
4. if none matches and the page is observable, `NOT_SATISFIED` — the field is
   genuinely not there.

## Consequential actions

`OperationRecorded` is the only postcondition whose evidence comes from outside
the browser, because browser confirmation text is exactly what a crash removes.

```text
durable record found      → SATISFIED
durable record absent     → NOT_SATISFIED
channel unreachable       → AMBIGUOUS
no durable source wired   → AMBIGUOUS
```

Verification is side-effect free: `test_ambiguous_verification_performs_no_side_effect`
verifies five times against the non-deduplicating fixture server and asserts the
arrival count is unchanged.

## Known limitations

Three earlier limitations were removed by
[Observation Contract V1](../../03_DECISIONS/OBSERVATION_CONTRACT_V1.md): bare
`<div>` text is now observable, `TextPresence` is frame-scoped, and frame ids
are minted identities so the `section`-pin workaround is gone. What remains:

1. **No ArtifactStore exists in production.** `DownloadPresent` is tested
   against a harness implementation of the `ArtifactStore` protocol. Downloads
   remain P1 and untested end to end per the architecture freeze.
2. **Frame ids do not survive a controller restart.** They are per kernel
   instance; a restart re-mints them.
3. **Groups cover rows and list items only.** Card grids and other implicit
   groupings are not represented, so `group_cells` cannot scope to them.
4. **Scope.** This verifies single actions against controlled localhost
   fixtures. It says nothing about multi-step task correctness, live websites,
   or whether an autonomous agent would work — none of which exist yet.

## Reproduction

```bash
python -m pytest tests/verification -q                       # full suite
python -m pytest tests/verification/test_contracts_unit.py   # no browser
python -m pytest tests/verification/test_stress_and_matrix.py -p no:randomly
```

Stress counts and the classification matrix are written to
`tests/verification/results/stress_and_matrix.json`.
