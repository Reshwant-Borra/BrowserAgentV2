# Windows UIA Parity Research

## Decision
**Use Windows UI Automation as the Windows semantic desktop route, but capability-gate actions and retain injected-input/visual fallbacks. Confidence: 91%.**

UIA is sufficiently broad to justify the same semantic-first architecture used on macOS, but it is not evidence for a universal background-control guarantee.

## Evidence

### Microsoft platform evidence
Microsoft's current Windows app automation tooling (`winapp ui`) is built on UIA and explicitly targets WPF, WinForms, Win32, Electron, and WinUI 3 applications. Most commands use UIA control patterns rather than input injection; click/hover/drag and send-keys are documented fallbacks for cases where UIA patterns cannot perform the operation. This is almost exactly the route hierarchy BrowserAgentV2 needs: semantic pattern first, physical/synthetic input only when required.

Microsoft's accessibility tooling exposes UIA properties, control patterns, and navigation structure through Inspect and related tools. This gives BrowserAgentV2 a deterministic capability-probing path instead of assuming a control supports Invoke/Value/Selection patterns.

### pywinauto implementation evidence
pywinauto documents a UIA backend covering WinForms, WPF, Store apps, Qt5 and browsers, but also documents meaningful gaps: Chrome may require forced renderer accessibility and custom properties/controls are constrained. This supports UIA breadth while falsifying any assumption that one accessibility wrapper can expose every custom UI.

### Architecture implication
Windows should mirror the macOS principle, not the exact implementation:

`TargetSpec -> fresh UIA observation -> candidate + supported patterns -> ephemeral execution ref -> freshness check -> UIA pattern action -> independent verification`

If the needed pattern is unavailable or verification fails, re-resolve through the next route. Do not convert a UIA handle into a visual coordinate and pretend identity survived the route change.

## Background execution
UIA pattern actions can often avoid moving the physical cursor, but background operation must be measured per application/control/action. Some operations inherently require injected mouse/keyboard input and therefore have foreground/focus implications. BrowserAgentV2 must maintain an action capability matrix with at least:
- semantic readability
- supported UIA patterns
- verified mutation/action
- works while occluded
- works while unfocused
- changes foreground app
- moves physical cursor
- requires injected input

No global `supports_background=true` should exist at the adapter level.

## Electron/custom surfaces
Electron does not invalidate UIA as the default semantic route: Microsoft's current tooling explicitly includes Electron. However, custom-rendered canvases/editors and accessibility-disabled browser content remain expected semantic gaps. BrowserAgentV2 should probe the live tree and patterns rather than infer support from framework name.

## Rejected alternatives
1. **Win32 message automation as universal route** — insufficient for modern WPF/WinUI/Electron/web surfaces.
2. **UIA-only Windows agent** — contradicted by documented custom-control/browser limitations and Microsoft's own injected-input fallbacks.
3. **Pixel-first Windows control** — sacrifices deterministic semantics and background-capable pattern actions where UIA works.
4. **Framework-specific adapters per application** — too much integration cost; reserve app-specific skills for high-value workflows, not basic control.

## Risks
- Accessibility tree can be incomplete, stale, or disabled.
- UIA action success still does not prove application-level effect.
- Synthetic input fallback can steal focus or interfere with the user.
- Electron/custom canvas behavior varies by application/version.

## Cheapest validation
On the target RTX 4070 Windows machine, port the Phase 0 capability probe and test a controlled fixture plus Notepad, Settings, Chrome, VS Code/Electron, and one custom-rendered app. For each action run repeated trials under foreground/background/occluded conditions and independently verify postconditions. This experiment should happen before claiming Windows parity in production.

## Architecture effect
This research strengthens rather than changes the current architecture: Windows can use the same route-neutral `TargetSpec` and verifier contracts while its adapter exposes UIA-specific candidates/patterns. Platform parity belongs above the adapter; platform quirks stay below it.