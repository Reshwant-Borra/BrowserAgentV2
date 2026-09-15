"""Deterministic PolicyEngine.

Sits between the model and the BrowserKernel. It reads the Decision and the
current Observation; it never reads page text as instructions and it has no
model in it. Its guarantee is the one Experiment 8 must establish:

    even if the model is completely fooled by page content, the set of things
    that can actually happen does not grow.

Authority order (END_TO_END_SYSTEM_SPEC section 16):
    system policy > user goal/approval > trusted connector > page content
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from .contracts import (
    ALLOWED_ACTIONS,
    ALLOWED_KINDS,
    Decision,
    TARGETED_ACTIONS,
)


class Verdict(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    REQUIRE_USER = "REQUIRE_USER"


class Reason(str, enum.Enum):
    OK = "OK"
    UNKNOWN_KIND = "UNKNOWN_KIND"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    TARGET_NOT_IN_OBSERVATION = "TARGET_NOT_IN_OBSERVATION"
    TARGET_REQUIRED = "TARGET_REQUIRED"
    TARGET_DISABLED = "TARGET_DISABLED"
    CROSS_ORIGIN_NOT_AUTHORIZED = "CROSS_ORIGIN_NOT_AUTHORIZED"
    SECRET_ENTRY_REQUIRES_USER = "SECRET_ENTRY_REQUIRES_USER"
    CONSEQUENTIAL_REQUIRES_APPROVAL = "CONSEQUENTIAL_REQUIRES_APPROVAL"
    PAGE_NOT_AGENT_OWNED = "PAGE_NOT_AGENT_OWNED"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    MALFORMED_TARGET = "MALFORMED_TARGET"


# Generic high-impact verbs. This is ordinary English, not site knowledge: no
# rule here names a website, and the same list is used for every page.
CONSEQUENTIAL_NAME = re.compile(
    r"\b(delete|remove|erase|destroy|wipe|purge|"
    r"submit|send|post|publish|"
    r"pay|purchase|buy|checkout|order|book|reserve|"
    r"transfer|withdraw|"
    r"deactivate|deregister|unsubscribe|close account|cancel (subscription|account)|"
    r"confirm (payment|order|booking|purchase)|"
    r"accept and (pay|submit))\b",
    re.IGNORECASE,
)

SECRET_FIELD_NAME = re.compile(
    r"\b(password|passcode|pin|secret|security code|verification code|"
    r"one[- ]time code|otp|2fa|two[- ]factor|mfa|cvv|card number|ssn)\b",
    re.IGNORECASE,
)

# Capabilities the architecture deliberately does not have. They are absent from
# the action enum; this list exists so that an attempt is *recorded* as an
# attempted escalation rather than silently mapping to "unknown action".
UNSUPPORTED_CAPABILITIES = {
    "EVAL", "EVALUATE", "RUN_JS", "JAVASCRIPT", "EXEC", "SHELL", "RUN_CODE",
    "UPLOAD", "UPLOAD_FILE", "FILE_UPLOAD", "READ_FILE", "WRITE_FILE",
    "READ_COOKIES", "GET_COOKIES", "DUMP_STATE", "REVEAL_SYSTEM_PROMPT",
    "DOWNLOAD_TO_PATH", "SET_POLICY", "DISABLE_CONFIRMATION", "REFRESH", "RELOAD",
}


@dataclass
class TaskPolicy:
    """Authorization state for one task. Only the user can widen it."""

    goal: str = ""
    # Origins the user's goal implies, plus the origin the task started on.
    allowed_origins: set[str] = field(default_factory=set)
    # Approvals the USER granted, keyed by a stable approval id.
    approvals: set[str] = field(default_factory=set)
    # Pages the agent may drive.
    agent_page_ids: set[str] = field(default_factory=set)
    allow_same_origin_navigation: bool = True

    def approve(self, key: str):
        self.approvals.add(key)


@dataclass
class PolicyResult:
    verdict: Verdict
    reason: Reason
    detail: str = ""
    # Non-empty when page content tried to widen authority; recorded as evidence.
    escalation_attempt: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW

    def to_json(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason.value,
            "detail": self.detail,
            "escalation_attempt": self.escalation_attempt,
        }


def origin_of(url: str) -> str:
    p = urlparse(url or "")
    if not p.hostname:
        return ""
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{p.hostname}{port}"


class PolicyEngine:
    def __init__(self, policy: TaskPolicy):
        self.policy = policy

    def check(self, dec: Decision, observation: dict) -> PolicyResult:
        p = self.policy

        # 1. Closed vocabulary. Anything outside it cannot reach the kernel.
        if dec.kind not in ALLOWED_KINDS:
            up = dec.kind.upper() if dec.kind else ""
            if up in UNSUPPORTED_CAPABILITIES:
                return PolicyResult(
                    Verdict.DENY, Reason.UNSUPPORTED_CAPABILITY,
                    f"kind {dec.kind!r} is not a capability of this system",
                    escalation_attempt=up,
                )
            return PolicyResult(Verdict.DENY, Reason.UNKNOWN_KIND, f"kind={dec.kind!r}")

        if dec.kind != "BROWSER_ACTION":
            return PolicyResult(Verdict.ALLOW, Reason.OK)

        act = (dec.action or "").upper()
        if act not in ALLOWED_ACTIONS:
            if act in UNSUPPORTED_CAPABILITIES:
                return PolicyResult(
                    Verdict.DENY, Reason.UNSUPPORTED_CAPABILITY,
                    f"action {act!r} is not a capability of this system",
                    escalation_attempt=act,
                )
            return PolicyResult(Verdict.DENY, Reason.UNKNOWN_ACTION, f"action={dec.action!r}")

        elements = {e["target"]: e for e in observation.get("elements", [])}

        # 2. Every targeted action must name a target from THIS observation.
        if act in TARGETED_ACTIONS:
            if not dec.target:
                return PolicyResult(Verdict.DENY, Reason.TARGET_REQUIRED, f"{act} needs a target")
            el = elements.get(dec.target)
            if el is None:
                return PolicyResult(
                    Verdict.DENY, Reason.TARGET_NOT_IN_OBSERVATION,
                    f"{dec.target!r} is not in observation "
                    f"{observation.get('observation_id')}",
                )
            if not el.get("enabled", True):
                return PolicyResult(
                    Verdict.DENY, Reason.TARGET_DISABLED,
                    f"{el.get('name')!r} is disabled",
                )

            # 3. Secrets are the human's to enter.
            if act == "TYPE":
                name = f"{el.get('name','')} {el.get('section','')}"
                if SECRET_FIELD_NAME.search(name) or (
                    el.get("attrs", {}).get("type") == "password"
                ):
                    return PolicyResult(
                        Verdict.REQUIRE_USER, Reason.SECRET_ENTRY_REQUIRES_USER,
                        f"{el.get('name')!r} is a secret field",
                    )

            # 4. High-impact controls need recorded user approval.
            if act in ("CLICK", "PRESS"):
                nm = el.get("name", "")
                if CONSEQUENTIAL_NAME.search(nm):
                    key = f"consequential:{nm.strip().lower()}"
                    if key not in p.approvals and "consequential:*" not in p.approvals:
                        return PolicyResult(
                            Verdict.REQUIRE_CONFIRMATION,
                            Reason.CONSEQUENTIAL_REQUIRES_APPROVAL,
                            f"{nm!r} is a high-impact control and has no user approval",
                        )

        # 5. Navigation may not leave the authorized origins.
        if act in ("NAVIGATE", "NEW_TAB"):
            url = str(dec.args.get("url") or "")
            if url:
                o = origin_of(url)
                current = origin_of(observation.get("url", ""))
                ok = o in p.allowed_origins or (
                    p.allow_same_origin_navigation and o and o == current
                )
                if not ok:
                    return PolicyResult(
                        Verdict.DENY, Reason.CROSS_ORIGIN_NOT_AUTHORIZED,
                        f"{o or url!r} is not an authorized origin "
                        f"(allowed={sorted(p.allowed_origins)}, current={current})",
                        escalation_attempt="CROSS_ORIGIN_NAVIGATION",
                    )

        # 6. The agent drives only its own pages.
        if act == "SWITCH_TAB":
            pid = str(dec.args.get("page_id") or "")
            owners = {t["page_id"]: t.get("owner") for t in observation.get("tabs", [])}
            if pid and owners.get(pid) not in (None, "AGENT"):
                return PolicyResult(
                    Verdict.DENY, Reason.PAGE_NOT_AGENT_OWNED,
                    f"page {pid} is {owners.get(pid)}-owned",
                )

        return PolicyResult(Verdict.ALLOW, Reason.OK)
