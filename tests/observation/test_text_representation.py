"""Text representation: the bare-`<div>` investigation and its cost.

Issue C asked whether excluding bare `<div>` text is a genuine defect or
whether equivalent content is already represented elsewhere. The answer is
measured here, not asserted.

The strategy changed from a fixed tag whitelist plus `textContent` to each
element's OWN direct text nodes. That is a statement about where text lives,
not about which tags matter, and it happens to remove the duplication the old
approach created.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PORT_BASE = 9121

#: Every marker the fixture says must be observable.
EXPECTED_SIGNALS = [
    "SIGNAL bare div text",
    "SIGNAL nested div text",
    "SIGNAL div heading",
    "SIGNAL text beside a heading",
    "SIGNAL text next to a control",
    "SIGNAL duplicated line",
    "SIGNAL status message",
    "SIGNAL alert message",
    "SIGNAL Account balance: $42",
    "SIGNAL initial dynamic text",
    "SIGNAL paragraph text",
    "SIGNAL span text",
    "SIGNAL list item text",
    "SIGNAL caption",
    "SIGNAL cell text",
]

#: Content that must never appear.
EXPECTED_ABSENT = [
    "NOISE visually hidden div",
    "NOISE aria hidden div",
    "NOISE script string",
]


def _text(kernel, cluster, path):
    kernel.navigate(cluster.url(path))
    obs = kernel.observe()
    return obs, [b.text for b in obs.text_blocks]


# ------------------------------------------------------------------ recall


@pytest.mark.parametrize("signal", EXPECTED_SIGNALS)
def test_semantically_relevant_text_is_observed(kit, signal):
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_variants")
    assert any(signal in b for b in blocks), f"missing {signal!r}"


@pytest.mark.parametrize("absent", EXPECTED_ABSENT)
def test_hidden_and_non_content_text_is_not_observed(kit, absent):
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_variants")
    assert not any(absent in b for b in blocks), f"leaked {absent!r}"


def test_dynamically_updated_text_is_observed_after_the_change(kit):
    kernel, cluster = kit
    obs, blocks = _text(kernel, cluster, "/p/text_variants")
    assert any("SIGNAL initial dynamic text" in b for b in blocks)
    kernel.click(next(e for e in obs.elements if e.name == "Update dynamic").target)
    obs2 = kernel.observe()
    blocks2 = [b.text for b in obs2.text_blocks]
    assert any("SIGNAL updated dynamic text" in b for b in blocks2)
    assert not any("SIGNAL initial dynamic text" in b for b in blocks2)


def test_control_labels_are_not_repeated_as_text(kit):
    """The element list already states them, with a target attached."""
    kernel, cluster = kit
    obs, blocks = _text(kernel, cluster, "/p/text_variants")
    names = {e.name for e in obs.elements if e.name}
    assert "Unique Control Label" in names
    assert not any(b == "Unique Control Label" for b in blocks)


def test_identical_lines_collapse(kit):
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_variants")
    assert len(blocks) == len(set(blocks)), "duplicate text blocks present"
    assert sum(1 for b in blocks if b == "SIGNAL duplicated line") == 1


def test_wrapper_containers_contribute_nothing(kit):
    """A div that only wraps other elements has no direct text of its own."""
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_variants")
    # The outer wrapper's textContent would have been "SIGNAL nested div text";
    # with direct-text-node extraction it appears exactly once, from the inner.
    assert sum(1 for b in blocks if "SIGNAL nested div text" in b) == 1


# ------------------------------------------------------------------- frames


def test_text_is_frame_scoped(kit):
    """Child-frame text is observable and tagged with its frame."""
    kernel, cluster = kit
    kernel.navigate(cluster.url("/p/frames_adversarial"))
    import time
    time.sleep(0.8)
    obs = kernel.observe()
    frames = {b.frame_id for b in obs.text_blocks}
    assert len(frames) >= 2, f"text came from only {frames}"
    child_text = [b.text for b in obs.text_blocks if b.frame_id != obs.main_frame_id]
    assert any("leaf" in t for t in child_text), child_text[:5]
    main_text = [b.text for b in obs.text_blocks if b.frame_id == obs.main_frame_id]
    assert any("Adversarial frames" in t for t in main_text)


# -------------------------------------------------------------------- noise


def test_signal_recall_on_a_realistic_page(kit):
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_noise")
    joined = "\n".join(blocks)
    for s in ("SIGNAL Order status", "SIGNAL Amount due", "SIGNAL Payment due by",
              "SIGNAL Widget A", "SIGNAL Widget B"):
        assert s in joined, f"missing {s!r}"


def test_observation_size_stays_bounded(kit):
    """A recall fix must not become a DOM dump.

    The realistic fixture carries eight nav links, eight footer lines, four
    repeated recommendation cards and a form. The bound is generous but finite;
    the point is that it is asserted at all.
    """
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/text_noise")
    chars = sum(len(b) for b in blocks)
    assert len(blocks) <= 60, f"{len(blocks)} text blocks"
    assert chars <= 1500, f"{chars} characters of text"
    print(f"\ntext_noise blocks={len(blocks)} chars={chars}")


def test_table_page_text_did_not_grow(kit):
    """On table-heavy pages the new strategy is a net reduction.

    Cell text used to be captured twice: once from the `td` and again from any
    nested element. Direct-text extraction plus de-duplication removes that.
    """
    kernel, cluster = kit
    _obs, blocks = _text(kernel, cluster, "/p/verify_records")
    chars = sum(len(b) for b in blocks)
    assert len(blocks) == len(set(blocks))
    assert chars <= 209, f"{chars} chars, was 209 under the old strategy"
    print(f"\nverify_records blocks={len(blocks)} chars={chars} (old: 17 blocks/209 chars)")
