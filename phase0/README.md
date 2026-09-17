# Phase 0 Capability Harness

This directory is **experimental measurement infrastructure**, not the
ComputerAgent product. It exists to answer, with measured evidence
rather than assumption, two Phase 0 questions from `docs/BUILD_SPEC.md`:

- **A.** Can Playwright perform useful browser actions without moving
  the user's physical cursor, stealing foreground application focus, or
  interfering with unrelated user activity?
- **B.** Can macOS Accessibility (AX) perform semantic desktop actions
  without moving the physical cursor, and under exactly what conditions
  does it steal application/window/keyboard focus?

See `docs/CLAUDE.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`,
`docs/BUILD_SPEC.md`, `docs/DECISIONS.md`, and `docs/ROADMAP.md` for the
source-of-truth hierarchy this harness operates under. Nothing here
overrides those documents; it produces evidence they can be updated
from.

## Directory layout

```
phase0/
  schemas/        typed, versioned evidence schema (ExperimentObservation)
  harness/        reusable pipeline: observers, classification, runner, persistence, positive control
  fixtures/       deterministic local targets (browser HTML pages, a tiny AX-observable Cocoa app)
  experiments/
    browser_background/   Playwright experiment
    macos_ax/              macOS Accessibility experiment
  results/        generated JSONL evidence + summaries (gitignored except .gitkeep)
tests/phase0/     unit tests (fake observers, no real desktop control)
tests/phase0/integration/  real-machine tests, marked `integration`, opt-in
```

## Architecture

```
capture_before()  -->  execute_action()  -->  capture_after()
      -->  verify_postcondition()  -->  classify_interference()  -->  persist_result()
```

- `phase0/harness/runner.py` (`ExperimentRunner`, `ActionSpec`) implements
  this pipeline. The action (`ActionSpec.execute`) and its verifier
  (`ActionSpec.verify`) are kept strictly separate: a successful
  `execute()` call never by itself counts as success. `verify()` must
  inspect independently observable state (e.g. re-reading a DOM element
  or an AXValue), not trust whatever `execute()` returned.
- `phase0/harness/observers_macos.py` (`MacObserver`) captures physical
  cursor position, frontmost application, and focused window/element,
  using only public APIs (`Quartz.CGEventGetLocation`,
  `AppKit.NSWorkspace`, `ApplicationServices` AXUIElement calls). Every
  observer method returns a `Measurement` that is either a real value or
  `unavailable` with an explicit reason - nothing is ever fabricated.
- `phase0/harness/classification.py` turns measured cursor/foreground/
  focus deltas into an `InterferenceClassification`. This is the only
  place background-safety is decided, and it is derived purely from
  measurement, never from action success or model confidence
  (`docs/DECISIONS.md` D-011).
- `phase0/schemas/evidence.py` defines `ExperimentObservation`, the
  single typed/versioned record every experiment emits. It is generic
  across mechanisms (Playwright, macOS AX, and future Windows UIA) -
  not coupled to Chrome or macOS specifically.
- `phase0/harness/persistence.py` writes/reads JSON Lines results and
  computes aggregate summaries, always counting failed/error trials in
  the denominator.

## Background-safety classification

Per-trial, from `phase0/schemas/evidence.py::InterferenceClassification`:

| Classification | Meaning |
|---|---|
| `BACKGROUND_SAFE` | Cursor didn't move; foreground app didn't change; focused window/element didn't change. |
| `CURSOR_INTERFERENCE` | Only the physical cursor moved. |
| `FOREGROUND_INTERFERENCE` | Only the frontmost application changed. |
| `FOCUS_INTERFERENCE` | Only the focused window/element (within the same frontmost app) changed. |
| `MULTIPLE_INTERFERENCE` | More than one of the above happened. |
| `UNSUPPORTED` | The platform/permission/target does not support this operation at all (e.g. Accessibility permission not granted). Never attempted. |
| `INCONCLUSIVE` | One or more of the three signals could not be measured; no safety claim is made. |
| `ERROR` | The harness could not run the action/observers at all. |

This is a **per-trial measurement**, not the same thing as the
route-level capability labels (`BACKGROUND_PROVEN` /
`BACKGROUND_BEST_EFFORT` / `FOREGROUND_REQUIRED`) that
`docs/ARCHITECTURE.md` says the future `InteractionRouter` will use.
Those labels are a later aggregation/decision built from many
`InterferenceClassification` observations like these; this harness does
not compute or claim them.

**Interference and task success are orthogonal.** A trial with a failed
`postcondition_success` can still be `BACKGROUND_SAFE` (nothing on the
desktop was disturbed, the semantic action just didn't achieve its
goal), and a trial with a fully successful action can still show
interference. Both fields are always reported.

## Setup

```bash
cd BrowserAgentV2
python3 -m venv .venv-phase0
source .venv-phase0/bin/activate
pip install -r phase0/requirements.txt
python3 -m playwright install chromium
```

### Required macOS permissions

- **None** for cursor position or frontmost-application observation
  (public APIs, no entitlement needed).
- **Accessibility** permission for the terminal/interpreter process is
  required for: focused-window/focused-element observation in general,
  and for every macOS AX experiment operation. Grant it under
  **System Settings -> Privacy & Security -> Accessibility**. If it is
  not granted, the AX experiment does not silently skip - every trial
  is recorded as `UNSUPPORTED` with an explicit reason, and browser
  experiment trials that would have measured focus report `INCONCLUSIVE`
  for the focus signal specifically (cursor/foreground are unaffected).
- **Screen Recording** permission is not required by anything in this
  harness (no screenshots are captured yet).

## Running experiments

```bash
# Browser non-interference experiment (headed Chromium; headless would
# have no OS window to steal focus from and would prove nothing)
python3 -m phase0 browser --trials 50 --out phase0/results

# macOS Accessibility non-interference experiment
python3 -m phase0 ax --trials 50 --out phase0/results

# Positive control: DELIBERATELY moves your physical cursor a short,
# reversible distance, to prove the harness can detect interference.
# Requires --confirm; never runs as part of ordinary experiments/tests.
python3 -m phase0 control --confirm

# Re-aggregate an existing JSONL results file
python3 -m phase0 summarize --input phase0/results/<file>.jsonl
```

Each run writes:
- `phase0/results/<experiment_id>-<run_id>.jsonl` - one `ExperimentObservation` per line.
- `phase0/results/<experiment_id>-<run_id>-summary.json` - the aggregate summary (trials, successful actions, verified postconditions, per-classification counts/rates, latency median/p95). Failed/error trials are always included in these counts.

## Tests

```bash
# Unit tests only (default; no real desktop control, no cursor movement, no focus changes)
python3 -m pytest tests/phase0

# Real-machine integration tests (launches a real headed browser and a
# real tiny AX fixture app; reads real cursor/foreground/focus state)
python3 -m pytest -m integration tests/phase0/integration
```

Unit tests use `FakeObserver` (`tests/phase0/conftest.py`), a
canned-snapshot replay object; they never call into `Quartz`, `AppKit`,
or `ApplicationServices`, and never launch a browser or fixture
process. `pyproject.toml` deselects `integration`-marked tests by
default (`addopts = -m "not integration"`), so plain `pytest` never
touches the real desktop.

## Fixtures

- `phase0/fixtures/browser_page1.html` / `browser_page2.html` -
  deterministic local pages (loaded via `file://`, no network) exercising
  click, fill, select, and navigation, each with an independently
  readable DOM postcondition (a counter, a mirrored text/select value, a
  page title/marker).
- `phase0/fixtures/mac_ax_fixture_app.py` - a tiny standalone Cocoa app
  (not a production component) with one editable `AXTextField` and one
  `AXButton` wired to an `AXStaticText` counter. It uses
  `NSApplicationActivationPolicyAccessory` (no Dock icon), holds no user
  data, and can be killed at any time with no save prompt. Run it
  directly for manual inspection: `python3 phase0/fixtures/mac_ax_fixture_app.py`.

## Larger evidence campaign

The single-condition `browser`/`ax` CLI commands above were a preliminary
60/30-trial spike. `phase0/experiments/browser_background/campaign.py`
and `phase0/experiments/macos_ax/campaign.py` run a much larger,
multi-condition campaign (500+ trials each: click/fill/select/navigate,
backgrounded/occluded/multi-tab/multi-window/popup for the browser;
read/set-value/invoke/focus-switch/occluded/stale-element for AX). See
`phase0/CAMPAIGN_REPORT.md` for the results, gate verdict against
`docs/BUILD_SPEC.md`, and current limitations (most notably: Chrome did
not expose `AXFocusedUIElement` via a single-shot public AX read in the
tested environment, which kept the majority of trials `INCONCLUSIVE`
rather than `BACKGROUND_SAFE` for the focus signal specifically - not
converted into a pass anywhere in the pipeline. `phase0/CAMPAIGN_REPORT.md`
section M has since identified the root cause and a working, non-invasive
fix, `observers_macos.warm_up_ax_focus_tree` - not yet wired into a
campaign rerun).

## Interpreting results / known limitations

- **This is a spike on one machine, not a capability proof.** Both
  experiments were run tens of times on a single Apple Silicon Mac
  during this milestone; `docs/BUILD_SPEC.md`'s Phase 0 completion
  criteria require measurement across target macOS *and* Windows
  configurations, at higher trial counts, before any `BACKGROUND_PROVEN`
  claim is justified. See `phase0/CAMPAIGN_REPORT.md` for the larger
  (500+ trial) follow-up campaign's results.
- **Focus identity vs. content.** `focus_changed()` /
  `_element_identity_changed()` compare a focused element's role,
  subrole, `AXIdentifier`, title, description, help text, and geometry
  (position/size) - deliberately *excluding* its `AXValue`. Early runs
  showed false-positive `FOCUS_INTERFERENCE` because a terminal's
  `AXValue` is its entire scrollback buffer, which grows from unrelated
  shell output between a trial's before/after snapshot - that is content
  drift, not a focus change. `AXValue` capture is also capped at 200
  characters (`observers_macos._bounded_value_fields`) with a
  `value_truncated` flag, both to avoid this false signal and to avoid
  persisting unbounded/potentially sensitive application content into
  evidence files.
  Identity previously compared `(role, title)` only, which created the
  opposite problem: a **false negative**. Two distinct, untitled
  `AXTextField`s (a common real shape - `role=AXTextField`, `title=None`
  on both) compared equal, so a genuine focus move between them was
  missed. Role/title alone are no longer treated as sufficient evidence
  of sameness; at least one corroborating signal (identifier, title,
  description, help, or geometry within ~1px tolerance) must also match,
  otherwise the comparison returns *unknown* rather than "same" -
  `classify_interference` maps unknown to `INCONCLUSIVE`, never
  `BACKGROUND_SAFE`. `phase0/fixtures/mac_ax_fixture_app.py` now exposes
  two such untitled fields (`second_text_field`, distinguishable only by
  position) and
  `tests/phase0/integration/test_focus_switch_positive_control.py` moves
  real AX focus between them via the public `AXFocused` attribute to
  prove `FOCUS_INTERFERENCE` is actually detected, not just unit-tested
  against canned data. See `tests/phase0/test_observers_macos.py` for
  the full identity truth table (same-element value drift, distinct
  elements with matching role/title, role-only/insufficient information,
  role or subrole mismatches, stable same-element observations).
  `focus_changed()`'s window/element combinator was also tightened: it
  previously coerced an unmeasurable element signal (`None`) to "no
  change" whenever the window signal alone was already known `False`
  (`bool(None) == False`), which could silently manufacture a clean
  focus result from a half-unknown comparison. It now returns unknown
  whenever *either* signal is unknown, unless the other signal is a
  definite `True`.
- **Geometry as an identity signal has its own edge case.** A live
  window resize/reflow between a trial's before/after snapshot could in
  principle move the *same* element by more than the 1px tolerance,
  registering as a different element. Not observed in this milestone's
  fixed-size fixture/browser-page runs (a trial's before/after capture
  is near-instantaneous), but a source of measurement noise to watch for
  once real, resizable third-party applications are exercised (tracked
  by the "small, deterministic fixtures only" limitation below).
- **Window title volatility.** A window's title *is* still used for
  identity (there is no better cheap signal without deeper AX/window
  APIs). In terminals or tools that rewrite their own window title
  dynamically (status spinners, running-command indicators), that alone
  could in principle register as `FOCUS_INTERFERENCE` even with no real
  focus change. This was not observed in this milestone's runs but is a
  known source of measurement noise to watch for in longer runs.
- **`target_process` for the browser experiment is `unavailable`.**
  Playwright's Python sync API does not expose the underlying Chromium
  OS process id; this is recorded honestly rather than guessed.
- **The AX experiment's fixture-launch step is unmeasured by design.**
  Creating a new window can legitimately grab focus; that is a
  known, separate effect of window *creation*, not of the AX read/
  write/invoke actions under test. The harness explicitly re-activates
  the prior foreground application (polling until confirmed, no blind
  sleep) before any measured trial runs, so what's measured is
  interference from the AX calls themselves against an already
  backgrounded target.
- **Small, deterministic fixtures only.** Neither experiment yet covers
  popups, downloads, occluded/multi-window targets, stale AX elements
  under mutation, or third-party/real-world applications - all called
  out in `docs/BUILD_SPEC.md` section 2/3 as required before Phase 0's
  browser/AX workstreams are considered complete.
- **Windows UIA is not implemented.** `docs/BUILD_SPEC.md` section 4 is
  a separate, not-yet-started workstream.
