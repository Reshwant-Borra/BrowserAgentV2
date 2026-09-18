"""Fixture A: a deterministic, pure-Python mutable UI graph for falsifying
the M1 grounding/freshness contract (docs/IMPLEMENTATION_PLAN.md M1,
research/overnight-2026-09-18's VERTICAL_SLICE_BUILD_SPEC.md "Fixture A").

Every fixture element carries a hidden `true_id`. Production resolution
code (`computer_agent.grounding`) never sees it -- `observe()` only ever
exposes role/name/text/container/state/bounds plus a fresh, observation-
local opaque handle. `true_id` exists purely so the campaign harness
(`tests/computer_agent/campaign.py`) can grade whether a dispatch hit the
objectively correct element, independent of whatever `resolve()` itself
concluded. Feeding `true_id` into a `TargetSpec` anywhere would make that
grading circular -- nothing in this module or `scenarios.py` does that.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from computer_agent.types import (
    ExecutionRef,
    Observation,
    ObservationVersion,
    TargetCandidate,
)

Bounds = tuple[int, int, int, int]


@dataclass
class FixtureElement:
    """Ground-truth element state. Mutable; only ever touched by MutableUIGraph."""

    true_id: str
    role: str
    name: str
    text: str
    container: str | None = None
    enabled: bool = True
    visible: bool = True
    bounds: Bounds = (0, 0, 10, 10)


@dataclass(frozen=True)
class DispatchAttempt:
    """Result of the fake dispatch operation -- test-only, not production."""

    is_stale: bool
    touched_true_id: str | None


class MutableUIGraph:
    """One mutable synthetic UI. `version` bumps on every mutation.

    `observe()` mints fresh, observation-local opaque handles every call
    -- even calling it twice in a row with no mutation between produces
    two different `ExecutionRef.adapter_local_id` values, because a real
    adapter re-observing a live UI would do the same (a fresh DOM/AX/UIA
    snapshot, not a cached one). `dispatch()` resolves a handle back to a
    `true_id` using history recorded at `observe()` time, so grading can
    tell exactly which element a dispatch touched regardless of whether
    the ref used was stale.
    """

    def __init__(self) -> None:
        self.version = 0
        self._elements: list[FixtureElement] = []
        self._next_id = itertools.count(1)
        self._next_handle = itertools.count(1)
        # (observation_version_sequence, adapter_local_id) -> true_id
        self._handle_history: dict[tuple[int, str], str] = {}

    # -- construction / mutation -------------------------------------------------

    def add_element(
        self,
        role: str,
        name: str,
        text: str = "",
        *,
        container: str | None = None,
        enabled: bool = True,
        visible: bool = True,
        bounds: Bounds = (0, 0, 10, 10),
    ) -> str:
        true_id = f"el-{next(self._next_id)}"
        self._elements.append(
            FixtureElement(true_id, role, name, text or name, container, enabled, visible, bounds)
        )
        self.version += 1
        return true_id

    def remove_element(self, true_id: str) -> None:
        self._elements = [e for e in self._elements if e.true_id != true_id]
        self.version += 1

    def replace_element(
        self,
        true_id: str,
        *,
        role: str | None = None,
        name: str | None = None,
        text: str | None = None,
        container: str | None = ...,
        enabled: bool | None = None,
        visible: bool | None = None,
    ) -> str:
        """Remove `true_id` and insert a brand-new element (new true_id) at the
        same position. `container=...` (the sentinel default) means "keep the
        old container"; pass `container=None` explicitly to clear it."""
        idx = next(i for i, e in enumerate(self._elements) if e.true_id == true_id)
        old = self._elements[idx]
        new_true_id = f"el-{next(self._next_id)}"
        new_element = FixtureElement(
            true_id=new_true_id,
            role=role if role is not None else old.role,
            name=name if name is not None else old.name,
            text=text if text is not None else old.text,
            container=old.container if container is ... else container,
            enabled=old.enabled if enabled is None else enabled,
            visible=old.visible if visible is None else visible,
            bounds=old.bounds,
        )
        self._elements[idx] = new_element
        self.version += 1
        return new_true_id

    def reorder(self, rng) -> None:
        rng.shuffle(self._elements)
        self.version += 1

    def set_enabled(self, true_id: str, enabled: bool) -> None:
        self._element(true_id).enabled = enabled
        self.version += 1

    def set_visible(self, true_id: str, visible: bool) -> None:
        self._element(true_id).visible = visible
        self.version += 1

    def set_container(self, true_id: str, container: str | None) -> None:
        self._element(true_id).container = container
        self.version += 1

    def move(self, true_id: str, bounds: Bounds) -> None:
        self._element(true_id).bounds = bounds
        self.version += 1

    def _element(self, true_id: str) -> FixtureElement:
        return next(e for e in self._elements if e.true_id == true_id)

    # -- observation / dispatch ---------------------------------------------------

    def observe(self) -> Observation:
        version = ObservationVersion(self.version)
        candidates = []
        for element in self._elements:
            adapter_local_id = f"h-{next(self._next_handle)}"
            self._handle_history[(version.sequence, adapter_local_id)] = element.true_id
            ref = ExecutionRef(observation_version=version, adapter_local_id=adapter_local_id)
            candidates.append(
                TargetCandidate(
                    execution_ref=ref,
                    role=element.role,
                    name=element.name,
                    text=element.text,
                    states={"enabled": element.enabled, "visible": element.visible},
                    container=element.container,
                    bounds=element.bounds,
                    provenance={"source": "fixture_a"},
                )
            )
        return Observation(version=version, candidates=tuple(candidates))

    def dispatch(self, ref: ExecutionRef) -> DispatchAttempt:
        """Fake dispatch: pure recording, never mutates fixture state."""
        is_stale = ref.observation_version.sequence != self.version
        touched = self._handle_history.get((ref.observation_version.sequence, ref.adapter_local_id))
        return DispatchAttempt(is_stale=is_stale, touched_true_id=touched)

    def elements_snapshot(self) -> list[FixtureElement]:
        """Ground truth for the grading oracle only -- never for production resolution."""
        return list(self._elements)
