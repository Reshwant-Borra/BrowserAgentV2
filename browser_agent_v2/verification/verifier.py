"""The deterministic Verifier.

Boundary:

    Decision -> PolicyEngine -> ActionIntent -> BrowserKernel -> ActionResult
                                                                     |
                                              fresh observation / durable evidence
                                                                     |
                                                                  Verifier
                                                                     |
                                                            VerificationResult

Rules this module holds itself to, all of them load-bearing:

* No model is consulted. There is no LLM call anywhere in this file.
* No retry, no reload, no refresh, no waiting loop. A Verifier that retries is
  measuring a different moment than the one it reports on.
* The kernel's "the primitive returned" is never evidence of the postcondition.
* Evidence is always taken fresh, by this module, after the action.
* AMBIGUOUS means insufficient or contradictory evidence. It never means
  "something went wrong".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .contracts import (
    Check,
    Reason,
    VerificationResult,
    VerificationStatus,
    ambiguous,
    not_satisfied,
    satisfied,
)
from .evidence import (
    ArtifactStore,
    DurableEvidenceSource,
    ElementView,
    EvidenceSource,
    EvidenceUnavailable,
    ObservationView,
    PageView,
)
from .postconditions import (
    MAIN_FRAME,
    AllOf,
    DialogState,
    DownloadPresent,
    ElementPresence,
    FieldValueEquals,
    OBSERVATION_BACKED,
    OperationRecorded,
    PageState,
    Postcondition,
    SelectValueEquals,
    TextMatch,
    TextPresence,
    UrlIs,
    ValueMatch,
)

_OBS_SEQ = re.compile(r"(\d+)\s*$")


@dataclass(frozen=True)
class VerificationRequest:
    """Everything the Verifier is allowed to know about the action."""

    postcondition: Postcondition
    #: Observation the decision was made against. Fresh evidence must post-date
    #: it, which is what stops a pre-action snapshot satisfying a postcondition.
    observation_id_before: Optional[str] = None
    execution_status: str = "OK"
    kernel_error: Optional[str] = None
    intent_id: Optional[str] = None
    action: Optional[str] = None

    @classmethod
    def from_action(
        cls, intent: Any, result: Any, postcondition: Postcondition,
        observation_id_before: Optional[str] = None,
    ) -> "VerificationRequest":
        """Build from duck-typed ActionIntent / ActionResult objects."""
        return cls(
            postcondition=postcondition,
            observation_id_before=observation_id_before,
            execution_status=getattr(result, "execution_status", "OK"),
            kernel_error=getattr(result, "kernel_error", None),
            intent_id=getattr(intent, "intent_id", None),
            action=getattr(intent, "action", None),
        )


class Verifier:
    """Evaluates one postcondition against freshly gathered evidence."""

    def __init__(
        self,
        source: EvidenceSource,
        *,
        durable: Optional[DurableEvidenceSource] = None,
        artifacts: Optional[ArtifactStore] = None,
    ):
        self._source = source
        self._durable = durable
        self._artifacts = artifacts

    # ------------------------------------------------------------------ api

    def verify(self, request: VerificationRequest) -> VerificationResult:
        pc = request.postcondition
        name = self._HANDLERS.get(type(pc))
        if name is None:
            raise TypeError(f"no verifier for postcondition {type(pc).__name__}")
        # Dispatch through the bound method rather than a captured function, so
        # a subclass override is actually used.
        return getattr(self, name)(pc, request)

    # ------------------------------------------------------- shared helpers

    def _fresh(self, page_id: str, request: VerificationRequest) -> ObservationView:
        """Observe now, and refuse anything that is not newer than the decision.

        Raises EvidenceUnavailable so every caller funnels into AMBIGUOUS
        rather than each inventing its own staleness handling.
        """
        obs = self._source.observe(page_id)
        before = request.observation_id_before
        if before and not _advanced(before, obs.observation_id):
            raise EvidenceUnavailable(
                "STALE_OBSERVATION",
                f"observation {obs.observation_id!r} does not post-date the "
                f"pre-action observation {before!r}",
            )
        if obs.page_id != page_id:
            raise EvidenceUnavailable(
                "WRONG_PAGE",
                f"asked for page {page_id!r}, source returned {obs.page_id!r}",
            )
        return obs

    @staticmethod
    def _prov(obs: ObservationView, **extra) -> dict:
        """Compact provenance: enough to re-find the state, not the state."""
        return {
            "observation_id": obs.observation_id,
            "page_id": obs.page_id,
            "url": obs.url,
            "document_token": obs.document_token,
            **extra,
        }

    def _unavailable(
        self, verifier_type: str, exc: EvidenceUnavailable, **evidence
    ) -> VerificationResult:
        reason = (
            Reason.STALE_EVIDENCE
            if exc.cause in ("STALE_OBSERVATION", "OBSERVATION_SUPERSEDED")
            else Reason.EVIDENCE_UNAVAILABLE
        )
        return ambiguous(
            verifier_type,
            reason,
            [Check("evidence", None, detail=f"{exc.cause}: {exc.detail}"[:200])],
            cause=exc.cause,
            detail=exc.detail[:200],
            **evidence,
        )

    # ------------------------------------------------------------ TYPE/FILL

    def _verify_field_value(
        self, pc: FieldValueEquals, request: VerificationRequest
    ) -> VerificationResult:
        vt = "FieldValueEquals"
        try:
            obs = self._fresh(pc.page_id, request)
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        observed, how, err = self._read_field(pc, obs)
        if err is not None:
            if err is Reason.FIELD_NOT_FOUND:
                # The page is observable and the field is not in it. The
                # postcondition is definitively false, not unknowable.
                return not_satisfied(
                    vt,
                    Reason.FIELD_NOT_FOUND,
                    [Check("field_exists", False, expected=pc.target)],
                    **self._prov(obs, target=pc.target),
                )
            return ambiguous(
                vt,
                Reason.FIELD_AMBIGUOUS,
                [Check("field_identity", None, detail=how)],
                **self._prov(obs, target=pc.target, detail=how),
            )

        expected = pc.expected
        actual = observed
        if pc.match is ValueMatch.TRIMMED:
            expected, actual = expected.strip(), actual.strip()
        ok = actual == expected
        check = Check(
            "field_value", ok, expected=expected, observed=actual, detail=how
        )
        prov = self._prov(obs, target=pc.target, resolved_by=how)
        if ok:
            return satisfied(vt, [check], **prov)
        return not_satisfied(vt, Reason.VALUE_MISMATCH, [check], **prov)

    def _read_field(
        self, pc: FieldValueEquals, obs: ObservationView
    ) -> tuple[str, str, Optional[Reason]]:
        """Read the field's live value.

        Order matters. The observed node is tried first because node identity is
        the strongest evidence we have (ADR-012). Semantic relocation is a
        fallback for the legitimate rerender case, and it refuses rather than
        guesses when more than one element matches.
        """
        try:
            return self._source.read_value(pc.target), "target_node", None
        except EvidenceUnavailable:
            pass  # node is gone; fall through to semantic relocation

        name = pc.name
        if name is None:
            return "", "no name available for relocation", Reason.FIELD_AMBIGUOUS

        frame_id = _resolve_frame(obs, pc.frame_id)
        matches = [
            e
            for e in obs.elements
            if (frame_id is None or e.frame_id == frame_id)
            and e.role == pc.role
            and e.name.strip() == name.strip()
        ]
        if not matches:
            return "", "field absent from fresh observation", Reason.FIELD_NOT_FOUND
        if len(matches) > 1:
            return (
                "",
                f"{len(matches)} controls match role={pc.role!r} name={name!r} in "
                f"frame {frame_id}; cannot attribute a value to one of them",
                Reason.FIELD_AMBIGUOUS,
            )
        try:
            return self._source.read_value(matches[0].target), "relocated_unique", None
        except EvidenceUnavailable as exc:
            return "", f"relocated node unreadable: {exc.cause}", Reason.FIELD_AMBIGUOUS

    # --------------------------------------------------------------- SELECT

    def _verify_select_value(
        self, pc: SelectValueEquals, request: VerificationRequest
    ) -> VerificationResult:
        vt = "SelectValueEquals"
        field = FieldValueEquals(
            page_id=pc.page_id,
            target=pc.target,
            expected=pc.expected_value,
            role="combobox",
            name=pc.name,
            frame_id=pc.frame_id,
            match=ValueMatch.EXACT,
        )
        result = self._verify_field_value(field, request)
        # Re-badge so the trace names the postcondition that was declared.
        return VerificationResult(
            result.status, result.reason, vt, result.checks, result.evidence
        )

    # ----------------------------------------------------------- NAVIGATION

    def _verify_url(self, pc: UrlIs, request: VerificationRequest) -> VerificationResult:
        vt = "UrlIs"
        try:
            obs = self._fresh(pc.page_id, request)
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        ok = _text_matches(obs.url, pc.expected, pc.match)
        check = Check("url", ok, expected=pc.expected, observed=obs.url, detail=pc.match.value)
        prov = self._prov(obs)
        if ok:
            return satisfied(vt, [check], **prov)
        return not_satisfied(vt, Reason.URL_MISMATCH, [check], **prov)

    # -------------------------------------------------------------- ELEMENT

    def _verify_element(
        self, pc: ElementPresence, request: VerificationRequest
    ) -> VerificationResult:
        vt = "ElementPresence"
        try:
            obs = self._fresh(pc.page_id, request)
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        # Observation Contract V1: frame ids are minted identities, so they are
        # trusted directly. A detached frame simply has no elements, which makes
        # the postcondition false rather than answerable by another frame.
        frame_id = _resolve_frame(obs, pc.frame_id)
        matches = _find_elements(
            obs,
            role=pc.role,
            name=pc.name,
            frame_id=frame_id,
            section=pc.section,
            require_visible=pc.require_visible,
            group_cells=pc.group_cells,
        )
        present = len(matches) > 0
        ok = present == pc.expect_present
        check = Check(
            "element_presence",
            ok,
            expected=f"{'present' if pc.expect_present else 'absent'} "
                     f"{pc.role}:{pc.name!r} frame={pc.frame_id}",
            observed=f"{len(matches)} match(es)",
        )
        prov = self._prov(
            obs,
            matches=[m.target for m in matches[:5]],
            frame_id=frame_id,
            requested_frame=pc.frame_id,
            matched_frames=sorted({m.frame_id for m in matches}),
            section=pc.section,
            group_cells=pc.group_cells,
        )
        if ok:
            return satisfied(vt, [check], **prov)
        reason = (
            Reason.ELEMENT_MISSING if pc.expect_present
            else Reason.ELEMENT_UNEXPECTEDLY_PRESENT
        )
        return not_satisfied(vt, reason, [check], **prov)

    # ----------------------------------------------------------------- TEXT

    def _verify_text(
        self, pc: TextPresence, request: VerificationRequest
    ) -> VerificationResult:
        vt = "TextPresence"
        try:
            obs = self._fresh(pc.page_id, request)
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        # Observation Contract V1 carries text per frame, so a child frame's
        # text is directly assertable instead of being refused.
        frame_id = _resolve_frame(obs, pc.frame_id)
        hay = [
            b.text for b in obs.text_blocks
            if frame_id is None or b.frame_id == frame_id
        ]
        present = any(_text_matches(block, pc.text, pc.match) for block in hay)
        ok = present == pc.expect_present
        check = Check(
            "text_presence",
            ok,
            expected=f"{'present' if pc.expect_present else 'absent'}: {pc.text!r}",
            observed=f"{len(hay)} text blocks searched; present={present}",
        )
        prov = self._prov(obs, blocks_searched=len(hay), frame_id=frame_id,
                          requested_frame=pc.frame_id)
        if ok:
            return satisfied(vt, [check], **prov)
        reason = (
            Reason.TEXT_MISSING if pc.expect_present
            else Reason.TEXT_UNEXPECTEDLY_PRESENT
        )
        return not_satisfied(vt, reason, [check], **prov)

    # ----------------------------------------------------------------- PAGE

    def _verify_page(
        self, pc: PageState, request: VerificationRequest
    ) -> VerificationResult:
        vt = "PageState"
        try:
            pages: Sequence[PageView] = self._source.list_pages()
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        match: Optional[PageView] = next(
            (p for p in pages if p.page_id == pc.page_id and not p.closed), None
        )
        exists = match is not None
        checks = [
            Check(
                "page_exists",
                exists == pc.expect_exists,
                expected=f"{'exists' if pc.expect_exists else 'absent'}: {pc.page_id}",
                observed="exists" if exists else "absent/closed",
            )
        ]
        if exists != pc.expect_exists:
            reason = (
                Reason.PAGE_MISSING if pc.expect_exists
                else Reason.PAGE_UNEXPECTEDLY_PRESENT
            )
            return not_satisfied(
                vt, reason, checks, page_id=pc.page_id, known_pages=[p.page_id for p in pages]
            )
        if not pc.expect_exists:
            return satisfied(vt, checks, page_id=pc.page_id)

        assert match is not None
        if pc.expect_opener_page_id is not None:
            ok = match.opener_page_id == pc.expect_opener_page_id
            checks.append(
                Check("opener", ok, expected=pc.expect_opener_page_id,
                      observed=match.opener_page_id)
            )
            if not ok:
                return not_satisfied(
                    vt, Reason.PAGE_WRONG_OPENER, checks,
                    page_id=pc.page_id, opener=match.opener_page_id,
                )
        if pc.expect_url is not None:
            ok = _text_matches(match.url, pc.expect_url, pc.url_match)
            checks.append(Check("url", ok, expected=pc.expect_url, observed=match.url))
            if not ok:
                return not_satisfied(
                    vt, Reason.URL_MISMATCH, checks, page_id=pc.page_id, url=match.url
                )
        if pc.expect_active is not None:
            try:
                obs = self._source.observe(pc.page_id)
            except EvidenceUnavailable as exc:
                return self._unavailable(vt, exc, page_id=pc.page_id)
            active = next(
                (t.active for t in obs.tabs if t.page_id == pc.page_id), False
            )
            ok = active == pc.expect_active
            checks.append(Check("active", ok, expected=pc.expect_active, observed=active))
            if not ok:
                return not_satisfied(
                    vt, Reason.PAGE_NOT_ACTIVE, checks, page_id=pc.page_id
                )
        return satisfied(
            vt, checks, page_id=pc.page_id, opener=match.opener_page_id, url=match.url
        )

    # --------------------------------------------------------------- DIALOG

    def _verify_dialog(
        self, pc: DialogState, request: VerificationRequest
    ) -> VerificationResult:
        vt = "DialogState"
        try:
            state = self._source.dialog_state()
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        open_now = state is not None
        if open_now != pc.expect_open:
            reason = (
                Reason.DIALOG_MISSING if pc.expect_open
                else Reason.DIALOG_UNEXPECTEDLY_PRESENT
            )
            return not_satisfied(
                vt,
                reason,
                [Check("dialog_open", False, expected=pc.expect_open, observed=open_now)],
                dialog=_compact_dialog(state),
            )
        if not pc.expect_open:
            return satisfied(
                vt, [Check("dialog_open", True, expected=False, observed=False)]
            )

        assert state is not None
        checks = [Check("dialog_open", True, expected=True, observed=True)]
        raw = " ".join(str(v) for v in state.values())
        if pc.kind is not None:
            observed_kind = str(state.get("type") or state.get("kind") or "")
            ok = observed_kind == pc.kind or pc.kind in raw
            checks.append(Check("dialog_kind", ok, expected=pc.kind, observed=observed_kind or raw[:80]))
            if not ok:
                return not_satisfied(vt, Reason.DIALOG_MISMATCH, checks,
                                     dialog=_compact_dialog(state))
        if pc.message_contains is not None:
            message = str(state.get("message") or raw)
            ok = pc.message_contains in message
            checks.append(
                Check("dialog_message", ok, expected=pc.message_contains, observed=message[:120])
            )
            if not ok:
                return not_satisfied(vt, Reason.DIALOG_MISMATCH, checks,
                                     dialog=_compact_dialog(state))
        return satisfied(vt, checks, dialog=_compact_dialog(state))

    # ------------------------------------------------------------- DOWNLOAD

    def _verify_download(
        self, pc: DownloadPresent, request: VerificationRequest
    ) -> VerificationResult:
        vt = "DownloadPresent"
        if self._artifacts is None:
            return ambiguous(
                vt,
                Reason.EVIDENCE_UNAVAILABLE,
                [Check("artifact_store", None, detail="no artifact store configured")],
                cause="NO_ARTIFACT_STORE",
            )
        try:
            record = self._artifacts.find_artifact(
                artifact_id=pc.artifact_id, filename=pc.filename
            )
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc)

        if record is None:
            return not_satisfied(
                vt,
                Reason.DOWNLOAD_MISSING,
                [Check("artifact", False, expected=pc.artifact_id or pc.filename,
                       observed=None)],
                artifact_id=pc.artifact_id, filename=pc.filename,
            )
        checks = [Check("artifact", True, expected=pc.artifact_id or pc.filename,
                        observed=record.artifact_id)]
        if pc.require_complete and not record.complete:
            checks.append(Check("complete", False, expected=True, observed=False))
            return not_satisfied(vt, Reason.DOWNLOAD_INCOMPLETE, checks,
                                 artifact_id=record.artifact_id)
        if record.size_bytes < pc.min_bytes:
            checks.append(
                Check("size", False, expected=f">={pc.min_bytes}", observed=record.size_bytes)
            )
            return not_satisfied(vt, Reason.DOWNLOAD_INCOMPLETE, checks,
                                 artifact_id=record.artifact_id)
        if pc.filename is not None and record.filename != pc.filename:
            checks.append(Check("filename", False, expected=pc.filename, observed=record.filename))
            return not_satisfied(vt, Reason.DOWNLOAD_MISMATCH, checks,
                                 artifact_id=record.artifact_id)
        if pc.expected_sha256 is not None:
            ok = record.sha256 == pc.expected_sha256
            checks.append(Check("sha256", ok, expected=pc.expected_sha256, observed=record.sha256))
            if not ok:
                return not_satisfied(vt, Reason.DOWNLOAD_MISMATCH, checks,
                                     artifact_id=record.artifact_id)
        return satisfied(
            vt, checks, artifact_id=record.artifact_id, filename=record.filename,
            size_bytes=record.size_bytes,
        )

    # ------------------------------------------------ CONSEQUENTIAL OPERATION

    def _verify_operation(
        self, pc: OperationRecorded, request: VerificationRequest
    ) -> VerificationResult:
        vt = "OperationRecorded"
        if self._durable is None:
            # No way to ask the world. For a consequential action this is
            # exactly the case that must stay AMBIGUOUS (ADR-014).
            return ambiguous(
                vt,
                Reason.EVIDENCE_UNAVAILABLE,
                [Check("durable_channel", None, detail="no durable evidence source")],
                cause="NO_DURABLE_SOURCE",
                operation_id=pc.operation_id,
            )
        try:
            record = self._durable.lookup_operation(pc.operation_id)
        except EvidenceUnavailable as exc:
            return self._unavailable(vt, exc, operation_id=pc.operation_id)

        ok = record.found == pc.expect_recorded
        check = Check(
            "operation_recorded", ok,
            expected=pc.expect_recorded, observed=record.found,
        )
        prov = {
            "operation_id": pc.operation_id,
            "confirmation_ref": record.confirmation_ref,
            "execution_status": request.execution_status,
        }
        if ok:
            return satisfied(vt, [check], **prov)
        reason = (
            Reason.OPERATION_NOT_RECORDED if pc.expect_recorded
            else Reason.OPERATION_RECORDED
        )
        return not_satisfied(vt, reason, [check], **prov)

    # ---------------------------------------------------------- COMPOSITION

    def _verify_all_of(
        self, pc: AllOf, request: VerificationRequest
    ) -> VerificationResult:
        vt = "AllOf"
        results = [
            self.verify(
                VerificationRequest(
                    postcondition=part,
                    observation_id_before=request.observation_id_before,
                    execution_status=request.execution_status,
                    kernel_error=request.kernel_error,
                    intent_id=request.intent_id,
                    action=request.action,
                )
            )
            for part in pc.parts
        ]
        checks = tuple(
            Check(r.verifier_type, r.status is VerificationStatus.SATISFIED,
                  expected="SATISFIED", observed=r.status.value, detail=r.reason.value)
            for r in results
        )
        evidence = {"parts": [r.to_json() for r in results]}
        # A definite failure outranks ambiguity: if any part is definitively
        # false the composite is false regardless of what else is unknown.
        failed = [r for r in results if r.status is VerificationStatus.NOT_SATISFIED]
        if failed:
            return not_satisfied(vt, Reason.COMPOSITE_FAILED, checks, **evidence)
        unknown = [r for r in results if r.status is VerificationStatus.AMBIGUOUS]
        if unknown:
            return ambiguous(vt, Reason.EVIDENCE_UNAVAILABLE, checks, **evidence)
        return satisfied(vt, checks, **evidence)

    #: postcondition type -> method name. Names, not function objects, so that
    #: overriding a handler on a subclass changes dispatch.
    _HANDLERS = {
        FieldValueEquals: "_verify_field_value",
        SelectValueEquals: "_verify_select_value",
        UrlIs: "_verify_url",
        ElementPresence: "_verify_element",
        TextPresence: "_verify_text",
        PageState: "_verify_page",
        DialogState: "_verify_dialog",
        DownloadPresent: "_verify_download",
        OperationRecorded: "_verify_operation",
        AllOf: "_verify_all_of",
    }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _advanced(before: str, after: str) -> bool:
    """Is `after` strictly newer than `before`?

    Observation ids are monotonic per kernel instance (`obs_00042`). When both
    carry a trailing sequence number the comparison is numeric; otherwise the
    weaker "must differ" rule applies, which still rejects replaying the exact
    pre-action observation.
    """
    if before == after:
        return False
    mb, ma = _OBS_SEQ.search(before), _OBS_SEQ.search(after)
    if mb and ma:
        return int(ma.group(1)) > int(mb.group(1))
    return True


def _text_matches(haystack: str, needle: str, mode: TextMatch) -> bool:
    if mode is TextMatch.EXACT:
        return haystack == needle
    if mode is TextMatch.CONTAINS:
        return needle in haystack
    if mode is TextMatch.REGEX:
        return re.search(needle, haystack) is not None
    raise ValueError(f"unknown match mode {mode!r}")


def _resolve_frame(obs: ObservationView, frame_id: Optional[str]) -> Optional[str]:
    """Translate MAIN_FRAME into this page's minted main-frame id.

    `None` means "any frame on this page" and is passed through.
    """
    if frame_id == MAIN_FRAME:
        return getattr(obs, "main_frame_id", "") or None
    return frame_id


def _group_matches(obs: ObservationView, element: ElementView, wanted: dict) -> bool:
    """Is this element inside a row whose cells match every wanted pair?

    This is what lets a postcondition name "the Open button in B. Lindqvist's
    row" rather than one of three identical Open buttons. Comparison is on the
    structured cells, not on a rendered label string.
    """
    gid = getattr(element, "group_id", "")
    if not gid:
        return False
    group = next((g for g in obs.groups if g.group_id == gid), None)
    if group is None:
        return False
    cells = dict(group.cells)
    for key, value in wanted.items():
        found = cells.get(key)
        if found is None:
            # Allow matching on value alone when the caller does not know the
            # header, e.g. an unheadered table.
            if value not in cells.values():
                return False
            continue
        if value not in found:
            return False
    return True


def _find_elements(
    obs: ObservationView,
    *,
    role: str,
    name: str,
    frame_id: Optional[str],
    section: Optional[str],
    require_visible: bool,
    group_cells: Optional[dict] = None,
) -> list[ElementView]:
    out = []
    for e in obs.elements:
        if frame_id is not None and e.frame_id != frame_id:
            continue
        if e.role != role or e.name.strip() != name.strip():
            continue
        if section is not None and (getattr(e, "section", "") or "").strip() != section:
            continue
        if require_visible and not getattr(e, "visible", True):
            continue
        if group_cells is not None and not _group_matches(obs, e, group_cells):
            continue
        out.append(e)
    return out


def _compact_dialog(state) -> Optional[dict]:
    if not state:
        return None
    return {k: str(v)[:120] for k, v in dict(state).items()}
