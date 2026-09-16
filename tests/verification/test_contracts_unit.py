"""Unit tests for the verification contracts.

No browser, no fixture server, no model. These pin the invariants that make the
three-valued answer meaningful in the first place.
"""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browser_agent_v2.verification import (  # noqa: E402
    AMBIGUITY_REASONS,
    Check,
    Reason,
    VerificationResult,
    VerificationStatus,
)
from browser_agent_v2.verification.contracts import (  # noqa: E402
    ambiguous,
    not_satisfied,
    satisfied,
)
from browser_agent_v2.verification.verifier import _advanced, _text_matches  # noqa: E402
from browser_agent_v2.verification.postconditions import TextMatch  # noqa: E402


class TestThreeValuedAnswer:
    def test_only_three_statuses_exist(self):
        assert {s.value for s in VerificationStatus} == {
            "SATISFIED", "NOT_SATISFIED", "AMBIGUOUS"
        }

    def test_ambiguous_rejects_a_definite_reason(self):
        """AMBIGUOUS must not become a dumping ground for real failures."""
        with pytest.raises(ValueError, match="not an ambiguity reason"):
            ambiguous("X", Reason.VALUE_MISMATCH, [])

    def test_not_satisfied_rejects_an_ambiguity_reason(self):
        """The converse: missing evidence must not be reported as a definite no."""
        with pytest.raises(ValueError, match="cannot mean NOT_SATISFIED"):
            not_satisfied("X", Reason.EVIDENCE_UNAVAILABLE, [])

    def test_ambiguity_reasons_are_exactly_evidence_problems(self):
        assert {r.value for r in AMBIGUITY_REASONS} == {
            "EVIDENCE_UNAVAILABLE", "STALE_EVIDENCE",
            "EVIDENCE_CONTRADICTORY", "FIELD_AMBIGUOUS",
        }


class TestResultShape:
    def test_serializable_and_complete(self):
        r = satisfied("FieldValueEquals", [Check("v", True, "a", "a")], page_id="page_1")
        js = r.to_json()
        assert set(js) == {
            "status", "reason", "verifier_type", "checks", "evidence", "confidence"
        }
        assert js["status"] == "SATISFIED"
        assert js["verifier_type"] == "FieldValueEquals"
        assert js["confidence"] == "deterministic"
        import json
        json.dumps(js)  # must round-trip through a trace

    def test_result_is_immutable(self):
        r = satisfied("X", [])
        with pytest.raises(FrozenInstanceError):
            r.status = VerificationStatus.NOT_SATISFIED  # type: ignore[misc]

    def test_evidence_stays_compact(self):
        """A result is stored for every action; it must not embed a page."""
        huge = "x" * 5000
        r = satisfied("X", [Check("c", True, expected=huge, observed=huge)])
        rendered = r.to_json()["checks"][0]
        assert len(rendered["expected"]) < 300
        assert "+4760 chars" in rendered["expected"]

    def test_long_lists_are_truncated(self):
        r = satisfied("X", [Check("c", True, observed=list(range(100)))])
        assert len(r.to_json()["checks"][0]["observed"]) == 13


class TestFreshnessComparison:
    @pytest.mark.parametrize(
        "before,after,expected",
        [
            ("obs_00001", "obs_00002", True),
            ("obs_00002", "obs_00002", False),   # identical snapshot replayed
            ("obs_00003", "obs_00002", False),   # older snapshot
            ("obs_00009", "obs_00010", True),    # no lexicographic confusion
            ("obs_00010", "obs_00009", False),
            ("weird-a", "weird-b", True),        # unparseable: difference suffices
            ("weird-a", "weird-a", False),
        ],
    )
    def test_advanced(self, before, after, expected):
        assert _advanced(before, after) is expected


class TestTextMatching:
    @pytest.mark.parametrize(
        "hay,needle,mode,expected",
        [
            ("Submission confirmed", "Submission confirmed", TextMatch.EXACT, True),
            ("Submission confirmed!", "Submission confirmed", TextMatch.EXACT, False),
            ("Submission confirmed!", "Submission confirmed", TextMatch.CONTAINS, True),
            ("/p/a?x=1", r"^/p/a", TextMatch.REGEX, True),
            ("/p/b?x=1", r"^/p/a", TextMatch.REGEX, False),
        ],
    )
    def test_modes(self, hay, needle, mode, expected):
        assert _text_matches(hay, needle, mode) is expected

    def test_unknown_mode_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError):
            _text_matches("a", "a", "NOT_A_MODE")  # type: ignore[arg-type]


class TestNoModelDependency:
    def test_verification_package_imports_no_model_or_experiment_code(self):
        """The Verifier must not be able to consult a model even by accident."""
        import browser_agent_v2.verification as pkg

        pkg_dir = Path(pkg.__file__).parent
        banned = ("ollama", "openai", "anthropic", "model_adapter",
                  "experiments.", "requests", "httpx", "playwright")
        offenders = []
        for py in pkg_dir.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for b in banned:
                    if b in stripped:
                        offenders.append(f"{py.name}: {stripped}")
        assert offenders == [], f"production verifier imports forbidden modules: {offenders}"

    def test_no_retry_or_sleep_primitives_in_production_verifier(self):
        import browser_agent_v2.verification as pkg

        pkg_dir = Path(pkg.__file__).parent
        offenders = []
        for py in pkg_dir.glob("*.py"):
            for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#")[0]
                if "sleep(" in code or "while True" in code or ".reload(" in code:
                    offenders.append(f"{py.name}:{i}: {line.strip()}")
        assert offenders == [], f"retry/wait primitives found: {offenders}"
