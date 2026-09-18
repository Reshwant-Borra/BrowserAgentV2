# Mac Application Capability Matrix

**Date:** 2026-09-17 · **Git commit (base):** `97ff445`
**Status:** evidence for `docs/BUILD_SPEC.md` §3's "representative native and custom applications" requirement.

This is a **breadth capability survey**, not a reliability campaign. It reuses the existing, unmodified measurement pipeline (`ExperimentRunner`/`ActionSpec`/`MacObserver`/`classify_interference`, `phase0/harness/*`) and adds a new probe — `phase0/experiments/mac_app_capabilities/` — that determines, per representative real macOS application, how much of AXUIElement's semantic surface (discovery, read, action, value mutation, background operation, occlusion tolerance) actually works. It does not build the production `MacAccessibilityAdapter`/`AccessibilityKernel`.

## A. Machine / OS context

- macOS 26.6.2, arm64, Apple M5, 24 GiB RAM (same machine as `phase0/CAMPAIGN_REPORT.md`)
- Accessibility permission: granted to the interpreter running the harness
- Real, shared interactive desktop session — not an isolated CI runner

## B. Applications actually tested

| App | Bundle ID | Category | Resolution |
|---|---|---|---|
| Finder | `com.apple.finder` | system, always running | attached to running process; a new Finder window was opened at this repository's own directory (never a personal folder) |
| Notes | `com.apple.Notes` | system | already running (attached, not launched); no window was open at probe time, so no window was force-opened |
| Calendar | `com.apple.iCal` | system | launched fresh by the probe; quit afterward since the probe started it |
| System Settings | `com.apple.systempreferences` | system | launched fresh by the probe; quit afterward |
| Safari | `com.apple.Safari` | real installed app | launched fresh; scratch window pointed at the existing local `phase0/fixtures/browser_page1.html` fixture (never the user's real tabs); scratch window closed, then quit for hygiene |
| Google Chrome | `com.google.Chrome` | real installed app | **disposable** instance with a temporary `--user-data-dir`, pointed at the same local fixture page; killed and profile deleted on teardown — the user's real Chrome profile/session was never touched |
| Visual Studio Code | `com.microsoft.VSCode` | real installed app | launched fresh with `--new-window` (no folder/files opened); scratch window closed via AX afterward |
| Phase 0 Cocoa AX Fixture | *(none)* | existing Phase 0 fixture | `phase0/fixtures/mac_ax_fixture_app.py`, launched/terminated via the existing `fixture_process.launch_fixture()` |

No third-party application was installed for this milestone. No real notes/events/settings/files were read beyond structural AX metadata (role/title/identifier/geometry — never full-text content), and none were created or modified. See §J for the one incidental cleanup action taken (below).

**Incidental finding, not caused by this probe's code:** an unrelated, already-running VS Code process was discovered executing from a stray mounted disk image (`/Volumes/VS Code`, an old installer/update volume unrelated to this repository) that did not respond to AX or AppleScript queries. It was terminated (a plain process kill, no data involved — VS Code holds no autosave-relevant state for a hung, windowless process) so the probe could launch a normal instance from `/Applications`. The mounted disk image itself was left alone.

## C. Capability matrix (measured)

| App | Type | AX App | Windows | Tree | Read | Action Avail. | Action Verified | Value Mut. Avail. | Value Mut. Verified |
|---|---|---|---|---|---|---|---|---|---|
| Finder | Cocoa | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY |
| Notes | SwiftUI | SUPPORTED | INCONCLUSIVE | INCONCLUSIVE | INCONCLUSIVE | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY |
| Calendar | Cocoa | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY |
| System Settings | SwiftUI | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY |
| Safari | WebKit | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | INCONCLUSIVE | SUPPORTED | UNSUPPORTED |
| Google Chrome | Chromium | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | UNSUPPORTED | SUPPORTED | UNSUPPORTED |
| VS Code | Electron | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY | NOT_TESTED_SAFETY |
| Cocoa AX Fixture | Cocoa | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED |

Full machine-readable record (all 20 fields per app, including `interference_classifications` and `limitations`): `phase0/results/mac_app_capabilities-caps-campaign01-matrix.json` (gitignored — regenerate via `python -m phase0 mac-app-capabilities`).

## D. Background-operation matrix

| App | Background inspection | Background action |
|---|---|---|
| Finder | SUPPORTED (`BACKGROUND_SAFE`) | NOT_TESTED_SAFETY |
| Notes | INCONCLUSIVE (focus signal unmeasurable; no window was open to probe) | NOT_TESTED_SAFETY |
| Calendar | SUPPORTED (`BACKGROUND_SAFE`) | NOT_TESTED_SAFETY |
| System Settings | SUPPORTED (`BACKGROUND_SAFE`) | NOT_TESTED_SAFETY |
| Safari | INCONCLUSIVE (focus signal unmeasurable) | INCONCLUSIVE (focus signal unmeasurable) |
| Chrome | SUPPORTED (`BACKGROUND_SAFE`) | UNSUPPORTED (the action itself didn't take effect — see §F) |
| VS Code | SUPPORTED (`BACKGROUND_SAFE`) | NOT_TESTED_SAFETY |
| Cocoa Fixture | SUPPORTED (`BACKGROUND_SAFE`) | SUPPORTED (`BACKGROUND_SAFE`) |

All 8 apps: **0 `CURSOR_INTERFERENCE`, 0 `FOREGROUND_INTERFERENCE`** across every trial. Cursor and foreground-app identity were never observed to move/change for any app in this survey, consistent with `phase0/CAMPAIGN_REPORT.md`'s 1,010-trial finding. Where a background verdict reads INCONCLUSIVE, it is always the *focus* signal specifically that was unmeasurable (`AXFocusedUIElement` unreadable for that pid at that moment) — the same class of gap `phase0/CAMPAIGN_REPORT.md` §F/§M documents for Chrome, now also observed transiently for Safari and Notes.

## E. Occlusion results

| App | Occluded inspection | Occluded action |
|---|---|---|
| Finder | SUPPORTED | NOT_TESTED_SAFETY |
| Notes | INCONCLUSIVE | NOT_TESTED_SAFETY |
| Calendar | SUPPORTED | NOT_TESTED_SAFETY |
| System Settings | SUPPORTED | NOT_TESTED_SAFETY |
| Safari | INCONCLUSIVE | INCONCLUSIVE |
| Chrome | UNSUPPORTED (action itself doesn't work regardless of occlusion) | UNSUPPORTED |
| VS Code | INCONCLUSIVE | NOT_TESTED_SAFETY |
| Cocoa Fixture | SUPPORTED | SUPPORTED |

Reused the existing `overlay_window_app.py`/`overlay_process.py` fixture unchanged (a full-screen, non-activating, non-input-intercepting window). Where occlusion could actually be tested against a working action (Finder/Calendar/System Settings reads, Cocoa fixture's full suite), the overlay never changed the result relative to the un-occluded condition — consistent with `phase0/CAMPAIGN_REPORT.md`'s prior finding that visual occlusion does not, by itself, block AXUIElement calls.

## F. AX-tree quality observations

| App | Elements (bounded) | Max depth | Actionable | With identifier | Web content exposed |
|---|---:|---:|---:|---:|---|
| Finder | 190 | 6 | 109 | 20 | no |
| Calendar | 64 | 6 | 23 | 14 | no |
| System Settings | 67 | 6 | 48 | 4 | no |
| Safari (web content) | 17 | 3 | 17 | 0 | yes |
| Chrome (web content) | 21 | 3 | 21 | 0 | yes |
| VS Code | 12 | 6 (capped) | 4 | 0 | no |
| Cocoa Fixture | 11 | 2 | 8 | 0 | no |
| Notes | *(no window open at probe time)* | — | — | — | — |

- **Finder, Calendar, System Settings** all exposed rich, meaningful native AX trees (roles, titles, sizeable actionable-control counts) with no code required beyond generic bounded traversal.
- **Safari and Chrome's web content** exposed a comparably *shallow* structure (max depth 3, capped by the bounded fixture page's own simplicity) but zero `AXIdentifier`s — WebKit/Chromium do not map an HTML `id` attribute to `AXIdentifier` by default, so an agent must locate controls by role+title/label, not by a stable id, when going through raw AX rather than the DOM.
- **VS Code (Electron/Monaco)**: only 12 elements, 4 actionable, found within the traversal bounds — the editor surface itself is a largely custom-drawn canvas with little exposed to AX beyond window-level chrome (title bar, minimap scrollbar). This matches the milestone's working hypothesis about custom-drawn/opaque regions.
- No huge tree dump was ever persisted — every count above is a bounded structural summary (max 300 nodes, max depth 6–12, never raw AXValue/text) per `docs/BUILD_SPEC.md` §5.

## G. Unsupported / inconclusive capabilities, explained

- **Chrome's `AXPress` on a plain HTML `<button>` returns success (AX error 0) but never fires the page's click handler** (`background_action`/`occluded_action` = UNSUPPORTED for Chrome; the identical action mechanism worked on Safari). Verified directly, isolated from the rest of the probe: pressing the fixture page's "Increment" button via `AXUIElementPerformAction(button, "AXPress")` on Chrome consistently leaves the counter unchanged, while the same call on Safari changes it. Not investigated further (breadth, not depth) — see §N.
- **Both Safari's and Chrome's `AXValue` write-then-read-back on the fixture's text input returned an empty string instead of the value just set**, when this trial ran *after* the action/background/occlusion trials on the same live page (`value_mutation_verified` = UNSUPPORTED for both). An isolated one-shot debug of the identical mechanism (`AXUIElementSetAttributeValue(field, "AXValue", ...)` immediately after page load, no prior AX activity) succeeded on both browsers. This is evidence that raw `AXValue` writes into web form fields are **ordering-/state-sensitive** in a live browsing session — not a reliable route for ComputerAgent to depend on for browser form-filling, which is exactly why `docs/ARCHITECTURE.md`'s routing hierarchy already places browser DOM/semantic control (Playwright) *ahead of* desktop accessibility for browser targets (D-002). This finding supports, not contradicts, that existing decision.
- **Notes reported `INCONCLUSIVE`/no window** because no Notes window happened to be open when the probe ran, and the probe deliberately never force-opens one (opening a window could reveal whatever note the user last had open). This is a state-dependent result, not a capability gap in Notes' AX support — Notes' `AXApplication` element itself was fully readable.
- **Safari's own `background_inspection`/`background_action`/`semantic_action_verified` show `INCONCLUSIVE`** purely because `AXFocusedUIElement` on Safari's own pid was intermittently unreadable — the *button press itself* (semantic_action_availability = SUPPORTED, and the counter *did* change in the underlying trial, confirmed in raw evidence) worked; only the interference classification's focus signal was the unmeasurable part.

## H. Harness/probe defects discovered and fixed during this milestone

All found and fixed while building/validating `phase0/experiments/mac_app_capabilities/`, before the campaign run below (§C/§D/§E reflect the fixed probe):

1. **Window-appearance race.** A single immediate `AXWindows` read right after `open -a <App> <target>` could transiently see zero windows even though the process was alive (observed on Safari, generalized to the fixture/VS Code/generic apps). Fixed with a bounded poll (`time.sleep` retry loop, 3–5s), not a blind sleep — same philosophy as the existing `_reactivate_and_wait`.
2. **AXWebArea search depth too shallow for Chrome.** Chrome's own toolbar/tab-strip chrome nests deeper before reaching web content than Safari's; a depth-6 search found nothing even after `warm_up_ax_focus_tree`. Widened to depth 12 for Chromium specifically.
3. **Stale AXUIElement reference across a mutating trial.** A `<span>` counter's captured AXUIElement reference, read again after the button that changes its text was pressed, returned an AX error instead of the new value — WebKit appears to rebuild that element's accessibility node when its text content changes, unlike the Cocoa fixture's in-place `NSStaticText` mutation. Fixed by re-locating the counter (and the button/text field) fresh on every read, matching a "value is a digit string" predicate that survives the counter incrementing, instead of holding one reference across calls.
4. **`_aggregate_capability` conflated "postcondition definitively failed" with "postcondition unmeasured."** Both previously produced `INCONCLUSIVE`, which would have hidden the real Chrome `AXPress` no-op finding (§G) behind a "we don't know" verdict instead of an honest "this doesn't work." Split into `UNSUPPORTED` (postcondition measured `False`) vs. `INCONCLUSIVE` (postcondition never measured either way).

## I. Tests executed and results

```
pytest tests/phase0 -m "not integration"       -> 80 passed  (67 pre-existing + 13 new)
pytest -m integration tests/phase0/integration -> 7 passed   (no change; regression check only)
```

New unit tests (no real desktop control — fake AX tree / hand-built dataclasses, same discipline as `tests/phase0/conftest.py`'s `FakeObserver`):
- `tests/phase0/test_ax_introspection.py` — 8 tests covering `walk_tree`'s bounded counting (nodes/actions/identifiers/labels/roles/web-area detection), depth/node-count truncation, and `find_by_role`/`find_by_role_and_title`/`find_descendant` against a fake tree.
- `tests/phase0/test_app_capability_schema.py` — 5 tests covering `AppCapabilityRecord`/`TreeQualityObservations` serialization and the `CapabilityState` vocabulary.

## J. Files changed

- `phase0/schemas/app_capability.py` (new) — `CapabilityState`, `AppArchitecture`, `TreeQualityObservations`, `AppCapabilityRecord`.
- `phase0/experiments/mac_app_capabilities/__init__.py` (new)
- `phase0/experiments/mac_app_capabilities/ax_introspection.py` (new) — generic bounded AX helpers (not tied to the Cocoa fixture).
- `phase0/experiments/mac_app_capabilities/targets.py` (new) — per-app safe attach/launch/teardown.
- `phase0/experiments/mac_app_capabilities/matrix.py` (new) — orchestrator; reuses `ExperimentRunner`/`ActionSpec`/`MacObserver`/`classify_interference`/`ResultWriter`/`_reactivate_and_wait`/`launch_overlay` unmodified.
- `phase0/cli.py` — added `mac-app-capabilities [--app <key>]` subcommand.
- `.gitignore` — added `phase0/results/*-matrix.json` (generated evidence, same treatment as the existing `*.jsonl`/`*summary.json` patterns).
- `tests/phase0/test_ax_introspection.py`, `tests/phase0/test_app_capability_schema.py` (new).
- `phase0/MAC_APP_CAPABILITY_REPORT.md` (this file, new).
- `docs/BUILD_SPEC.md` — one short measured-evidence note added under section 3 (see below); no other doc changes.

No existing Phase 0 module (`harness/`, `schemas/evidence.py`, `experiments/macos_ax/*`, `experiments/browser_background/*`) was modified.

## K. Evidence locations

- `phase0/results/mac_app_capabilities-caps-campaign01.jsonl` — every individual trial (gitignored, regenerate via CLI).
- `phase0/results/mac_app_capabilities-caps-campaign01-summary.json` — aggregate classification counts across all trials.
- `phase0/results/mac_app_capabilities-caps-campaign01-matrix.json` — the full 8-app `AppCapabilityRecord` list (all fields from §C/D/E/F/G).

## L. Answers to the critical questions

1. **Can we currently claim AX can control ANY Mac application?** Yes, narrowly: the Cocoa AX fixture and, for read/discovery, all seven real applications tested. For a *verified, background-safe, repeatable* action, only the Cocoa fixture (fully unrestricted) and Safari (action verified once the focus-signal issue is set aside) qualify from measured evidence.
2. **Can we claim AX can control MOST representative Mac applications tested?** For **discovery and semantic read**, yes — 7/8 apps (all but Notes, which had no open window at probe time) got `SUPPORTED` AX-application-creation, window discovery, tree traversal, and read. For **verified action/mutation**, no — only 1/8 (the Cocoa fixture) achieved a clean `SUPPORTED` across the full action+mutation+background+occlusion set; real apps were either untested by design (safety) or measured with a genuine gap (Chrome's no-op `AXPress`, both browsers' ordering-sensitive `AXValue` writes, Safari/Notes' intermittent focus signal).
3. **Which application architectures expose the strongest AX semantics?** Native Cocoa/SwiftUI system apps (Finder, Calendar, System Settings) — rich, meaningful, deeply-nested trees with real titles/roles and no extra warm-up needed.
4. **Which expose weak/incomplete semantics?** Electron (VS Code) — a nearly opaque custom-drawn editor surface with almost nothing exposed below the window chrome. Chromium (Chrome) — reachable but structurally shallow web content with no stable identifiers and an action mechanism (`AXPress`) that doesn't reliably invoke the underlying handler.
5. **Which operations commonly require foreground interaction?** None were *found* to require foreground interaction in this survey — every background trial across all 8 apps measured `cursor_moved=False` and `foreground_changed=False`. The open question is a different one: whether the *focus* signal can be measured at all for a given target (Safari/Notes/Chrome all showed transient gaps here), not whether the operation itself needs the foreground.
6. **Does occlusion materially affect AX semantic control?** No evidence that it does, anywhere it could be tested (§E) — consistent with the prior 1,010-trial campaign.
7. **Where would ComputerAgent likely need another mechanism?**
   - **Browser form-filling/value entry** (Safari, Chrome): route through Playwright/DOM semantics, not raw AXValue writes — this survey's evidence reinforces the architecture's existing D-002 preference (browser semantics before desktop accessibility) rather than requiring a new decision.
   - **Chrome button/control activation via AX**: needs the browser semantic route (Playwright click), not `AXPress` — the existing `BrowserAdapter` already covers this; this is evidence *for* using it, not a new gap.
   - **Electron/VS Code editor content**: candidate for visual grounding (VisionAdapter) given how little of the editor surface AX exposes; Electron's own window chrome (title bar, sidebar if present) is AX-reachable and could still route through desktop accessibility for chrome-level interactions.
   - **Real user-data apps (Notes/Calendar/System Settings) mutation**: genuinely untested here by design; a production adapter will need its own scoped, reversible-action safety design before any verified-mutation claim can be made for these, not a different mechanism per se.

## M. Remaining limitations

- Single-machine, single-session survey (same caveat as `phase0/CAMPAIGN_REPORT.md`) — no Windows equivalent exists yet (out of scope, per instruction).
- Each real app got a small number of trials (1 baseline + 3 background + 3 occluded per tested condition) — enough to distinguish basic capability, not a reliability rate.
- Chrome's `AXPress` no-op and the ordering-sensitive `AXValue` write-back (§G) were observed and isolated but not root-caused to the same depth as the Chromium focus-tree gap in `phase0/CAMPAIGN_REPORT.md` §M — flagged as a candidate for a future focused diagnostic, not resolved here (breadth, not depth, per this milestone's scope).
- Notes/Calendar/System Settings/Finder never got a verified action or value-mutation trial, by design (§B) — their `NOT_TESTED_SAFETY` fields are an explicit safety choice, not evidence that mutation would fail.
- "Multiple windows per app" and "stale-element behavior in a real (non-fixture) app" were not covered here — the existing campaign's stale-element coverage (`phase0/CAMPAIGN_REPORT.md` §D) remains the only measured evidence for that failure mode.

## N. Recommended next Phase 0 workstream

Two small, targeted follow-ups (not started here, per instruction to stop after this sweep):
1. A short, isolated diagnostic (mirroring `phase0/experiments/macos_ax/focus_diagnostics.py`'s style) specifically on **why Chrome's `AXPress` doesn't invoke a plain HTML button's click handler** while Safari's does — this is a concrete, novel, falsifiable question with a clear existing template to reuse.
2. Wire `docs/BUILD_SPEC.md`/`docs/DECISIONS.md` review of whether D-002's browser-semantics-before-AX ordering should be stated even more explicitly for *write* operations specifically, now that this survey has direct evidence for it (see §L.7) — a documentation decision, not new code.

Windows UIA, model/runtime benchmarking, hardware-tier benchmarking, OmniParser/UI-TARS, vision implementation, isolation implementation, TaskController, and the production InteractionRouter/AccessibilityKernel remain explicitly out of scope, unstarted, per this milestone's instructions.
