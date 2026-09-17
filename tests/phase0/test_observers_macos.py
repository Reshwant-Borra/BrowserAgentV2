"""Unit tests for macOS focused-element identity/change detection
(phase0/harness/observers_macos.py). All inputs are hand-built
`Measurement`s - no real desktop control, no Quartz/AppKit/
ApplicationServices calls.

These specifically guard against the false-negative this module was
hardened for: two distinct, untitled AXTextFields comparing equal on
(role, title) alone must not be reported as the same focused element.
"""

from __future__ import annotations

from phase0.harness.observers_macos import _element_identity_changed, focus_changed
from phase0.schemas.evidence import Measurement

UNAVAILABLE_WINDOW = Measurement.unavailable("test: window unavailable")


def _element(
    *,
    role="AXTextField",
    subrole=None,
    identifier=None,
    title=None,
    description=None,
    help_text=None,
    position=None,
    size=None,
    value=None,
    available=True,
) -> Measurement:
    if not available:
        return Measurement.unavailable("test: element unavailable")
    return Measurement.of(
        {
            "role": role,
            "subrole": subrole,
            "identifier": identifier,
            "title": title,
            "description": description,
            "help": help_text,
            "position": {"x": position[0], "y": position[1]} if position else None,
            "size": {"width": size[0], "height": size[1]} if size else None,
            "value": value,
            "value_length": len(value) if value is not None else None,
            "value_truncated": False,
        }
    )


def _window(title) -> Measurement:
    return Measurement.of({"title": title}) if title is not None else UNAVAILABLE_WINDOW


# --- same element, content/value changed -> NO focus interference --------


def test_same_element_value_change_is_not_identity_change():
    before = _element(title="Search", position=(10, 10), size=(200, 24), value="abc")
    after = _element(title="Search", position=(10, 10), size=(200, 24), value="abc123xyz")

    assert _element_identity_changed(before, after) is False


def test_same_element_value_change_is_not_focus_interference():
    window = _window("Main Window")
    before = _element(title="Search", position=(10, 10), size=(200, 24), value="abc")
    after = _element(title="Search", position=(10, 10), size=(200, 24), value="abc123xyz")

    assert focus_changed(window, window, before, after) is False


# --- different elements, same role/title -> focus interference -----------


def test_different_identifiers_same_role_and_title_is_identity_change():
    before = _element(title="Field", identifier="field-a", position=(10, 10), size=(200, 24))
    after = _element(title="Field", identifier="field-b", position=(10, 10), size=(200, 24))

    assert _element_identity_changed(before, after) is True


def test_different_identifiers_same_role_and_title_is_focus_interference():
    window = _window("Main Window")
    before = _element(title="Field", identifier="field-a", position=(10, 10), size=(200, 24))
    after = _element(title="Field", identifier="field-b", position=(10, 10), size=(200, 24))

    assert focus_changed(window, window, before, after) is True


# --- different text fields with no titles -> interference when distinguishable


def test_untitled_fields_distinguished_by_geometry_is_identity_change():
    # This is the exact false-negative scenario this module was hardened
    # against: role=AXTextField, title=None on both sides. Geometry is
    # the only available disambiguator, and it clearly differs.
    before = _element(role="AXTextField", title=None, position=(10.0, 10.0), size=(200.0, 24.0))
    after = _element(role="AXTextField", title=None, position=(400.0, 300.0), size=(200.0, 24.0))

    assert _element_identity_changed(before, after) is True


def test_untitled_fields_distinguished_by_geometry_is_focus_interference():
    window = _window("Main Window")
    before = _element(role="AXTextField", title=None, position=(10.0, 10.0), size=(200.0, 24.0))
    after = _element(role="AXTextField", title=None, position=(400.0, 300.0), size=(200.0, 24.0))

    assert focus_changed(window, window, before, after) is True


def test_untitled_same_field_small_geometry_jitter_is_not_identity_change():
    # Sub-pixel jitter within tolerance on the same element must not
    # register as a different element.
    before = _element(role="AXTextField", title=None, position=(10.0, 10.0), size=(200.0, 24.0))
    after = _element(role="AXTextField", title=None, position=(10.3, 10.2), size=(200.0, 24.0))

    assert _element_identity_changed(before, after) is False


# --- window changed -> focus interference ---------------------------------


def test_window_change_is_focus_interference_even_with_identical_element():
    before_window = _window("Window A")
    after_window = _window("Window B")
    # Same element descriptor on both sides (even an ambiguous one) -
    # the window signal alone must still register as interference.
    element = _element(role="AXTextField", title=None)

    assert focus_changed(before_window, after_window, element, element) is True


# --- insufficient identity information -> inconclusive --------------------


def test_role_only_match_is_inconclusive_identity():
    # Only role is comparable; no title, identifier, description, help,
    # or geometry on either side. Must not be asserted as "same".
    before = _element(role="AXTextField", title=None)
    after = _element(role="AXTextField", title=None)

    assert _element_identity_changed(before, after) is None


def test_role_only_match_is_inconclusive_focus_change():
    window = _window("Main Window")
    before = _element(role="AXTextField", title=None)
    after = _element(role="AXTextField", title=None)

    assert focus_changed(window, window, before, after) is None


def test_element_unavailable_is_inconclusive():
    window = _window("Main Window")
    before = _element(title="Search")
    after = _element(available=False)

    assert _element_identity_changed(before, after) is None
    assert focus_changed(window, window, before, after) is None


# --- normal stable same-element observation -> unchanged ------------------


def test_fully_matching_descriptor_is_unchanged():
    before = _element(
        role="AXTextField",
        subrole="AXSearchField",
        identifier="search-box",
        title="Search",
        description="Search the document",
        help_text="Type to search",
        position=(10, 10),
        size=(200, 24),
        value="hello",
    )
    after = _element(
        role="AXTextField",
        subrole="AXSearchField",
        identifier="search-box",
        title="Search",
        description="Search the document",
        help_text="Type to search",
        position=(10, 10),
        size=(200, 24),
        value="hello",
    )

    assert _element_identity_changed(before, after) is False

    window = _window("Main Window")
    assert focus_changed(window, window, before, after) is False


# --- role/subrole mismatches are always decisive --------------------------


def test_role_mismatch_is_identity_change_even_with_matching_title():
    before = _element(role="AXTextField", title="Same Title")
    after = _element(role="AXButton", title="Same Title")

    assert _element_identity_changed(before, after) is True


def test_subrole_mismatch_is_identity_change():
    before = _element(role="AXButton", subrole="AXCloseButton", position=(10, 10), size=(16, 16))
    after = _element(role="AXButton", subrole="AXZoomButton", position=(10, 10), size=(16, 16))

    assert _element_identity_changed(before, after) is True
