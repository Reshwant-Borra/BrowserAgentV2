"""The typed postcondition set.

An ActionIntent carries one of these so the Verifier knows *what was expected*
rather than inferring intent from natural language. The set is deliberately
small: one type per thing the current MVP action space can actually accomplish
(END_TO_END_SYSTEM_SPEC section 4.4).

Every postcondition is scoped to a `page_id`, and DOM-level ones additionally to
a `frame_id`. That scoping is not decoration — Experiments 4, 5 and 7 showed
that identical text on another page or in another frame is the realistic way a
verifier accidentally reports success.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional, Sequence


class TextMatch(str, enum.Enum):
    EXACT = "EXACT"
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"


class ValueMatch(str, enum.Enum):
    #: Byte-for-byte. The default, because "Tam" instead of "Tampa" is the
    #: BrowserAgent V1 failure class this whole layer exists to catch.
    EXACT = "EXACT"
    #: Leading/trailing whitespace ignored. Must be requested explicitly.
    TRIMMED = "TRIMMED"


@dataclass(frozen=True)
class Postcondition:
    """Base class. Subclasses are plain data; evaluation lives in the Verifier."""

    page_id: str


@dataclass(frozen=True)
class FieldValueEquals(Postcondition):
    """A text-entry control holds exactly this value.

    `target` is the observation-scoped ref the action used. It is tried first,
    because node identity is the strongest evidence available (ADR-012). If the
    node no longer exists the Verifier may fall back to a *unique* semantic
    match in the fresh observation, and refuses when that match is ambiguous.
    """

    target: str
    expected: str
    role: str = "textbox"
    name: Optional[str] = None
    frame_id: str = "f0"
    match: ValueMatch = ValueMatch.EXACT


@dataclass(frozen=True)
class SelectValueEquals(Postcondition):
    """A combobox has this option value selected.

    Compared against the control's underlying value, never its visible label:
    duplicate labels with different values are a real pattern and the label
    cannot distinguish them.
    """

    target: str
    expected_value: str
    name: Optional[str] = None
    frame_id: str = "f0"


@dataclass(frozen=True)
class UrlIs(Postcondition):
    """The page is at this destination.

    A specific destination, not "some navigation happened". Title is never used.
    """

    expected: str
    match: TextMatch = TextMatch.EXACT


@dataclass(frozen=True)
class ElementPresence(Postcondition):
    """An element with this role and accessible name is (or is not) present.

    Frame scoping, and why it is not simply `frame_id`
    --------------------------------------------------
    A kernel `frame_id` is a *positional index* over the frame list, not an
    identity. Detaching a frame renumbers the rest: on the frames fixture, `f1`
    means the same-origin child before a detach and the cross-origin child
    after it, while the frame count stays the same. Both contain a control
    named "Confirm", so trusting the index produces a wrong-frame false
    success. This is the same defect class as identifying a tab by its index,
    which Experiment 5 ruled out for pages.

    So:

    * ``frame_id="f0"`` (the main frame) is a stable identity and needs nothing
      more.
    * Any other frame must be pinned by ``section`` — the nearest heading
      inside that frame's own document — which is content-derived and does not
      shift when sibling frames come and go. The index is then advisory only.
    * A non-main frame with no ``section`` cannot be scoped safely, and the
      Verifier answers AMBIGUOUS rather than guessing.
    """

    role: str
    name: str
    expect_present: bool = True
    frame_id: Optional[str] = "f0"
    #: Nearest-heading anchor. Disambiguates duplicate control names, and is
    #: REQUIRED to scope to any frame other than the main one.
    section: Optional[str] = None
    #: When True, a present-but-not-visible element does not count as present.
    require_visible: bool = True


@dataclass(frozen=True)
class TextPresence(Postcondition):
    """Page text contains (or does not contain) this string."""

    text: str
    expect_present: bool = True
    frame_id: Optional[str] = "f0"
    match: TextMatch = TextMatch.CONTAINS


@dataclass(frozen=True)
class PageState(Postcondition):
    """A page exists / is active / was opened by a particular page.

    Identity is the `page_id` minted at the creation event (Experiment 5). `url`
    is an additional assertion, never the identity.
    """

    expect_exists: bool = True
    expect_active: Optional[bool] = None
    expect_opener_page_id: Optional[str] = None
    expect_url: Optional[str] = None
    url_match: TextMatch = TextMatch.EXACT


@dataclass(frozen=True)
class DialogState(Postcondition):
    """A native dialog of this kind is open.

    Reads the BrowserKernel's dialog state rather than inventing a second
    mechanism (Experiment 1 established the dialog as explicit kernel state).
    """

    expect_open: bool = True
    kind: Optional[str] = None  # alert | confirm | prompt
    message_contains: Optional[str] = None


@dataclass(frozen=True)
class DownloadPresent(Postcondition):
    """A completed download artifact exists.

    A started download is not a finished one, so completion is required unless
    explicitly waived.
    """

    artifact_id: Optional[str] = None
    filename: Optional[str] = None
    min_bytes: int = 1
    require_complete: bool = True
    expected_sha256: Optional[str] = None


@dataclass(frozen=True)
class OperationRecorded(Postcondition):
    """A consequential operation is durably recorded on the far side.

    This is the only postcondition whose evidence is external to the browser.
    When the durable channel cannot be reached the answer is AMBIGUOUS, and per
    ADR-014 the controller must reconcile or ask the user — never retry.
    """

    operation_id: str
    expect_recorded: bool = True


@dataclass(frozen=True)
class AllOf(Postcondition):
    """Every member must hold.

    The single combinator in the set. It exists because real intents genuinely
    have compound postconditions — a submit click expects a confirmation *and* a
    durable record — and expressing that as two unrelated results would lose the
    fact that they describe one action. No `AnyOf` and no `Not`: neither has an
    established use, and each would be a step toward a rule DSL.
    """

    parts: Sequence[Postcondition] = ()


#: Postconditions that consult a browser observation and therefore require
#: freshness checking. `OperationRecorded` and `DownloadPresent` read durable
#: stores instead.
OBSERVATION_BACKED = (
    FieldValueEquals,
    SelectValueEquals,
    UrlIs,
    ElementPresence,
    TextPresence,
    PageState,
)
