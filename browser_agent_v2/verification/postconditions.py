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

#: Re-exported so callers scope to "this page's main frame" without knowing the
#: minted id. Defined in the kernel contracts; mirrored here to keep production
#: verification free of experiment imports.
MAIN_FRAME = "main"


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
    frame_id: str = MAIN_FRAME
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
    frame_id: str = MAIN_FRAME


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

    Frame scoping
    -------------
    Under Observation Contract V1 a `frame_id` is a minted identity, issued at
    the frame's attach event and never reused for a different frame. It can be
    trusted directly, so no content pin is required.

    * ``frame_id=MAIN_FRAME`` — this page's main frame, whatever its minted id.
    * ``frame_id="fr_7"`` — exactly that frame. If it has detached, the element
      is reported missing; another frame can never answer for it.
    * ``frame_id=None`` — any frame on the page.

    Before V1 the kernel numbered frames positionally, so detaching a frame
    renumbered the rest and an id could transfer between frames. The Verifier
    defended against that by refusing any unpinned non-main frame scope. That
    workaround is gone because the defect is gone; see ADR-016.

    ``section`` remains available as an ordinary disambiguator for duplicate
    control names within a frame. It is no longer load-bearing for identity.
    """

    role: str
    name: str
    expect_present: bool = True
    frame_id: Optional[str] = MAIN_FRAME
    #: Nearest-heading anchor. Disambiguates duplicate control names.
    section: Optional[str] = None
    #: When True, a present-but-not-visible element does not count as present.
    require_visible: bool = True
    #: Enclosing row / list item, matched against ObservedGroup.cells. Lets a
    #: postcondition say "the Open button in B. Lindqvist's row" instead of
    #: "one of three identical Open buttons".
    group_cells: Optional[dict] = None


@dataclass(frozen=True)
class TextPresence(Postcondition):
    """Page text contains (or does not contain) this string.

    Text is frame-scoped under Observation Contract V1: every block carries the
    minted id of the frame it came from, so a child frame's text can be
    asserted directly. Before V1, text was collected for the main frame only
    and any frame-scoped assertion had to be refused.
    """

    text: str
    expect_present: bool = True
    frame_id: Optional[str] = MAIN_FRAME
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
