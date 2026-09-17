"""Deterministic, harmless "occluding window" fixture.

Purpose: give the browser/AX campaigns a controlled way to test the
"occluded target window" condition from docs/BUILD_SPEC.md sections 2/3
- a real, visible window stacked on top of the target - without changing
which application is frontmost or stealing keyboard focus.

It covers the whole main screen at a high window level
(`NSScreenSaverWindowLevel`), shown via `orderFrontRegardless()` (never
`makeKeyAndOrderFront_`), with `ignoresMouseEvents_(True)` so it never
intercepts input. `NSApplicationActivationPolicyAccessory` keeps it out
of the Dock/Cmd-Tab and it is never explicitly activated, so it does not
become the frontmost application - only a visual occluder.

Run standalone for manual inspection:
    python3 phase0/fixtures/overlay_window_app.py

Prints one JSON line once visible: {"ready": true, "pid": <pid>}.
"""

from __future__ import annotations

import json
import os
import sys

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSColor,
    NSScreen,
    NSScreenSaverWindowLevel,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskBorderless,
)


def build_and_run() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    screen_frame = NSScreen.mainScreen().frame()

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        screen_frame, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
    )
    window.setLevel_(NSScreenSaverWindowLevel)
    window.setOpaque_(True)
    window.setBackgroundColor_(NSColor.systemOrangeColor())
    window.setIgnoresMouseEvents_(True)

    label = NSTextField.alloc().initWithFrame_(screen_frame)
    label.setStringValue_("phase0 occlusion fixture")
    label.setEditable_(False)
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setAlignment_(1)  # NSTextAlignmentCenter
    window.contentView().addSubview_(label)

    # Deliberately `orderFrontRegardless()`, never `makeKeyAndOrderFront_`
    # or `activateIgnoringOtherApps_`: this must occlude visually without
    # becoming key window or frontmost application.
    window.orderFrontRegardless()

    print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
    app.run()


if __name__ == "__main__":
    try:
        build_and_run()
    except KeyboardInterrupt:
        sys.exit(0)
