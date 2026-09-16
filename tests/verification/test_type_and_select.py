"""TYPE and SELECT verification.

Typing was the headline BrowserAgent V1 failure class, and Experiment 1 found a
runtime that could report a field's *label* as its value. So verification reads
the live control state and compares byte-for-byte by default.
"""

from __future__ import annotations

import pytest

from browser_agent_v2.verification import (
    FieldValueEquals,
    Reason,
    SelectValueEquals,
    VerificationStatus,
)
from browser_agent_v2.verification.postconditions import ValueMatch

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


# --------------------------------------------------------------------- TYPE

TYPE_CASES = [
    ("plain input", "Plain text", "Tampa"),
    ("textarea", "Notes", "line one and line two"),
    ("contenteditable", "Rich note", "rich text value"),
    ("controlled React-style input", "Controlled", "controlled value"),
    ("single leading space", "Plain text", " leading"),
    ("single trailing space", "Plain text", "trailing "),
    ("multiple interior spaces", "Plain text", "a  b   c"),
    ("punctuation", "Plain text", "O'Brien-Smith, Jr. (ret.)"),
    ("unicode", "Plain text", "Müller & Söhne — 東京 — café"),
    ("digits and symbols", "Plain text", "+1 (555) 010-9999 #42"),
    ("email-like", "Plain text", "customer@example.invalid"),
    ("long value", "Notes", "x" * 200),
]


@pytest.mark.parametrize("label,field,value", TYPE_CASES,
                         ids=[c[0] for c in TYPE_CASES])
def test_exact_value_satisfied(fresh, label, field, value):
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name=field)
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, value),
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected=value, name=field),
    )
    assert step.execution_status == "OK"
    assert result.status is SAT, result.to_json()
    assert result.checks[0].observed == value


@pytest.mark.parametrize("mutation", ["Tamp", "Tampaa", "tampa", "Tampa ", " Tampa", "Tanpa"])
def test_one_character_wrong_is_rejected(fresh, mutation):
    """Mutation control: the value the model asked for was 'Tampa'."""
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, mutation),
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="Tampa", name="Plain text"),
    )
    assert result.status is NOT
    assert result.reason is Reason.VALUE_MISMATCH
    assert result.checks[0].observed == mutation


def test_whitespace_is_significant_by_default(fresh):
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, "  padded  "),
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="padded", name="Plain text"),
    )
    assert result.status is NOT, "EXACT matching must not silently trim"


def test_trimmed_mode_is_opt_in(fresh):
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, "  padded  "),
        FieldValueEquals(page_id=obs.page_id, target=el.target, expected="padded",
                         name="Plain text", match=ValueMatch.TRIMMED),
    )
    assert result.status is SAT


def test_hydration_reset_is_not_satisfied(fresh):
    """The field wipes itself 400ms after input.

    The kernel's fill() succeeds; the intended postcondition is false. This is
    precisely the gap between "the action ran" and "the result happened".
    """
    import time

    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Hydrated")
    step = fresh.act(obs, lambda: fresh.kernel.type_text(el.target, "will be wiped"))
    time.sleep(0.9)  # let the page's own reset fire; not a verifier retry
    result = fresh.verify(
        step,
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="will be wiped", name="Hydrated"),
    )
    assert step.execution_status == "OK"
    assert result.status is NOT
    assert result.reason is Reason.VALUE_MISMATCH
    assert result.checks[0].observed == ""


def test_key_handler_field_requires_real_keystrokes(fresh):
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Key only")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, "abc123", slowly=True),
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="abc123", name="Key only"),
    )
    assert result.status is SAT


def test_enter_submit_field_value_still_verified(fresh):
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Search query")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.type_text(el.target, "annual report", submit=True),
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="annual report", name="Search query"),
    )
    assert result.status is SAT


def test_field_removed_after_action_is_not_satisfied(fresh):
    """The page is observable and the field is gone: definitively false."""
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    step = fresh.act(obs, lambda: fresh.kernel.type_text(el.target, "Tampa"))
    fresh.kernel.page_object().evaluate(
        "() => document.getElementById('plain').remove()"
    )
    result = fresh.verify(
        step,
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="Tampa", name="Plain text"),
    )
    assert result.status is NOT
    assert result.reason is Reason.FIELD_NOT_FOUND


def test_duplicate_fields_after_node_loss_are_ambiguous_not_guessed(fresh):
    """Relocation must refuse when more than one control matches.

    Picking one of two identical fields would be a coin flip reported as fact.
    """
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    step = fresh.act(obs, lambda: fresh.kernel.type_text(el.target, "Tampa"))
    # Replace the field with two identically-labelled clones.
    fresh.kernel.page_object().evaluate(
        """() => {
             const old = document.getElementById('plain');
             const host = old.parentElement;
             old.remove();
             for (const id of ['plainA', 'plainB']) {
               const i = document.createElement('input');
               i.type = 'text'; i.id = id;
               i.setAttribute('aria-label', 'Plain text');
               i.value = 'Tampa';
               host.appendChild(i);
             }
           }"""
    )
    result = fresh.verify(
        step,
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="Tampa", name="Plain text"),
    )
    assert result.status is AMB
    assert result.reason is Reason.FIELD_AMBIGUOUS
    assert "2 controls match" in result.evidence["detail"]


def test_unique_relocation_after_rerender_is_allowed(fresh):
    """A legitimately rerendered unique control can still be verified."""
    obs = fresh.goto("/p/inputs")
    el = fresh.find(obs, name="Plain text")
    step = fresh.act(obs, lambda: fresh.kernel.type_text(el.target, "Tampa"))
    fresh.kernel.page_object().evaluate(
        """() => {
             const old = document.getElementById('plain');
             const host = old.parentElement;
             const val = old.value;
             old.remove();
             const i = document.createElement('input');
             i.type='text'; i.id='plain';
             i.setAttribute('aria-label','Plain text');
             i.value = val;
             host.appendChild(i);
           }"""
    )
    result = fresh.verify(
        step,
        FieldValueEquals(page_id=obs.page_id, target=el.target,
                         expected="Tampa", name="Plain text"),
    )
    assert result.status is SAT
    assert result.evidence["resolved_by"] == "relocated_unique"


# ------------------------------------------------------------------- SELECT


@pytest.mark.parametrize("value", ["ca", "us", "mx"])
def test_select_correct_option(fresh, value):
    obs = fresh.goto("/p/selects")
    el = fresh.find(obs, name="Country")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.select(el.target, value),
        SelectValueEquals(page_id=obs.page_id, target=el.target,
                          expected_value=value, name="Country"),
    )
    assert result.status is SAT
    assert result.verifier_type == "SelectValueEquals"


def test_select_wrong_option_rejected(fresh):
    obs = fresh.goto("/p/selects")
    el = fresh.find(obs, name="Country")
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.select(el.target, "mx"),
        SelectValueEquals(page_id=obs.page_id, target=el.target,
                          expected_value="ca", name="Country"),
    )
    assert step.execution_status == "OK", "the browser action itself succeeded"
    assert result.status is NOT
    assert result.checks[0].observed == "mx"


def test_select_verifies_value_not_visible_label(fresh):
    """Two options can share a label; only the value distinguishes them."""
    obs = fresh.goto("/p/selects")
    el = fresh.find(obs, name="Country")
    fresh.kernel.page_object().evaluate(
        """() => {
             const s = document.getElementById('country');
             for (const v of ['dup1','dup2']) {
               const o = document.createElement('option');
               o.value = v; o.textContent = 'Duplicate Label';
               s.appendChild(o);
             }
           }"""
    )
    obs2 = fresh.observe()
    el2 = fresh.find(obs2, name="Country")
    result, _ = fresh.act_and_verify(
        obs2,
        lambda: fresh.kernel.select(el2.target, "dup2"),
        SelectValueEquals(page_id=obs2.page_id, target=el2.target,
                          expected_value="dup1", name="Country"),
    )
    assert result.status is NOT, "matched on the shared label instead of the value"
    assert result.checks[0].observed == "dup2"


def test_select_disabled_option_is_not_satisfied(fresh):
    obs = fresh.goto("/p/selects")
    el = fresh.find(obs, name="Tier")
    fresh.kernel.page_object().evaluate(
        "() => { document.querySelector('#tier option[value=enterprise]').disabled = true; }"
    )
    obs2 = fresh.observe()
    el2 = fresh.find(obs2, name="Tier")
    step = fresh.act(obs2, lambda: fresh.kernel.select(el2.target, "enterprise"))
    result = fresh.verify(
        step,
        SelectValueEquals(page_id=obs2.page_id, target=el2.target,
                          expected_value="enterprise", name="Tier"),
    )
    assert result.status is NOT
