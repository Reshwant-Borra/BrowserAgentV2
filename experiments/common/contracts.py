"""Canonical experiment contracts shared by every P0 experiment.

These mirror the schemas in 02_ARCHITECTURE/END_TO_END_SYSTEM_SPEC.md section 4.
They are deliberately *experiment* contracts: small, frozen, and reused across
experiments so that no experiment builds its own private mini-project.

Nothing here is production architecture. It is the smallest set of typed
structures needed to make the P0 gates measurable.
"""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --------------------------------------------------------------------------
# Ownership / page registry
# --------------------------------------------------------------------------


class Owner(str, enum.Enum):
    AGENT = "AGENT"
    USER = "USER"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class PageRecord:
    """Identity of a page is the page_id minted at the creation event.

    Never title, never URL, never tab index. `url`/`title` are descriptive
    metadata only and are explicitly NOT part of identity.
    """

    page_id: str
    owner: Owner
    opener_page_id: Optional[str]
    created_event_id: int
    url: str = ""
    title: str = ""
    closed: bool = False
    # Monotonic document generation; bumped on every new document in this page.
    document_generation: int = 0

    def to_json(self) -> dict:
        d = asdict(self)
        d["owner"] = self.owner.value
        return d


# --------------------------------------------------------------------------
# Observation
# --------------------------------------------------------------------------


@dataclass
class ObservedElement:
    target: str  # "<observation_id>:<frame_id>:e<N>"
    role: str
    name: str
    value: str = ""
    frame_id: str = "f0"
    enabled: bool = True
    visible: bool = True
    tag: str = ""
    # Nearest preceding heading. Without it, three identical "Submit" buttons are
    # indistinguishable in the observation and the model can only guess.
    section: str = ""
    # Selectable values for a combobox; empty for every other role.
    options: list[dict] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class TabSummary:
    page_id: str
    url: str
    title: str
    owner: str
    active: bool


@dataclass
class Observation:
    observation_id: str
    page_id: str
    url: str
    title: str
    # Document identity token read from the live page. A new document (navigation,
    # reload, crash-recovery) always produces a new token. This is what makes
    # "same URL, same title, different document" detectable.
    document_token: str
    document_generation: int
    frame_tree_version: int
    tabs: list[TabSummary] = field(default_factory=list)
    modal: Optional[dict] = None
    elements: list[ObservedElement] = field(default_factory=list)
    text_blocks: list[str] = field(default_factory=list)
    change_summary: list[str] = field(default_factory=list)
    state_fingerprint: str = ""

    def target_ids(self) -> list[str]:
        return [e.target for e in self.elements]

    def element(self, target: str) -> Optional[ObservedElement]:
        for e in self.elements:
            if e.target == target:
                return e
        return None

    def compute_fingerprint(self) -> str:
        payload = json.dumps(
            {
                "url": self.url,
                "title": self.title,
                "elements": [
                    (e.role, e.name, e.value, e.frame_id, e.enabled) for e in self.elements
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_json(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "page_id": self.page_id,
            "url": self.url,
            "title": self.title,
            "document_token": self.document_token,
            "document_generation": self.document_generation,
            "frame_tree_version": self.frame_tree_version,
            "tabs": [asdict(t) for t in self.tabs],
            "modal": self.modal,
            "elements": [e.to_json() for e in self.elements],
            "text_blocks": self.text_blocks,
            "change_summary": self.change_summary,
            "state_fingerprint": self.state_fingerprint,
        }


# --------------------------------------------------------------------------
# Decision (model output, canonical semantic form)
# --------------------------------------------------------------------------


class DecisionKind(str, enum.Enum):
    BROWSER_ACTION = "BROWSER_ACTION"
    EXTRACT = "EXTRACT"
    ASK_USER = "ASK_USER"
    REQUEST_CONFIRMATION = "REQUEST_CONFIRMATION"
    REPLAN = "REPLAN"
    FINISH = "FINISH"
    FAIL = "FAIL"


class BrowserAction(str, enum.Enum):
    CLICK = "CLICK"
    TYPE = "TYPE"
    SELECT = "SELECT"
    PRESS = "PRESS"
    SCROLL = "SCROLL"
    NAVIGATE = "NAVIGATE"
    BACK = "BACK"
    SWITCH_TAB = "SWITCH_TAB"
    NEW_TAB = "NEW_TAB"
    WAIT = "WAIT"


ALLOWED_ACTIONS = {a.value for a in BrowserAction}
ALLOWED_KINDS = {k.value for k in DecisionKind}

# Actions that require a target drawn from the current observation.
TARGETED_ACTIONS = {"CLICK", "TYPE", "SELECT", "PRESS"}
# Actions that mutate browser/page/server state.
MUTATING_ACTIONS = {"CLICK", "TYPE", "SELECT", "PRESS", "NAVIGATE", "BACK", "NEW_TAB"}


@dataclass
class Decision:
    """The canonical semantic decision.

    Both candidate model interfaces in Experiment 2 (strict JSON and native
    tool calling) must map onto exactly this structure, so that scoring is
    interface-independent.
    """

    kind: str
    action: Optional[str] = None
    target: Optional[str] = None
    args: dict[str, Any] = field(default_factory=dict)
    subgoal_id: Optional[str] = None
    expected_outcome: Optional[str] = None
    reason_short: str = ""

    def to_json(self) -> dict:
        return asdict(self)

    def semantic_key(self) -> tuple:
        """Comparison key used by the graders."""
        return (self.kind, self.action, self.target, _norm_args(self.args))


def _norm_args(args: dict[str, Any]) -> tuple:
    if not args:
        return ()
    out = []
    for k in sorted(args):
        v = args[k]
        if isinstance(v, str):
            v = v.strip()
        out.append((k, v))
    return tuple(out)


# --------------------------------------------------------------------------
# Action lifecycle (side-effect protocol)
# --------------------------------------------------------------------------


class IntentStatus(str, enum.Enum):
    PREPARED = "PREPARED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    AMBIGUOUS = "AMBIGUOUS"
    ABANDONED = "ABANDONED"


class Risk(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    CONSEQUENTIAL = "CONSEQUENTIAL"


@dataclass
class ActionIntent:
    intent_id: str
    decision_id: str
    action: str
    target: Optional[str]
    risk: str
    idempotence: str  # IDEMPOTENT | NOT_IDEMPOTENT | UNKNOWN
    status: str = IntentStatus.PREPARED.value
    # Durable correlation token written into the request so the server side can
    # be interrogated after a crash. This is what makes ambiguity resolvable.
    operation_id: Optional[str] = None
    payload: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


class ExecutionStatus(str, enum.Enum):
    OK = "OK"
    KERNEL_ERROR = "KERNEL_ERROR"
    TIMEOUT = "TIMEOUT"
    DISCONNECTED = "DISCONNECTED"
    REJECTED_STALE_TARGET = "REJECTED_STALE_TARGET"
    REJECTED_POLICY = "REJECTED_POLICY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ActionResult:
    intent_id: str
    execution_status: str
    kernel_error: Optional[str] = None
    new_page_ids: list[str] = field(default_factory=list)
    download_artifact_ids: list[str] = field(default_factory=list)
    dialog: Optional[dict] = None
    observation_id_after: Optional[str] = None

    def to_json(self) -> dict:
        return asdict(self)


class VerificationStatus(str, enum.Enum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class VerificationResult:
    status: str
    checks: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    confidence: str = "deterministic"

    def to_json(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Typed kernel errors
# --------------------------------------------------------------------------


class KernelErrorCode(str, enum.Enum):
    TARGET_STALE = "TARGET_STALE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_NOT_ACTIONABLE = "TARGET_NOT_ACTIONABLE"
    TARGET_DISABLED = "TARGET_DISABLED"
    OBSERVATION_SUPERSEDED = "OBSERVATION_SUPERSEDED"
    DOCUMENT_CHANGED = "DOCUMENT_CHANGED"
    FRAME_DETACHED = "FRAME_DETACHED"
    PAGE_CLOSED = "PAGE_CLOSED"
    PAGE_NOT_OWNED = "PAGE_NOT_OWNED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    DIALOG_BLOCKING = "DIALOG_BLOCKING"
    HYDRATION_RESET = "HYDRATION_RESET"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    UNSUPPORTED = "UNSUPPORTED"
    DISCONNECTED = "DISCONNECTED"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"


class KernelError(Exception):
    def __init__(self, code: KernelErrorCode, message: str = "", detail: dict | None = None):
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_json(self) -> dict:
        return {"code": self.code.value, "message": self.message, "detail": self.detail}
