"""Deterministic, harmless AX target for the macOS Accessibility spike.

This is a tiny standalone Cocoa app (not a production component) whose
only purpose is to give `phase0/experiments/macos_ax` a controlled
AXUIElement tree to probe: two editable, untitled AXTextFields (the
second exists only for the focus-switch positive control - see
`SECOND_TEXT_FIELD_INITIAL_VALUE` below) and one AXButton that
increments an AXStaticText counter when pressed, and nothing else. It
holds no user data and needs no save step, so it can be killed
(SIGTERM/SIGKILL) at any time with no cleanup prompts.

Run standalone for manual inspection:
    python3 phase0/fixtures/mac_ax_fixture_app.py

On startup it prints a single JSON line to stdout once its window
exists: {"ready": true, "pid": <pid>}. Callers should read that line to
know when it is safe to attach AX calls to `pid`.

It uses `NSApplicationActivationPolicyAccessory` so it does not create a
Dock icon or appear in Cmd-Tab, minimizing incidental interference with
the rest of the desktop.
"""

from __future__ import annotations

import json
import os
import sys

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSButton,
    NSMakeRect,
    NSObject,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)

WINDOW_TITLE = "ComputerAgent Phase0 AX Fixture"
TEXT_FIELD_INITIAL_VALUE = "phase0-initial-value"
# A second, deliberately untitled AXTextField identical in role/title to
# the first. It exists so a real-machine test can move AX focus between
# two elements a naive (role, title) identity check cannot tell apart -
# proving the hardened focus-interference detector does not produce a
# false negative on this exact shape (see phase0/README.md and
# observers_macos._element_identity_changed). Distinguishable only by
# geometry (its frame position), same as many real untitled form fields.
SECOND_TEXT_FIELD_INITIAL_VALUE = "phase0-second-field"
COUNTER_LABEL_PREFIX = "pressed:"
BUTTON_TITLE = "Press Me"

_handler_ref = None  # module-global strong reference; see build_and_run()


class _ButtonHandler(NSObject):
    def initWithLabel_(self, label):
        self = objc.super(_ButtonHandler, self).init()
        if self is None:
            return None
        self.label = label
        self.count = 0
        return self

    def onPress_(self, sender):  # noqa: N802 - Objective-C selector naming
        self.count += 1
        self.label.setStringValue_(f"{COUNTER_LABEL_PREFIX}{self.count}")


def build_and_run() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    rect = NSMakeRect(100, 100, 320, 190)
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, style, NSBackingStoreBuffered, False
    )
    window.setTitle_(WINDOW_TITLE)

    text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 130, 280, 24))
    text_field.setStringValue_(TEXT_FIELD_INITIAL_VALUE)
    window.contentView().addSubview_(text_field)

    # Second AXTextField: same role, no title, same as `text_field` in
    # every (role, title) respect - only its frame position differs.
    # Used exclusively by the focus-switch positive control; the
    # read/set-value/invoke-action trials below only ever address
    # `text_field` (the first one) by role, unaffected by its presence.
    second_text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 90, 280, 24))
    second_text_field.setStringValue_(SECOND_TEXT_FIELD_INITIAL_VALUE)
    window.contentView().addSubview_(second_text_field)

    counter_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 60, 280, 24))
    counter_label.setStringValue_(f"{COUNTER_LABEL_PREFIX}0")
    counter_label.setEditable_(False)
    counter_label.setBezeled_(False)
    counter_label.setDrawsBackground_(False)
    window.contentView().addSubview_(counter_label)

    # Kept alive via a module-global strong reference (PyObjC bridged
    # objects do not support arbitrary attribute assignment for holding
    # our own strong ref, and NSButton's target is a weak/unretained
    # reference from the Python side).
    global _handler_ref
    handler = _ButtonHandler.alloc().initWithLabel_(counter_label)
    _handler_ref = handler

    button = NSButton.alloc().initWithFrame_(NSMakeRect(20, 20, 120, 30))
    button.setTitle_(BUTTON_TITLE)
    button.setBezelStyle_(1)
    button.setTarget_(handler)
    button.setAction_("onPress:")
    window.contentView().addSubview_(button)

    window.makeKeyAndOrderFront_(None)
    # Deterministic starting focus for the focus-switch positive control:
    # without this, initial first-responder assignment is unspecified.
    window.makeFirstResponder_(text_field)

    print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)

    # Deliberately no custom SIGTERM/SIGINT handler: NSApplication.run()
    # blocks in native code, so a Python signal handler would not run
    # until control returns to the interpreter. Leaving the default
    # disposition means `kill <pid>` terminates the process immediately
    # and deterministically, which is what callers rely on for teardown.
    app.run()


if __name__ == "__main__":
    try:
        build_and_run()
    except KeyboardInterrupt:
        sys.exit(0)
