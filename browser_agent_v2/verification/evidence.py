"""Evidence sources for the Verifier.

The Verifier does not import the BrowserKernel. It consumes the narrow,
structurally-typed views below, so production verification code has no
dependency on `experiments/`, on Playwright, or on any benchmark artefact.

The `KernelEvidenceSource` adapter is the single place where a kernel's
exceptions are translated into `EvidenceUnavailable`. That keeps the Verifier
itself free of broad `except Exception` handlers: it catches exactly one
declared error type, and unexpected failures propagate instead of being
silently downgraded to AMBIGUOUS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


class EvidenceUnavailable(Exception):
    """Fresh state could not be obtained.

    This is the *only* exception the Verifier treats as "insufficient evidence".
    It must carry why, because AMBIGUOUS without a cause is indistinguishable
    from a bug.
    """

    def __init__(self, cause: str, detail: str = ""):
        super().__init__(f"{cause}: {detail}" if detail else cause)
        self.cause = cause
        self.detail = detail


# ---------------------------------------------------------------------------
# Structural views. The experiment kernel's dataclasses satisfy these already;
# nothing needs to subclass anything.
# ---------------------------------------------------------------------------


@runtime_checkable
class ElementView(Protocol):
    target: str
    role: str
    name: str
    value: str
    frame_id: str
    enabled: bool
    visible: bool
    section: str


@runtime_checkable
class TabView(Protocol):
    page_id: str
    url: str
    title: str
    owner: str
    active: bool


@runtime_checkable
class ObservationView(Protocol):
    observation_id: str
    page_id: str
    url: str
    title: str
    document_token: str
    elements: Sequence[ElementView]
    text_blocks: Sequence[str]
    tabs: Sequence[TabView]


@runtime_checkable
class PageView(Protocol):
    page_id: str
    owner: Any
    opener_page_id: Optional[str]
    url: str
    title: str
    closed: bool


class EvidenceSource(Protocol):
    """The minimum a Verifier needs to establish what is actually true now."""

    def observe(self, page_id: Optional[str] = None) -> ObservationView: ...

    def read_value(self, target: str) -> str: ...

    def list_pages(self) -> Sequence[PageView]: ...

    def dialog_state(self) -> Optional[Mapping[str, Any]]: ...


# ---------------------------------------------------------------------------
# Durable / out-of-browser evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    found: bool
    confirmation_ref: Optional[str] = None
    detail: Mapping[str, Any] = None  # type: ignore[assignment]


class DurableEvidenceSource(Protocol):
    """Ground truth for consequential operations, outside the browser.

    Raises `EvidenceUnavailable` when the channel cannot be reached — which is
    exactly the case that must become AMBIGUOUS rather than a guess.
    """

    def lookup_operation(self, operation_id: str) -> OperationRecord: ...


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    filename: str
    size_bytes: int
    complete: bool
    sha256: Optional[str] = None
    source_url: Optional[str] = None


class ArtifactStore(Protocol):
    def find_artifact(
        self, *, artifact_id: Optional[str] = None, filename: Optional[str] = None
    ) -> Optional[ArtifactRecord]: ...


# ---------------------------------------------------------------------------
# Kernel adapter
# ---------------------------------------------------------------------------


class KernelEvidenceSource:
    """Adapts any BrowserKernel-shaped object to `EvidenceSource`.

    Translates kernel exceptions into `EvidenceUnavailable`, preserving the
    typed error code where the kernel provides one. A stale-target refusal
    becomes unavailable *evidence about that node* — not a false negative about
    the postcondition, which the Verifier decides separately.
    """

    def __init__(self, kernel: Any):
        self._kernel = kernel

    # -- reads -------------------------------------------------------------

    def observe(self, page_id: Optional[str] = None) -> ObservationView:
        try:
            return self._kernel.observe(page_id)
        except Exception as exc:  # single translation boundary, never silent
            raise EvidenceUnavailable(_code_of(exc), str(exc)[:300]) from exc

    def read_value(self, target: str) -> str:
        try:
            return self._kernel.read_value(target)
        except Exception as exc:
            raise EvidenceUnavailable(_code_of(exc), str(exc)[:300]) from exc

    def list_pages(self) -> Sequence[PageView]:
        try:
            return self._kernel.list_pages()
        except Exception as exc:
            raise EvidenceUnavailable(_code_of(exc), str(exc)[:300]) from exc

    def dialog_state(self) -> Optional[Mapping[str, Any]]:
        try:
            return self._kernel.dialog_state()
        except Exception as exc:
            raise EvidenceUnavailable(_code_of(exc), str(exc)[:300]) from exc


def _code_of(exc: Exception) -> str:
    """Prefer the kernel's typed error code over the Python exception name."""
    code = getattr(exc, "code", None)
    value = getattr(code, "value", None)
    if isinstance(value, str):
        return value
    if isinstance(code, str):
        return code
    return type(exc).__name__
