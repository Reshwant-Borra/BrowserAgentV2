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

Frames are the subtle one. **A kernel `frame_id` is a positional index, not an
identity.** On the frames fixture, detaching the same-origin child renumbers the
rest so that `f1` means "Child (primary)" before and "Child (secondary)" after,
while the frame count stays at 3 — and both contain a control named "Confirm".
Trusting the index therefore produces a wrong-frame false success. So:

* `frame_id="f0"` (main frame) is stable and needs nothing more.
* Any other frame must be pinned with `section` — the nearest heading inside
  that frame's own document, which does not shift when siblings come and go.
* A non-main frame with no `section` is answered `AMBIGUOUS`
  (`FRAME_ID_NOT_A_STABLE_IDENTITY`), never guessed.

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

These are real and deliberately not worked around.

1. **Observation text excludes bare `<div>` content.** The observation collects
   `h1`–`h3`, `p`, `li`, `td`, `label`, `span`. Text in a `<div>` is invisible to
   `TextPresence` even though a person can read it. This is why
   `submit_op.html`'s confirmation is unverifiable by text, and why
   **Experiment 6's worker could never record a SATISFIED verification** — its
   check was `f"Reference {op}" in text_blocks`. Pinned by
   `test_known_limitation_text_in_a_bare_div_is_invisible`. Fixing it means
   changing the observation format, which is frozen for this gate.
2. **`TextPresence` is main-frame only.** Observation text is collected for `f0`
   alone, so a frame-scoped text assertion returns `AMBIGUOUS`. Use
   `ElementPresence`, which is frame-aware.
3. **Frame identity is not stable in the kernel.** The Verifier works around it
   by requiring a `section` pin. The proper fix — minting a stable frame id at
   frame-attach time — belongs to the BrowserKernel, not here.
4. **No ArtifactStore exists in production.** `DownloadPresent` is tested
   against a harness implementation of the `ArtifactStore` protocol. Downloads
   remain P1 and untested end to end per the architecture freeze.
5. **Scope.** This verifies single actions against controlled localhost
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
