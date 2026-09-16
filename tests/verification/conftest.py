"""Shared pytest fixtures for the Verifier gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.verification.harness import VerifierHarness  # noqa: E402


@pytest.fixture(scope="session")
def harness():
    """One browser for the whole session.

    Each test navigates to its own fixture page first, which resets page state.
    Tests that mutate the page registry (popups, tabs) clean up after
    themselves so page identity stays meaningful across tests.
    """
    h = VerifierHarness()
    try:
        yield h
    finally:
        h.close()


@pytest.fixture
def fresh(harness):
    """A harness with the page-effect log cleared.

    Not autouse: the contract unit tests must not start a browser.
    """
    harness.reset_effects()
    return harness
