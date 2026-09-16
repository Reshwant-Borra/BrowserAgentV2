"""Test harness for the Verifier gate.

Strictly: intent -> browser action -> fresh state -> verifier.

It does NOT call a model, plan, retry, replan, or execute arbitrary tasks. It is
a Verifier harness, not BrowserAgent. The only reason it exists is that
verification cannot be tested without something to verify.

The BrowserKernel and fixture server come from `experiments/common/` because
Experiment 1 adopted that kernel; production verification code never imports
them, only this test harness does.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from browser_agent_v2.verification import (  # noqa: E402
    ArtifactRecord,
    EvidenceUnavailable,
    KernelEvidenceSource,
    OperationRecord,
    VerificationRequest,
    Verifier,
)
from experiments.common.fixture_server import FixtureCluster  # noqa: E402
from experiments.common.kernel_direct import DirectPlaywrightKernel  # noqa: E402


# --------------------------------------------------------------------------
# durable + artifact evidence (test-side implementations of production
# protocols; a real ArtifactStore is a later gate, not this one)
# --------------------------------------------------------------------------


class FixtureDurableEvidence:
    """Asks the fixture server whether an operation actually landed."""

    def __init__(self, origin: str, reachable: bool = True):
        self.origin = origin
        self.reachable = reachable

    def lookup_operation(self, operation_id: str) -> OperationRecord:
        if not self.reachable:
            raise EvidenceUnavailable(
                "DURABLE_CHANNEL_DOWN", f"cannot reach {self.origin}"
            )
        try:
            with urllib.request.urlopen(
                f"{self.origin}/api/op?operation_id={operation_id}", timeout=10
            ) as r:
                data = json.loads(r.read())
        except Exception as exc:
            raise EvidenceUnavailable("DURABLE_LOOKUP_FAILED", str(exc)[:200]) from exc
        return OperationRecord(
            operation_id=operation_id,
            found=bool(data.get("found")),
            confirmation_ref=(
                str(data["confirmation_seq"]) if data.get("confirmation_seq") else None
            ),
            detail={"kind": data.get("kind")},
        )


class RecordingArtifactStore:
    """Captures Playwright download events into a temp directory.

    Deliberately minimal. Downloads are P1 and untested in the P0 freeze, so
    this exists to exercise the Verifier's download evaluator against real
    download evidence, not to be the production ArtifactStore.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ArtifactRecord] = {}
        self.unreachable = False

    def capture(self, page: Any, action: Callable[[], Any], timeout_ms: int = 10_000):
        """Run `action` and record the download it produces, deterministically.

        Playwright's sync API only dispatches events while inside a Playwright
        call, so a `page.on("download", ...)` handler fires at an unpredictable
        later moment — in practice, during the *next* test. `expect_download`
        is the synchronisation point the API actually provides.

        Returns the ArtifactRecord, or None if no download arrived in time.
        """
        try:
            with page.expect_download(timeout=timeout_ms) as info:
                action()
            download = info.value
        except Exception:
            action_already_ran = True  # noqa: F841 - documents the timeout path
            return None
        name = download.suggested_filename
        dest = self.directory / name
        try:
            download.save_as(str(dest))
            complete = True
        except Exception:
            complete = False
        size = dest.stat().st_size if dest.exists() else 0
        aid = f"artifact_{len(self._records) + 1}"
        rec = ArtifactRecord(
            artifact_id=aid, filename=name, size_bytes=size,
            complete=complete, source_url=download.url,
        )
        self._records[aid] = rec
        return rec

    def add_synthetic(self, **kw) -> ArtifactRecord:
        """Inject a record directly, for incomplete/wrong-file negative controls."""
        aid = kw.pop("artifact_id", f"artifact_{len(self._records) + 1}")
        rec = ArtifactRecord(artifact_id=aid, **kw)
        self._records[aid] = rec
        return rec

    def find_artifact(
        self, *, artifact_id: Optional[str] = None, filename: Optional[str] = None
    ) -> Optional[ArtifactRecord]:
        if self.unreachable:
            raise EvidenceUnavailable("ARTIFACT_STORE_DOWN", str(self.directory))
        if artifact_id is not None:
            return self._records.get(artifact_id)
        if filename is not None:
            for r in self._records.values():
                if r.filename == filename:
                    return r
        return None

    def reset(self) -> None:
        self._records.clear()


# --------------------------------------------------------------------------
# adversarial evidence sources (negative controls)
# --------------------------------------------------------------------------


class FrozenEvidenceSource:
    """Replays one captured observation forever.

    Models the exact mistake the Verifier must refuse: verifying a
    state-changing action against the pre-action snapshot. The Verifier is
    expected to notice that the observation does not post-date the action.
    """

    def __init__(self, observation: Any, inner: Any):
        self._obs = observation
        self._inner = inner

    def observe(self, page_id: Optional[str] = None):
        return self._obs

    def read_value(self, target: str) -> str:
        return self._inner.read_value(target)

    def list_pages(self):
        return self._inner.list_pages()

    def dialog_state(self):
        return self._inner.dialog_state()


class BrokenEvidenceSource:
    """Every read fails. Proves unavailable evidence becomes AMBIGUOUS."""

    def __init__(self, cause: str = "DISCONNECTED"):
        self.cause = cause

    def _fail(self, *_a, **_k):
        raise EvidenceUnavailable(self.cause, "evidence source is down")

    observe = read_value = list_pages = dialog_state = _fail


# --------------------------------------------------------------------------
# the harness
# --------------------------------------------------------------------------


@dataclass
class ActedStep:
    """One intent -> action -> fresh-state cycle."""

    observation_before: Any
    execution_status: str
    kernel_error: Optional[str]
    new_page_ids: Sequence[str]


class VerifierHarness:
    def __init__(self, port_base: int = 8899, headless: bool = True):
        self._db = tempfile.mktemp(suffix=".sqlite")
        self.cluster = FixtureCluster(self._db, primary=port_base,
                                      secondary=port_base + 1).start()
        self._profile = tempfile.mkdtemp(prefix="bav2verify_")
        self.kernel = DirectPlaywrightKernel(self._profile, headless=headless)
        self.kernel.start()
        self.source = KernelEvidenceSource(self.kernel)
        self.downloads = RecordingArtifactStore(
            Path(tempfile.mkdtemp(prefix="bav2dl_"))
        )
        self.durable = FixtureDurableEvidence(self.cluster.primary_origin)
        self.verifier = Verifier(
            self.source, durable=self.durable, artifacts=self.downloads
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        try:
            self.kernel.shutdown()
        finally:
            self.cluster.stop()
            shutil.rmtree(self._profile, ignore_errors=True)
            shutil.rmtree(self.downloads.directory, ignore_errors=True)

    def url(self, path: str) -> str:
        return self.cluster.url(path)

    # -- navigation / observation -----------------------------------------

    def goto(self, path: str, page_id: Optional[str] = None):
        self.kernel.navigate(self.url(path), page_id)
        return self.kernel.observe(page_id)

    def observe(self, page_id: Optional[str] = None):
        return self.kernel.observe(page_id)

    def find(self, obs, *, role=None, name=None, contains=None, section=None,
             frame_id=None, nth=0):
        hits = []
        for e in obs.elements:
            if role and e.role != role:
                continue
            if name is not None and e.name.strip() != name:
                continue
            if contains and contains.lower() not in e.name.lower():
                continue
            if section is not None and (e.section or "").strip() != section:
                continue
            if frame_id is not None and e.frame_id != frame_id:
                continue
            hits.append(e)
        if len(hits) <= nth:
            available = [(e.role, e.name, e.section, e.frame_id) for e in obs.elements]
            raise LookupError(
                f"no element role={role} name={name!r} contains={contains!r} "
                f"section={section!r} frame={frame_id} nth={nth}; available={available[:25]}"
            )
        return hits[nth]

    # -- act ---------------------------------------------------------------

    def act(self, observation_before, action: Callable[[], Any]) -> ActedStep:
        """Run one browser action. Never retries, never inspects the result."""
        status, err, before_pages = "OK", None, {
            p.page_id for p in self.kernel.list_pages() if not p.closed
        }
        try:
            action()
        except Exception as exc:
            status = "KERNEL_ERROR"
            code = getattr(exc, "code", None)
            err = getattr(code, "value", None) or type(exc).__name__
        after_pages = {p.page_id for p in self.kernel.list_pages() if not p.closed}
        return ActedStep(
            observation_before=observation_before,
            execution_status=status,
            kernel_error=err,
            new_page_ids=sorted(after_pages - before_pages),
        )

    # -- verify ------------------------------------------------------------

    def verify(self, step: ActedStep, postcondition, *, verifier: Optional[Verifier] = None):
        request = VerificationRequest(
            postcondition=postcondition,
            observation_id_before=(
                step.observation_before.observation_id if step.observation_before else None
            ),
            execution_status=step.execution_status,
            kernel_error=step.kernel_error,
            intent_id="intent_test",
        )
        return (verifier or self.verifier).verify(request)

    def act_expecting_page(self, observation_before, action) -> ActedStep:
        """Run an action that opens a page, waiting on the page event.

        A fixed sleep is not a bound on when the browser delivers a new page;
        `expect_page` is the synchronisation the API actually provides.
        """
        before = {p.page_id for p in self.kernel.list_pages() if not p.closed}
        status, err = "OK", None
        try:
            with self.kernel.context.expect_page(timeout=10_000):
                action()
        except Exception as exc:
            status = "KERNEL_ERROR"
            code = getattr(exc, "code", None)
            err = getattr(code, "value", None) or type(exc).__name__
        after = {p.page_id for p in self.kernel.list_pages() if not p.closed}
        return ActedStep(
            observation_before=observation_before,
            execution_status=status,
            kernel_error=err,
            new_page_ids=sorted(after - before),
        )

    def act_and_verify(self, observation_before, action, postcondition, *,
                       verifier: Optional[Verifier] = None):
        step = self.act(observation_before, action)
        return self.verify(step, postcondition, verifier=verifier), step

    # -- durable side-effect helper ---------------------------------------

    def effects(self) -> list[str]:
        with urllib.request.urlopen(
            self.url("/api/pagefx/log"), timeout=10
        ) as r:
            return [
                e["name"] for e in json.loads(r.read())["entries"]
                if not e["name"].startswith("VALUE:")
            ]

    def reset_effects(self) -> None:
        urllib.request.urlopen(self.url("/api/pagefx/reset"), timeout=10).read()
