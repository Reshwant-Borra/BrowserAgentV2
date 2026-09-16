"""CLICK postconditions: DOM state, navigation, popup, dialog, download, no-op.

A click does not define its own success. The headline test here is
`test_wrong_but_valid_control_is_rejected`: the BrowserKernel reports a
successful click on a control the PolicyEngine correctly permits, and the
Verifier still says NOT_SATISFIED because the intended outcome did not happen.
"""

from __future__ import annotations

import time

import pytest

from browser_agent_v2.verification import (
    AllOf,
    DialogState,
    DownloadPresent,
    ElementPresence,
    PageState,
    Reason,
    TextPresence,
    UrlIs,
    VerificationStatus,
)
from browser_agent_v2.verification.postconditions import TextMatch

SAT = VerificationStatus.SATISFIED
NOT = VerificationStatus.NOT_SATISFIED
AMB = VerificationStatus.AMBIGUOUS


# ------------------------------------------------------------ DOM outcomes


def test_click_producing_expected_outcome(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Approve request")
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        TextPresence(page_id=obs.page_id, text="Right outcome recorded"),
    )
    assert step.execution_status == "OK"
    assert result.status is SAT


def test_wrong_but_valid_control_is_rejected(fresh):
    """THE test this gate exists for.

    "Decline request" is a real, enabled, policy-permitted control. The click
    genuinely succeeds. The intended postcondition is still false.
    """
    obs = fresh.goto("/p/verify_outcomes")
    wrong = fresh.find(obs, name="Decline request")
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(wrong.target),
        TextPresence(page_id=obs.page_id, text="Right outcome recorded"),
    )
    assert step.execution_status == "OK", "the browser action must have succeeded"
    assert step.kernel_error is None
    assert result.status is NOT
    assert result.reason is Reason.TEXT_MISSING
    # and the page really did do something — it just did the wrong thing
    assert "Wrong outcome recorded" in fresh.effects()


def test_true_noop_is_rejected(fresh):
    """Click succeeds, nothing changes. Not a browser error; still a failure."""
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Do nothing")
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        TextPresence(page_id=obs.page_id, text="Right outcome recorded"),
    )
    assert step.execution_status == "OK"
    assert result.status is NOT
    assert result.reason is Reason.TEXT_MISSING


def test_element_appears(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Show panel")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        ElementPresence(page_id=obs.page_id, role="button",
                        name="Close panel", expect_present=True),
    )
    assert result.status is SAT


def test_element_expected_to_appear_but_does_not(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Do nothing")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        ElementPresence(page_id=obs.page_id, role="button",
                        name="Close panel", expect_present=True),
    )
    assert result.status is NOT
    assert result.reason is Reason.ELEMENT_MISSING


def test_element_disappears(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    fresh.kernel.click(fresh.find(obs, name="Show panel").target)
    obs2 = fresh.observe()
    close = fresh.find(obs2, name="Close panel")
    result, _ = fresh.act_and_verify(
        obs2,
        lambda: fresh.kernel.click(close.target),
        ElementPresence(page_id=obs2.page_id, role="button",
                        name="Close panel", expect_present=False),
    )
    assert result.status is SAT


def test_element_expected_absent_but_still_present(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(fresh.find(obs, name="Show panel").target),
        ElementPresence(page_id=obs.page_id, role="button",
                        name="Show panel", expect_present=False),
    )
    assert result.status is NOT
    assert result.reason is Reason.ELEMENT_UNEXPECTEDLY_PRESENT


def test_hidden_element_does_not_count_as_present(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    fresh.kernel.click(fresh.find(obs, name="Show panel").target)
    fresh.kernel.page_object().evaluate(
        "() => { document.getElementById('panel-close').style.display = 'none'; }"
    )
    obs2 = fresh.observe()
    result = fresh.verify(
        fresh.act(obs2, lambda: None),
        ElementPresence(page_id=obs2.page_id, role="button", name="Close panel",
                        expect_present=True, require_visible=True),
    )
    assert result.status is NOT


# ------------------------------------------------------- click → navigation


def test_click_causing_expected_navigation(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Go to confirmation")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm")),
    )
    assert result.status is SAT


def test_click_navigating_somewhere_else_is_rejected(fresh):
    """"Some navigation happened" is not success when a destination was named."""
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Go somewhere else")
    result, step = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm")),
    )
    assert step.execution_status == "OK"
    assert result.status is NOT
    assert result.reason is Reason.URL_MISMATCH
    assert result.checks[0].observed.endswith("/p/verify_other")


def test_navigation_and_confirmation_together(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Go to confirmation")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        AllOf(page_id=obs.page_id, parts=(
            UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm")),
            TextPresence(page_id=obs.page_id, text="Submission confirmed"),
        )),
    )
    assert result.status is SAT
    assert len(result.checks) == 2


def test_composite_fails_if_any_part_fails(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Go somewhere else")
    result, _ = fresh.act_and_verify(
        obs,
        lambda: fresh.kernel.click(btn.target),
        AllOf(page_id=obs.page_id, parts=(
            UrlIs(page_id=obs.page_id, expected=fresh.url("/p/verify_confirm")),
            TextPresence(page_id=obs.page_id, text="Submission confirmed"),
        )),
    )
    assert result.status is NOT
    assert result.reason is Reason.COMPOSITE_FAILED


# ------------------------------------------------------------ click → popup


def test_click_creating_expected_popup(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, contains="Open confirmation popup")
    step = fresh.act_expecting_page(obs, lambda: fresh.kernel.click(btn.target))
    assert step.new_page_ids, "fixture did not open a popup"
    popup = step.new_page_ids[0]
    result = fresh.verify(
        step,
        PageState(page_id=popup, expect_exists=True,
                  expect_opener_page_id=obs.page_id,
                  expect_url=fresh.url("/p/verify_confirm")),
    )
    assert result.status is SAT
    fresh.kernel.close_agent_tab(popup)


def test_unrelated_popup_does_not_satisfy(fresh):
    """A popup that opened is not the popup that was expected."""
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, contains="Open other popup")
    step = fresh.act_expecting_page(obs, lambda: fresh.kernel.click(btn.target))
    popup = step.new_page_ids[0]
    result = fresh.verify(
        step,
        PageState(page_id=popup, expect_exists=True,
                  expect_url=fresh.url("/p/verify_confirm")),
    )
    assert result.status is NOT
    assert result.reason is Reason.URL_MISMATCH
    fresh.kernel.close_agent_tab(popup)


def test_popup_with_wrong_opener_is_rejected(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, contains="Open confirmation popup")
    step = fresh.act_expecting_page(obs, lambda: fresh.kernel.click(btn.target))
    popup = step.new_page_ids[0]
    result = fresh.verify(
        step,
        PageState(page_id=popup, expect_exists=True,
                  expect_opener_page_id="page_does_not_exist"),
    )
    assert result.status is NOT
    assert result.reason is Reason.PAGE_WRONG_OPENER
    fresh.kernel.close_agent_tab(popup)


def test_expected_popup_that_never_opened(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Do nothing")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    assert step.new_page_ids == []
    result = fresh.verify(step, PageState(page_id="page_9999", expect_exists=True))
    assert result.status is NOT
    assert result.reason is Reason.PAGE_MISSING


# ----------------------------------------------------------- click → dialog


def test_expected_dialog_opens(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Raise alert")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    result = fresh.verify(
        step,
        DialogState(page_id=obs.page_id, expect_open=True, kind="alert",
                    message_contains="outcome alert"),
    )
    assert result.status is SAT
    fresh.kernel.handle_dialog(accept=True)


def test_wrong_dialog_kind_is_rejected(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Raise alert")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    result = fresh.verify(
        step, DialogState(page_id=obs.page_id, expect_open=True, kind="prompt")
    )
    assert result.status is NOT
    assert result.reason is Reason.DIALOG_MISMATCH
    fresh.kernel.handle_dialog(accept=True)


def test_no_dialog_when_one_was_expected(fresh):
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Do nothing")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    result = fresh.verify(step, DialogState(page_id=obs.page_id, expect_open=True))
    assert result.status is NOT
    assert result.reason is Reason.DIALOG_MISSING


def test_dialog_gone_before_verification_is_not_satisfied(fresh):
    """Expected-open but already handled: definitively not open now."""
    obs = fresh.goto("/p/verify_outcomes")
    btn = fresh.find(obs, name="Raise alert")
    step = fresh.act(obs, lambda: fresh.kernel.click(btn.target))
    fresh.kernel.handle_dialog(accept=True)
    result = fresh.verify(step, DialogState(page_id=obs.page_id, expect_open=True))
    assert result.status is NOT
    assert result.reason is Reason.DIALOG_MISSING


# --------------------------------------------------------- click → download


def test_expected_download_is_verified(fresh):
    fresh.downloads.reset()
    obs = fresh.goto("/p/verify_outcomes")
    link = fresh.find(obs, name="Download report")
    page = fresh.kernel.page_object()
    step = fresh.act(
        obs,
        lambda: fresh.downloads.capture(page, lambda: fresh.kernel.click(link.target)),
    )
    result = fresh.verify(
        step, DownloadPresent(page_id=obs.page_id, filename="report.csv", min_bytes=10)
    )
    assert result.status is SAT, result.to_json()
    assert result.evidence["size_bytes"] > 10


def test_no_download_is_rejected(fresh):
    fresh.downloads.reset()
    obs = fresh.goto("/p/verify_outcomes")
    page = fresh.kernel.page_object()
    step = fresh.act(
        obs,
        lambda: fresh.downloads.capture(
            page,
            lambda: fresh.kernel.click(fresh.find(obs, name="Do nothing").target),
            timeout_ms=1500,
        ),
    )
    result = fresh.verify(
        step, DownloadPresent(page_id=obs.page_id, filename="report.csv")
    )
    assert result.status is NOT
    assert result.reason is Reason.DOWNLOAD_MISSING


def test_wrong_file_is_rejected(fresh):
    fresh.downloads.reset()
    fresh.downloads.add_synthetic(filename="other.csv", size_bytes=99, complete=True)
    obs = fresh.observe()
    result = fresh.verify(
        fresh.act(obs, lambda: None),
        DownloadPresent(page_id=obs.page_id, filename="report.csv"),
    )
    assert result.status is NOT
    assert result.reason is Reason.DOWNLOAD_MISSING


def test_started_but_incomplete_download_is_rejected(fresh):
    """A download that began is not a download that finished."""
    fresh.downloads.reset()
    rec = fresh.downloads.add_synthetic(
        filename="report.csv", size_bytes=0, complete=False
    )
    obs = fresh.observe()
    result = fresh.verify(
        fresh.act(obs, lambda: None),
        DownloadPresent(page_id=obs.page_id, artifact_id=rec.artifact_id),
    )
    assert result.status is NOT
    assert result.reason is Reason.DOWNLOAD_INCOMPLETE


def test_download_hash_mismatch_is_rejected(fresh):
    fresh.downloads.reset()
    rec = fresh.downloads.add_synthetic(
        filename="report.csv", size_bytes=50, complete=True, sha256="a" * 64
    )
    obs = fresh.observe()
    result = fresh.verify(
        fresh.act(obs, lambda: None),
        DownloadPresent(page_id=obs.page_id, artifact_id=rec.artifact_id,
                        expected_sha256="b" * 64),
    )
    assert result.status is NOT
    assert result.reason is Reason.DOWNLOAD_MISMATCH
