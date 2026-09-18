"""Recovery / retry decision table (M3). Pure functions, no I/O.

See `docs/DECISIONS.md` D-020, `docs/ARCHITECTURE.md` "Recovery
classification". There is no generic exactly-once claim: what may happen
to an unresolved action depends on its declared `EffectClass` and on the
last lifecycle phase the journal durably recorded.

Key rules:
- DISPATCH_STARTED is persisted *before* dispatch, so an action without it
  was provably never dispatched and may be (re)started for any class.
- Once DISPATCH_STARTED exists without a recorded verification, the effect
  may or may not have happened. Classes A/B/C reconcile against a fresh
  independent observation first; class D (non-idempotent, non-queryable)
  becomes OUTCOME_UNKNOWN -> NEEDS_REVIEW and is **never** re-dispatched.
- Persisted post-dispatch observations are re-judged, never re-acted upon.
- At most `MAX_DISPATCHES` dispatches per logical action; A retries reuse
  the same `action_id` (the idempotency key).
"""

from __future__ import annotations

from enum import Enum

from .state import ActionState, Phase
from .types import EffectClass
from .verification import VerificationOutcome as V

MAX_DISPATCHES = 2
A, B, C, D = EffectClass


class Next(str, Enum):
    COMMIT = "COMMIT"
    RETRY = "RETRY"  # start another dispatch of the same logical action
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"  # then NEEDS_REVIEW
    NEEDS_REVIEW = "NEEDS_REVIEW"
    # restart-only decisions
    RESUME_DISPATCH = "RESUME_DISPATCH"  # provably not dispatched yet
    RECONCILE = "RECONCILE"  # observe + verify now, then settle
    JUDGE_PERSISTED = "JUDGE_PERSISTED"  # re-judge durably recorded observations
    SETTLE_PERSISTED = "SETTLE_PERSISTED"  # act on a durably recorded verdict
    COMPLETE_STEP = "COMPLETE_STEP"
    BLOCK_STEP = "BLOCK_STEP"
    NOTHING = "NOTHING"


def after_verification(effect_class: EffectClass, outcome: V, dispatches: int) -> Next:
    if outcome == V.VERIFIED_SUCCESS:
        return Next.COMMIT
    if outcome in (V.PARTIAL_SUCCESS, V.UNEXPECTED_SIDE_EFFECT):
        return Next.NEEDS_REVIEW  # never "complete the rest" blindly
    ambiguous = outcome == V.INCONCLUSIVE
    if dispatches >= MAX_DISPATCHES:
        return Next.OUTCOME_UNKNOWN if ambiguous else Next.NEEDS_REVIEW
    if effect_class == D:
        return Next.OUTCOME_UNKNOWN if ambiguous else Next.NEEDS_REVIEW
    if ambiguous and effect_class == B:
        return Next.OUTCOME_UNKNOWN  # the query itself was inconclusive: retry could duplicate
    return Next.RETRY  # A: same key dedups; B: query showed absent; C: re-set is idempotent


def on_restart(action: ActionState) -> Next:
    phase = action.phase
    if phase in (Phase.INTENT_PERSISTED, Phase.RETRY_PENDING):
        return Next.RESUME_DISPATCH
    if phase in (Phase.DISPATCH_STARTED, Phase.DISPATCH_RETURNED):
        return Next.OUTCOME_UNKNOWN if action.effect_class == D else Next.RECONCILE
    if phase == Phase.OBSERVED_AFTER:
        return Next.JUDGE_PERSISTED
    if phase == Phase.VERIFIED:
        return Next.SETTLE_PERSISTED
    if phase == Phase.OUTCOME_UNKNOWN:
        return Next.NEEDS_REVIEW
    if phase == Phase.COMMITTED:
        return Next.COMPLETE_STEP
    if phase == Phase.ABANDONED:
        return Next.BLOCK_STEP
    return Next.NOTHING
