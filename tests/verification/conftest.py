"""Verifier-suite fixtures.

The `harness` and `fresh` fixtures live in the top-level tests/conftest.py
so the observation-contract suites can share one browser session with this
one; Playwright forbids two live sync instances in a process.
"""
