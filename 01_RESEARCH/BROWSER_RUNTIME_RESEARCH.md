# Browser Runtime Research

**Status:** active research

## Current conclusion

The browser layer should be a replaceable `BrowserKernel` abstraction. For the two-day MVP, the first implementation to test is **Playwright MCP**, not a custom low-level browser driver. If the spike exposes a fundamental blocker, the adapter can be replaced with direct Playwright without changing the controller, state model, or model interface.

## Why Playwright is still the right execution substrate

Playwright already implements behavior an agent should not reinvent: actionability checks, locator semantics, navigation waiting, popup/page events, browser contexts, keyboard/form controls, dialogs, and persistent authentication state. This directly addresses earlier BrowserAgent failures caused by arbitrary sleeps, focus ambiguity, and ad-hoc retry logic.

Key rule: browser infrastructure owns *how* an operation executes. The LLM only chooses from allowed operations.

Sources:
- https://playwright.dev/docs/actionability
- https://playwright.dev/docs/locators
- https://playwright.dev/docs/auth

## Playwright MCP as the first kernel candidate

Playwright MCP currently exposes browser state as accessibility snapshots. Interactive elements receive refs and tools act against those refs. This is close to the contract BrowserAgentV2 needs: compact semantic observation plus exact target resolution.

Important capabilities to validate in our spike:

- accessibility snapshots and refs;
- click/type/fill/select primitives;
- fresh snapshots after actions;
- tabs/popups;
- dialogs;
- persistent profiles;
- deterministic form operations;
- server restart and profile reattachment behavior;
- stale-ref behavior after DOM/page changes.

Playwright MCP persists browser state in a dedicated profile by default, including cookies and login state. A profile is locked to one browser instance at a time, so BrowserAgent must own process lifecycle cleanly.

Sources:
- https://playwright.dev/mcp/snapshots
- https://playwright.dev/mcp/configuration/user-profile

## Why not raw CDP for everything

CDP is valuable for observability, targets, accessibility data, and attaching to Chrome. It should not be the default implementation for ordinary click/fill/navigation because that would force us to recreate Playwright's waiting, locators, actionability, and edge-case behavior.

Direct CDP may later be used behind the kernel for richer observation or diagnostics.

## Form filling and the previous typing failures

The runtime should prefer deterministic fill semantics for ordinary text fields. Character-by-character typing is a specialized fallback, not the default.

Required postcondition for a fill action:

1. resolve explicit target from the current observation;
2. execute fill;
3. read the resulting value;
4. verify exact or policy-approved normalized match;
5. if value is reverted by hydration, classify `HYDRATION_RESET` rather than repeatedly typing;
6. obtain a fresh observation before retrying.

The model must never send text to whichever element happens to have focus.

## Modern web-app edge cases

The browser kernel must have explicit behavior for:

- SPA route changes without full navigation;
- delayed hydration;
- iframes and nested frames;
- popups/new tabs;
- dialogs;
- downloads/uploads;
- virtualized lists;
- infinite scroll;
- duplicate accessible names;
- disabled/covered controls;
- navigation that opens in the same tab vs a new tab;
- browser/profile crash and restart.

These must be tested as runtime mechanics before they are blamed on planning.

## Lessons from Browser Use

Browser Use's DOM service combines accessibility data, DOM information, frame structure, visibility/layout information, and CDP. That supports a hybrid long-term direction: accessibility snapshots as the default model-facing representation, with DOM/CDP enrichment only where needed.

Source:
- https://github.com/browser-use/browser-use/blob/main/browser_use/dom/service.py

## Lessons from Stagehand

Stagehand explicitly mixes AI-assisted `observe`/`act`/`extract` with deterministic Playwright-style locators. The relevant principle is **progressive determinism**: use AI to discover an unknown interaction; once a target/action is known, prefer deterministic execution.

Sources:
- https://github.com/browserbase/stagehand
- https://github.com/browserbase/stagehand/blob/main/packages/sdk-python/README.md

## BrowserKernel contract

The rest of BrowserAgent should depend on an interface like:

```text
start()
stop()
observe()
navigate(url)
click(target)
fill(target, text)
press(target, key)
select(target, value)
scroll(...)
go_back()
list_tabs()
switch_tab(page_id)
close_tab(page_id)
extract(...)
```

The adapter may be Playwright MCP initially and direct Playwright later. No model prompt should contain MCP-specific assumptions.

## Adoption gate

Do not commit the architecture to Playwright MCP until a deterministic spike repeatedly proves:

- navigation;
- exact fill/value verification;
- search submission;
- stale target rejection;
- tab/popup ownership;
- persistent session state;
- human takeover and fresh resume;
- runtime restart recovery.

If a failure is fundamental rather than an adapter bug, switch the kernel to direct Playwright. The upper layers should remain unchanged.
