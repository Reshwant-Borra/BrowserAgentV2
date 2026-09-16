# Architecture Decision Records

This file records current decisions and their confidence. A decision can change only when new evidence or a reproducible test justifies it.

## ADR-001 — Browser kernel abstraction

**Decision:** ACCEPTED.

All browser operations go through a `BrowserKernel` interface. No controller/model code depends directly on Playwright MCP/CDP internals.

**Reason:** protects the architecture from a bad browser-runtime choice and lets us evaluate MCP vs direct Playwright without rewriting upper layers.

## ADR-002 — BrowserKernel runtime: direct Playwright

**Decision:** ACCEPTED. Supersedes the earlier "Playwright MCP first candidate".

**Evidence:** [Experiment 1](../experiments/browser_kernel/REPORT.md). Both
candidates ran the identical 35-case suite through the identical interface,
3 passes each.

```text
direct Playwright  105/105 PASS, 0 unsafe, 0 inconsistent
Playwright MCP      90/105 PASS, 0 unsafe, 12 fail-safe, 3 unsupported
```

Neither runtime ever did the wrong thing. MCP was disqualified by the pass rule
stated in `04_TESTING/MASTER_VALIDATION_PLAN.md` section 2 **before** the
experiment ran - "inability to guarantee target freshness, tab ownership, typed
errors, or pause/resume is disqualifying":

- no page-creation event and no opener, so a popup's owner can only be `UNKNOWN`;
- no document-identity token, so same-URL document replacement is invisible and
  the Experiment 4 invalidation policy cannot be expressed on top of it;
- navigation timeout is not bounded through the interface;
- `contenteditable` values cannot be read back, so writes cannot be verified.

It is also ~13x slower per action (click 597 ms vs 46 ms median).

ADR-001 did its job: the candidate was swapped without touching anything above
the `BrowserKernel` interface. MCP remains a legitimate future option if it
gains creation events and document identity; it was evaluated at `0.0.81`.

## ADR-003 — Dedicated browser profile

**Decision:** ACCEPTED for MVP.

Use a BrowserAgent-owned persistent Chromium profile rather than attaching to arbitrary user Chrome tabs by default.

**Reason:** reduces tab-ownership ambiguity, keeps login state, and makes browser lifecycle reproducible.

Existing-browser attachment can be revisited later as an optional mode.

**Evidence:** [Profile strategy](../experiments/profile_strategy/REPORT.md),
36/36 runs. Cookies and `localStorage` both survive a controller restart, a
manually completed login is still authenticated afterwards, two agent profiles
are isolated from each other, and the user's real Chrome profile directory is
never written to. Chromium's own profile lock prevents two controllers sharing
one profile, though the controller should still enforce single ownership rather
than rely on that.

This gate is also what makes handoff work at all: the controller can die while
`WAITING_FOR_USER` and the human's session survives, because it lives in the
profile rather than in the controller.

## ADR-004 — Structured model decisions: strict JSON

**Decision:** ACCEPTED. The mechanism is a strict single `Decision` JSON schema
(Ollama structured outputs), thinking mode disabled.

**Evidence:** [Experiment 2](../experiments/qwen_decision_interface/REPORT.md).
166 frozen cases over real kernel observations, 108 held out, 216 runs per arm.

Decision quality was an exact tie (75.00% end-to-end usable decisions both), so
the choice was made on the properties the architecture depends on:

| | strict JSON | native tools |
|---|---:|---:|
| schema-valid output | 100.00% | 90.74% |
| consistency at temperature 0 | 100.00% | 98.15% |
| multiple-action violations | 0 | 2 |
| latency median / p95 | 811 ms / 976 ms | 4377 ms / 22312 ms |
| completion tokens | 11,186 | 112,478 |

Native tool calling also emits **nothing at all** unless thinking is enabled
(empty content, empty `tool_calls`, `done_reason: stop`), which is the source of
its latency and token cost.

Recorded against this decision: tool calling was genuinely better at deciding
*whether to act at all* (injection 95.24% vs 66.67%, handoff 60% vs 40%). That
advantage is confounded with thinking mode and is not explained away. If the
interface question is reopened, the experiment to run is strict JSON with a
separate reasoning pass.

## ADR-005 — One state-changing action per controller step

**Decision:** ACCEPTED for MVP.

**Reason:** any state change can invalidate the observation and its targets. This rule maximizes debuggability and prevents stale action sequences.

## ADR-006 — No model-callable refresh

**Decision:** ACCEPTED.

Reload/refresh is not in the normal model action schema. If a very specific runtime failure later requires reload, it belongs in deterministic recovery policy with a reproducible test.

## ADR-007 — SQLite first

**Decision:** ACCEPTED.

Use SQLite for task state, facts, checkpoints, and trace metadata. Do not add a vector database until a demonstrated retrieval problem requires it.

## ADR-008 — Human handoff is a runtime state

**Decision:** ACCEPTED.

Password, MFA, CAPTCHA, ambiguous account choice, consent, and high-impact submission use explicit `WAITING_FOR_USER` / `WAITING_FOR_CONFIRMATION` states.

**Evidence:** [Experiment 7](../experiments/human_handoff/REPORT.md), 90/90 runs
including a controller restart during handoff. Zero pre-handoff targets were
trusted after resume, and the human's own input was never overwritten.

The resume order matters and is part of the decision: invalidate **before**
rediscovering pages, or there is a window in which a stale target can be used
against a fresh-looking page list.

## ADR-009 — Accessibility-first grounding

**Decision:** ACCEPTED for primary path.

Use semantic/accessibility observation by default, with selective DOM/CDP enrichment and visual fallback rather than full DOM/screenshot-first operation.

## ADR-010 — Deterministic verification after state change

**Decision:** ACCEPTED, and now shown to be load-bearing rather than hygiene.

Every mutating browser action requires a postcondition result. Browser API
success alone is insufficient.

**Evidence:** [Experiment 3 containment analysis](../experiments/qwen_adequacy/results/containment_analysis.json).
Of the model's 14 forbidden decisions, the PolicyEngine caught 8. The 3 that
escaped were the model clicking a **legitimate, permitted control for the wrong
reason** - selecting a 96.50 service when the goal said under 50; opening the
wrong table row. No policy engine can catch those, because nothing about the
action itself is disallowed.

The Verifier is therefore the only layer that can close the remaining gap, and
it must exist before any autonomous run.

**Built and proven:** `browser_agent_v2/verification/`. All three preserved
wrong-but-permitted Qwen decisions (AD-M22, AD-M23, AD-M29) are replayed from
the committed P0 evidence through PolicyEngine (still `ALLOW`) and the
BrowserKernel (click still succeeds), and all three are caught as
`NOT_SATISFIED`. 280 stress runs across ten categories produced **0 false
SATISFIED**. See [`browser_agent_v2/verification/README.md`](../browser_agent_v2/verification/README.md).

## ADR-011 — No site-specific architecture

**Decision:** ACCEPTED.

Do not add `CanvasAgent`, `TravelAgent`, etc. as core architectural branches. Different tasks should compose the same primitives. Specialized connectors/adapters may be added later when they provide clear deterministic value.

## ADR-012 — Target identity is bound to a live DOM node

**Decision:** ACCEPTED.

A target resolves through a handle to the **node** observed, never through a
selector, accessible name, position or URL. Validity requires: node still
connected, document token unchanged, frame attached, page open.

**Evidence:** [Experiment 4](../experiments/observation_invalidation/REPORT.md),
672 runs. The `UNSAFE_NAME_RESOLVE` control - which re-resolves by role and
accessible name, i.e. what an agent does when it remembers "the Confirm button"
rather than a node - produced **84 wrong-target executions** across 7 scenarios,
including ordinary SPA navigation and ordinary React rerenders.

The `UNSAFE_URL_ONLY` control produced **zero** wrong targets despite skipping
every freshness check, because it still held the node handle. That is what
establishes node binding, rather than the invalidation rule, as the mechanism
that matters. It is still rejected: it produced 96 untyped `INTERNAL` errors
where node identity produced precise typed ones, and typed failure
classification is required for the controller to choose a transition.

Adopted policy: `NODE_IDENTITY` - the most permissive policy that never permits
incorrect stale targeting, per MASTER_VALIDATION_PLAN section 4.

## ADR-013 — Explicit invalidation outranks the invalidation policy

**Decision:** ACCEPTED.

`invalidate_all_observations(reason)` is unconditional and is honoured by every
policy. The invalidation policy governs what the kernel notices by itself;
explicit invalidation is the controller stating that the world changed
underneath it.

**Evidence:** [Experiment 7](../experiments/human_handoff/REPORT.md). Five of
nine handoff scenarios initially failed because explicit invalidation was only
consulted under one policy. When a human merely types into a field or opens a
tab, no node is disconnected and no document is replaced - the kernel is *right*
that nothing detectable changed, and only an explicit signal can help.

## ADR-014 — The side-effect protocol rests on one ordering rule

**Decision:** ACCEPTED.

`INTENT_DISPATCHED` is committed durably **before** the browser is touched.
Ambiguity is resolved by durable external evidence keyed on an operation id, and
when that channel is unavailable the task escalates to the user rather than
retrying.

**Evidence:** [Experiment 6](../experiments/side_effect_recovery/REPORT.md).
32 real process kills across seven boundaries against a server that does not
deduplicate: **0 duplicate side effects**. The `blind_replay` control produced
**20** under identical conditions.

Known limit: this requires a correlatable identifier to exist. On a site that
offers none, an interrupted submission is permanently ambiguous and must go to
the human. That is by design, and it is site-dependent.

## ADR-015 — A frame id is a positional index, not an identity

**Decision:** ACCEPTED.

A postcondition may not be scoped to a non-main frame by `frame_id` alone. The
main frame (`f0`) is stable; any other frame must be pinned by a content anchor
(`section`, the nearest heading inside that frame's own document). An unpinned
non-main frame scope is answered `AMBIGUOUS`, never guessed.

**Evidence:** found while building the Verifier. The kernel assigns frame ids by
enumerating the frame list, so detaching a frame renumbers the rest. On the
frames fixture, `f1` means "Child (primary)" before a detach and "Child
(secondary)" after — while `frame_tree_version` stays at 3, so a count-based
guard does not catch it. Both frames contain a control named "Confirm", so an
index-trusting verifier reports a wrong-frame **false success**. This is the same
defect class as identifying a tab by index, which
[ADR/Experiment 5](../experiments/page_registry/REPORT.md) ruled out for pages.

Regression tests: `test_unpinned_child_frame_scope_is_refused`,
`test_frame_renumbering_cannot_produce_a_false_success`, and the mutation test
`test_disabling_frame_pinning_produces_a_wrong_frame_false_success`, which shows
the false success reappearing when the guard is removed.

**Owed to the BrowserKernel, not fixed here:** the proper fix is a stable frame
identity minted at frame-attach time. The Verifier's `section` pin is a correct
but defensive workaround, and it is the reason frame-scoped verification is more
awkward than page-scoped verification.

## Rejected approaches for the MVP

- giant one-shot prompt that plans and executes a full web task;
- raw DOM in every model prompt;
- unrestricted JavaScript generated by Qwen;
- shell execution as a browser fallback;
- automatic refresh as generic recovery;
- arbitrary action retries;
- treating browser history as model memory;
- large site-specific skill library;
- multi-agent manager/worker architecture;
- vision-first coordinate clicking for normal DOM controls.

## Decision discipline

When implementation evidence conflicts with an ADR:

1. capture a minimal reproduction;
2. identify which assumption is false;
3. update the ADR/research document;
4. change the smallest relevant layer;
5. add a regression test.

Do not silently patch prompts or add another fallback layer.
