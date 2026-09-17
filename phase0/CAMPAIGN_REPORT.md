# Phase 0 Browser/AX Background-Safety Campaign (macOS)

**Date:** 2026-09-17 (harness verification + fix) · campaign run same session
**Git commit:** `36b3851` (pre-campaign; this report and the campaign code are added on top)
**Status:** evidence for `docs/BUILD_SPEC.md` §2/§3. Supersedes the 60-trial browser / 30-trial AX preliminary runs referenced in `phase0/README.md`.

## A. Machine / OS context

- macOS 26.6.2 (build 25G83), arm64
- CPU: Apple M5 (Apple Silicon, unified memory)
- RAM: 24 GiB
- Accessibility permission: granted to the interpreter running the harness (`AXIsProcessTrusted() == True`)
- Real, shared interactive desktop session (not an isolated CI runner) — the user's own foreground application varies during a run; this is directly relevant to the results (see F).

## B. Campaign design

Both campaigns reuse the existing, unmodified measurement pipeline (`ExperimentRunner` / `ActionSpec` / `MacObserver` / `classify_interference`) added in prior Phase 0 work. New code only adds **what** is exercised and **how results are labeled**, via an `action_type` prefix `"<condition>__<action>"` (no schema changes):

- `phase0/experiments/browser_background/campaign.py` — 5 conditions, reusing `experiment._build_trials` (click / fill / select / navigate-forward / navigate-back) as the base action mix, plus a new popup trial.
- `phase0/experiments/macos_ax/campaign.py` — 4 conditions, reusing `experiment._build_trials` (AX read / set-value / invoke-action) as the base mix, plus new focus-switch and stale-element trials.
- New fixtures: `phase0/fixtures/overlay_window_app.py` (a borderless, full-screen, `NSScreenSaverWindowLevel` window shown via `orderFrontRegardless()` — visually occludes without ever becoming key window or frontmost app), a "Rebuild Field 2" button added to `mac_ax_fixture_app.py` (destroys/replaces the second AXTextField to produce a genuine stale AXUIElement reference), and a `window.open()` popup trigger added to `browser_page1.html`.
- The real foreground-holder application is reactivated once at the start of each campaign and never touched again — this **is** the "unrelated foreground app stays active" condition (BUILD_SPEC's non-interference stress ask); no synthetic user input is injected during measurement, to avoid confounding the signal under test.

**Harness defect found and fixed during verification (step 1):** `classify_interference` returned `INCONCLUSIVE` for a trial with a *proven* `cursor_moved=True` whenever an unrelated signal (`focus_changed`) was simultaneously unmeasurable — discovered because the cursor positive control itself returned `INCONCLUSIVE` instead of `CURSOR_INTERFERENCE`. Fixed in `phase0/harness/classification.py`: a definite `True` on any signal now always wins, regardless of what else is unmeasurable in the same trial; `INCONCLUSIVE` is now reserved for trials with *no* proven interference and *at least one* unmeasurable signal. 5 new unit tests added (`tests/phase0/test_classification.py`). This is a strictly more conservative-on-danger, equally-conservative-on-safety change — it can never turn an unsafe trial into `BACKGROUND_SAFE`.

**Campaign-code defects found and fixed during evidence validation (step 8):** two cross-condition state-leakage bugs, both in the *new* campaign code, not the core harness: (1) `focus_switch` trials compared the focused element's content against hardcoded fixture-initial-value constants, which broke once `baseline`'s set-value trials had already mutated that content — fixed by reading each field's actual current value once, right before building the batch; (2) `occluded`'s AX trials reused the same live fixture process as `baseline`, so the *reused* trial builder's locally-reset expected press-counter no longer matched the fixture's real (cumulative) counter — fixed by giving the `occluded` AX condition its own freshly-launched fixture process. Both were caught because 100%-verified-postcondition was treated as a hard invariant to check, not assumed.

## C. Browser results (canonical: `browser_campaign-campaign01.jsonl`, 500 trials)

| Condition | n | Classifications |
|---|---:|---|
| `baseline_backgrounded` (click/fill/select/navigate×2, browser window backgrounded) | 400 | INCONCLUSIVE: 400 |
| `occluded` (same mix, screen covered by overlay) | 40 | INCONCLUSIVE: 40 |
| `multi_tab` (second tab open throughout) | 30 | INCONCLUSIVE: 30 |
| `multi_window` (second Chromium window/context open throughout) | 20 | INCONCLUSIVE: 20 |
| `popup` (`window.open()` trigger, verify, close) | 10 | INCONCLUSIVE: 10 |
| **Total** | **500** | **INCONCLUSIVE: 500 (100%)** |

- `cursor_moved`: `False` for all 500 (0 `CURSOR_INTERFERENCE`).
- `foreground_changed`: `False` for all 500 (0 `FOREGROUND_INTERFERENCE`), foreground app constant (`Google Chrome`, the real user session's own browser — not the Playwright-launched instance) across all 500 trials.
- `focus_changed`: `None` for all 500 — see F.
- Verified postconditions: **500/500 (100%)**. 0 `ERROR`, 0 `UNSUPPORTED`.

## D. AX results by operation/element class (canonical: `ax_campaign-campaign02.jsonl`, 510 trials)

| Condition | n | Mechanism | Classifications |
|---|---:|---|---|
| `baseline` (read / set-value / invoke-action, 1 fixture, backgrounded) | 400 | READ + MUTATE | INCONCLUSIVE: 400 |
| `focus_switch` (AX `AXFocused` between 2 identical-role/untitled fields) | 60 | MUTATE | FOCUS_INTERFERENCE: 59, BACKGROUND_SAFE: 1 |
| `occluded` (baseline mix, fresh fixture, screen covered) | 40 | READ + MUTATE | INCONCLUSIVE: 40 |
| `stale_element` (10× read of an AXUIElement invalidated by "Rebuild Field 2") | 10 | READ | BACKGROUND_SAFE: 10 |
| **Total** | **510** | | INCONCLUSIVE: 440, FOCUS_INTERFERENCE: 59, BACKGROUND_SAFE: 11 |

- `cursor_moved`: `False` for all 510 (0 `CURSOR_INTERFERENCE`).
- `foreground_changed`: `False` for all 510 (0 `FOREGROUND_INTERFERENCE`), foreground app constant (`Google Chrome`) throughout this run.
- `focus_switch`'s 59/60 `FOCUS_INTERFERENCE` is **expected and correct, not a safety violation**: this condition's whole purpose is a semantic "move AX focus" action — it is measuring that the harness correctly detects a real, intentional focus change (the same shape the focus-identity hardening targeted: identical role, no title), not testing a read/write action that is supposed to leave focus alone. It also directly re-validates the same-role/title focus-switch positive control under repetition (59 independent detections, not just one).
- `stale_element`: all 10 attempts to read the destroyed field's old reference returned AX error `-25202` (`kAXErrorInvalidUIElement`) and no value — the AX layer never silently returned stale/fabricated content.
- Verified postconditions: **510/510 (100%)**.
- **Not covered:** "multiple target windows" — the fixture app is single-window; adding a second window was judged out of scope for this campaign. Documented here as a limitation, not silently skipped.

## E. Non-interference stress results

Requirement: an unrelated foreground app stays active while the background target is manipulated, measuring cursor/foreground/focused-window/focused-element.

- Both campaigns reactivate the real foreground holder once, up front, and never touch it again for the remainder of the run (400+ trials each).
- Foreground application identity was **constant across every trial** in both campaigns (`Google Chrome` throughout the browser campaign; `Google Chrome` throughout the AX campaign's canonical run) — `foreground_changed` measured `False` on all 1,010 trials, 0 exceptions.
- Physical cursor position never moved (`cursor_moved=False` on all 1,010 trials).
- Focused-window/focused-element of that real foreground holder could not be read (see F) for the majority of trials, so "focus not stolen" is unproven for those specific trials, not proven false — no trial anywhere in either campaign registered an actual detected focus theft of the unrelated foreground app.
- No synthetic user input was injected during measurement, per instruction, to keep this signal uncontaminated.

## F. Inconclusive / error analysis

- **0 `ERROR`, 0 `UNSUPPORTED` in 1,010 trials.** Every trial ran to completion and was independently verified.
- **All `INCONCLUSIVE` trials (440 browser-condition-equivalent... 500 browser + 440 AX = 940/1,010, 93%) share one root cause:** `AXUIElementCopyAttributeValue(ax_app, "AXFocusedUIElement", ...)` returns AX error **-25212** (`kAXErrorAttributeUnsupported`) for the real foreground holder application, **Google Chrome**, in this session.
- **Investigated directly (public APIs only, no foreground-forcing, no fabricated identity):**
  1. Confirmed the failure is independent of Chrome's frontmost/foreground status (queried Chrome's AX tree directly by pid while a different app was frontmost — same -25212).
  2. Attempted `AXUIElementSetAttributeValue(ax_app, "AXManualAccessibility", True)` (a documented Chromium attribute meant to force its full accessibility tree on) — the set itself failed (`-25205`, not settable in this Chrome build/config).
  3. Attempted the standard AT-client handshake (`AXObserverCreate` + registering for `AXFocusedUIElementChanged`) — hit a PyObjC callback-signature issue before completion; not pursued further given this campaign's scope.
  - **Conclusion: no safe, public-API way to reliably obtain Chrome's focused-element signal was found in this investigation.** This is treated as a genuine, disclosed measurement limitation, not converted into a pass anywhere in the pipeline — **every** affected trial is recorded and reported as `INCONCLUSIVE`, never `BACKGROUND_SAFE`.
- **This is directly evidenced as environment-dependent, not action-dependent:** an earlier same-day AX run with the identical design (superseded only because of the postcondition-verification bug described in B, since fixed) recorded the same `baseline`/`occluded` action classes as 100% `BACKGROUND_SAFE` while the real frontmost holder happened to be **Terminal** instead of Chrome (Terminal's `AXFocusedUIElement` resolves normally). The semantic AX/browser actions under test did not change between these two runs — only which real application the user had frontmost did.
- No `INCONCLUSIVE` or failed trial was discarded, averaged away, or excluded from any summary; per-condition and per-class breakdowns in C/D account for all 1,010 trials exactly.

## G. Latency

| Campaign | n | median (ms) | p95 (ms) | min | max |
|---|---:|---:|---:|---:|---:|
| Browser | 500 | 37.9 | 44.4 | 1.1 | 76.1 |
| AX | 510 | 2.3 | 105.4 | 0.04 | 108.4 |

(AX p95 is pulled up by the `occluded` condition's fresh-fixture-launch trials; no latency-based gate is defined in BUILD_SPEC for this workstream.)

## H. Gate verdict (per `docs/BUILD_SPEC.md` §2/§3, strictly)

BUILD_SPEC defines this gate qualitatively, not as a single numeric threshold. It states two concrete, checkable requirements and one directive:

1. §2 P0 target: "**zero** unexpected physical pointer movement" and "**does not steal** unrelated application focus."
   - Physical pointer: **PASS** — 0/1,010 `CURSOR_INTERFERENCE`.
   - Foreground-app theft: **PASS** — 0/1,010 `FOREGROUND_INTERFERENCE`, foreground identity constant on every trial.
   - Focus-theft-of-the-unrelated-app: **NOT ESTABLISHED** — the required signal was unavailable (`None`) on 940/1,010 trials (93%) due to the Chrome AX limitation in F. 0 trials detected actual focus theft, but "not detected" ≠ "proven absent" when the sensor was off.
2. §3: "Do not mark an AX action `BACKGROUND_PROVEN` without measurement." Per D-011 and this task's explicit instruction, a route cannot become `BACKGROUND_PROVEN` from trials whose required safety signal was unavailable.

**Overall verdict: `INCONCLUSIVE`.**
Neither route can be marked `BACKGROUND_PROVEN` (focus signal insufficiently measured for the majority of trials), and neither is `FAIL` (zero interference was ever actually observed in 1,010 trials — no cursor, foreground, or unintended-focus violation). It is not `BLOCKED` (both campaigns ran to completion with 0 errors) and not a data-integrity `NEEDS_DECISION` case, but there is a genuine **policy `NEEDS_DECISION`**: BUILD_SPEC does not say whether a route may be provisionally treated as background-safe on cursor+foreground evidence alone when a specific target application (like Chrome) structurally cannot expose a focus signal via public AX APIs. That policy call is left to a human decision, not invented here.

## I. Files changed

- `phase0/harness/classification.py` — fixed the proven-interference-vs-unmeasurable-signal precedence bug (see B).
- `tests/phase0/test_classification.py` — 5 new regression tests for that fix.
- `phase0/fixtures/mac_ax_fixture_app.py` — added "Rebuild Field 2" button/handler (stale-element fixture).
- `phase0/experiments/macos_ax/ax_elements.py` — added `get_rebuild_button()` (shared `_get_button_titled()` helper).
- `phase0/fixtures/browser_page1.html` — added a `window.open()` popup trigger button.
- `phase0/fixtures/overlay_window_app.py` (new) — occlusion fixture.
- `phase0/experiments/overlay_process.py` (new) — overlay launcher, shared by both campaigns.
- `phase0/experiments/browser_background/campaign.py` (new) — browser campaign.
- `phase0/experiments/macos_ax/campaign.py` (new) — AX campaign.
- `phase0/CAMPAIGN_REPORT.md` (this file, new).

## J. Evidence / report locations

- Raw per-trial evidence (gitignored, kept locally): `phase0/results/browser_campaign-campaign01.jsonl` (500 records), `phase0/results/ax_campaign-campaign02.jsonl` (510 records), plus their `*-summary.json` aggregates and the two positive-control runs (`phase0/results/positive_control-campaign-verify.jsonl`).
- This file (`phase0/CAMPAIGN_REPORT.md`) is the compact, committable report.

## K. Remaining limitations

- Chrome's `AXFocusedUIElement` is unavailable via public AX APIs in this session for reasons not fully resolved (F) — the single largest open gap in this evidence.
- AX "multiple target windows" not covered (D).
- Both campaigns ran on one Apple Silicon Mac, one session; BUILD_SPEC's completion criterion requires measurement "on target macOS **and Windows** configurations" — Windows UIA is untouched (out of scope per instructions).
- `occluded` overlay covers the whole screen rather than precisely the target window's bounds (simpler, still a genuine visual occlusion, but not pixel-exact).
- `multi_window`/`multi_tab` conditions only exercise the *original* page/window while a second one is open; they do not yet test switching the acting target between windows/tabs mid-run.
- This is still a single-machine spike at the campaign level (no repeated-day/repeated-machine variance data beyond the two AX runs noted in F).

## L. Tests executed

- `pytest tests/phase0 -m "not integration"`: **64 passed** (59 pre-existing + 5 new classification regression tests).
- `pytest -m integration tests/phase0/integration`: **6 passed** (includes the same-role/title focus-switch positive control, re-run explicitly and individually: 1 passed).
- `python -m phase0 control --confirm`: **`CURSOR_INTERFERENCE`** (correctly detected; was `INCONCLUSIVE` before the classification fix — see B).
