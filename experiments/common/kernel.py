"""BrowserKernel contract.

Both candidate runtimes in Experiment 1 implement exactly this interface, so the
comparison measures the runtime rather than two different API shapes. Nothing
above this interface may reference Playwright, MCP, or CDP concepts.
"""

from __future__ import annotations

import abc
import enum
from typing import Optional

from .contracts import Observation, PageRecord


class InvalidationPolicy(str, enum.Enum):
    """Candidate observation-invalidation policies measured in Experiment 4.

    The two UNSAFE_* policies are deliberately included as controls. They model
    what an agent does when it re-resolves targets from the page instead of
    binding them to a node. Their job is to show that the safe policies are
    *necessary*, not merely sufficient.
    """

    # Any mutating action supersedes every observation on that page.
    STRICT_SUPERSEDE = "STRICT_SUPERSEDE"
    # A target is valid while its node is connected, its document is unchanged,
    # its frame is attached and its page is open.
    NODE_IDENTITY = "NODE_IDENTITY"
    # CONTROL (unsafe): invalidate only when the URL changes.
    UNSAFE_URL_ONLY = "UNSAFE_URL_ONLY"
    # CONTROL (unsafe): re-resolve the target by role+accessible name each time.
    UNSAFE_NAME_RESOLVE = "UNSAFE_NAME_RESOLVE"


class BrowserKernel(abc.ABC):
    """Deterministic browser mechanics. The model never sees anything below this."""

    name: str = "abstract"

    # lifecycle -------------------------------------------------------------
    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def shutdown(self) -> None: ...

    @abc.abstractmethod
    def health(self) -> dict: ...

    # observation -----------------------------------------------------------
    @abc.abstractmethod
    def observe(self, page_id: Optional[str] = None) -> Observation: ...

    # navigation ------------------------------------------------------------
    @abc.abstractmethod
    def navigate(self, url: str, page_id: Optional[str] = None) -> None: ...

    @abc.abstractmethod
    def back(self, page_id: Optional[str] = None) -> None: ...

    # element actions -------------------------------------------------------
    @abc.abstractmethod
    def click(self, target: str) -> dict: ...

    @abc.abstractmethod
    def type_text(
        self, target: str, text: str, submit: bool = False, slowly: bool = False
    ) -> dict: ...

    @abc.abstractmethod
    def select(self, target: str, value: str) -> dict: ...

    @abc.abstractmethod
    def press(self, target: str, key: str) -> dict: ...

    @abc.abstractmethod
    def read_value(self, target: str) -> str: ...

    # pages -----------------------------------------------------------------
    @abc.abstractmethod
    def list_pages(self) -> list[PageRecord]: ...

    @abc.abstractmethod
    def new_tab(self, url: Optional[str] = None) -> str: ...

    @abc.abstractmethod
    def switch_tab(self, page_id: str) -> None: ...

    @abc.abstractmethod
    def close_agent_tab(self, page_id: str) -> dict: ...

    # dialogs ---------------------------------------------------------------
    @abc.abstractmethod
    def dialog_state(self) -> Optional[dict]: ...

    @abc.abstractmethod
    def handle_dialog(self, accept: bool, prompt_text: str = "") -> dict: ...

    # freshness -------------------------------------------------------------
    @abc.abstractmethod
    def invalidate_all_observations(self, reason: str) -> None:
        """Called at handoff/resume and after reconnect. No prior target survives."""


class KernelCapability(str, enum.Enum):
    """Capability checklist scored in Experiment 1."""

    SEMANTIC_OBSERVATION = "SEMANTIC_OBSERVATION"
    STABLE_TARGET_IDENTITY = "STABLE_TARGET_IDENTITY"
    STALE_TARGET_FAILS_CLOSED = "STALE_TARGET_FAILS_CLOSED"
    EXACT_VALUE_VERIFICATION = "EXACT_VALUE_VERIFICATION"
    FRAME_SCOPED_TARGETS = "FRAME_SCOPED_TARGETS"
    PAGE_IDENTITY_NOT_URL = "PAGE_IDENTITY_NOT_URL"
    PAGE_OWNERSHIP = "PAGE_OWNERSHIP"
    POPUP_CAPTURE = "POPUP_CAPTURE"
    DIALOG_AS_STATE = "DIALOG_AS_STATE"
    TYPED_ERRORS = "TYPED_ERRORS"
    PERSISTENT_PROFILE = "PERSISTENT_PROFILE"
    HANDOFF_RESUME = "HANDOFF_RESUME"
    RESTART_RECOVERY = "RESTART_RECOVERY"
    NO_UNSAFE_TOOLS_REQUIRED = "NO_UNSAFE_TOOLS_REQUIRED"
