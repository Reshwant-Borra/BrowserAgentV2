"""Background-safety classification logic.

This module turns *measured* interference signals into an
`InterferenceClassification`. It never accepts a model's opinion of
whether an action was background-safe (docs/DECISIONS.md D-011) and it
never treats action/postcondition success as a proxy for non-interference
(the two are tracked as separate fields on `ExperimentObservation`).
"""

from __future__ import annotations

from typing import Optional

from phase0.schemas.evidence import ActionOutcome, InterferenceClassification


def classify_interference(
    *,
    cursor_moved: Optional[bool],
    foreground_changed: Optional[bool],
    focus_changed: Optional[bool],
    action_outcome: ActionOutcome,
    supported: bool = True,
) -> InterferenceClassification:
    """Classify a single trial from measured before/after signals.

    Precedence:
    1. `action_outcome == ERROR` -> ERROR (the harness could not even run
       the action/observers correctly; the trial says nothing about
       interference).
    2. `not supported` -> UNSUPPORTED (the platform/permission/target does
       not support this operation at all).
    3. Any signal is definitely `True` -> classify by how many of
       {cursor_moved, foreground_changed, focus_changed} are `True`
       (unmeasurable/`None` signals are *not* counted, but also cannot
       hide a proven interference):
         - 1  -> the specific *_INTERFERENCE label
         - >1 -> MULTIPLE_INTERFERENCE
       A definite interference is definite regardless of what else was
       unmeasurable in the same trial - an unrelated broken observer
       (e.g. a target app not exposing `AXFocusedUIElement`) must never
       downgrade a *proven* cursor/foreground/focus interference to
       INCONCLUSIVE. This exact gap was found by this harness's own
       cursor positive control returning INCONCLUSIVE instead of
       CURSOR_INTERFERENCE when the focus signal was unavailable.
    4. Otherwise, if any signal is unmeasurable (`None`) -> INCONCLUSIVE
       (no signal proved interference, but we also cannot claim
       BACKGROUND_SAFE from partial data).
    5. Otherwise (all three measured `False`) -> BACKGROUND_SAFE.
    """

    if action_outcome == ActionOutcome.ERROR:
        return InterferenceClassification.ERROR

    if not supported:
        return InterferenceClassification.UNSUPPORTED

    signals = (cursor_moved, foreground_changed, focus_changed)
    interference_count = sum(1 for signal in signals if signal is True)

    if interference_count > 1:
        return InterferenceClassification.MULTIPLE_INTERFERENCE
    if interference_count == 1:
        if cursor_moved:
            return InterferenceClassification.CURSOR_INTERFERENCE
        if foreground_changed:
            return InterferenceClassification.FOREGROUND_INTERFERENCE
        return InterferenceClassification.FOCUS_INTERFERENCE

    if any(signal is None for signal in signals):
        return InterferenceClassification.INCONCLUSIVE

    return InterferenceClassification.BACKGROUND_SAFE
