"""Unit tests for computer_agent.types value semantics (no resolution logic)."""

from __future__ import annotations

from computer_agent.types import (
    DispatchSafety,
    ExecutionRef,
    FreshnessResult,
    GroundingTrace,
    Observation,
    ObservationVersion,
    ResolutionOutcome,
    ResolutionResult,
    TargetCandidate,
    TargetSpec,
    summarize_candidate,
)


def _candidate(adapter_local_id: str = "h-1", version: int = 0, **overrides) -> TargetCandidate:
    ref = ExecutionRef(observation_version=ObservationVersion(version), adapter_local_id=adapter_local_id)
    defaults = dict(role="button", name="Submit", text="Submit", states={"enabled": True, "visible": True}, container="panel")
    defaults.update(overrides)
    return TargetCandidate(execution_ref=ref, **defaults)


def test_target_spec_is_expressible_false_when_empty():
    assert TargetSpec().is_expressible() is False


def test_target_spec_is_expressible_true_with_any_single_constraint():
    assert TargetSpec(role="button").is_expressible() is True
    assert TargetSpec(name="Submit").is_expressible() is True
    assert TargetSpec(text_hint="Sub").is_expressible() is True
    assert TargetSpec(container_hint="panel").is_expressible() is True
    assert TargetSpec(state_constraints={"enabled": True}).is_expressible() is True


def test_target_spec_equality_and_immutability():
    a = TargetSpec(role="button", name="Submit")
    b = TargetSpec(role="button", name="Submit")
    assert a == b
    try:
        a.role = "checkbox"  # type: ignore[misc]
        assert False, "TargetSpec must be frozen"
    except Exception:
        pass


def test_execution_ref_equality_is_by_value_not_identity():
    a = ExecutionRef(observation_version=ObservationVersion(3), adapter_local_id="h-9")
    b = ExecutionRef(observation_version=ObservationVersion(3), adapter_local_id="h-9")
    assert a == b
    assert a is not b


def test_execution_ref_differs_across_observation_versions():
    a = ExecutionRef(observation_version=ObservationVersion(1), adapter_local_id="h-9")
    b = ExecutionRef(observation_version=ObservationVersion(2), adapter_local_id="h-9")
    assert a != b


def test_resolution_result_defaults_are_empty_not_none():
    result = ResolutionResult(outcome=ResolutionOutcome.ABSENT)
    assert result.candidates == ()
    assert result.selected is None
    assert result.reason == ""


def test_summarize_candidate_drops_execution_ref_and_text():
    candidate = _candidate()
    summary = summarize_candidate(candidate)
    assert summary.role == "button"
    assert summary.name == "Submit"
    assert summary.container == "panel"
    assert not hasattr(summary, "execution_ref")


def test_grounding_trace_build_assembles_from_results_only():
    candidate = _candidate()
    observation = Observation(version=ObservationVersion(1), candidates=(candidate,))
    resolution = ResolutionResult(
        outcome=ResolutionOutcome.RESOLVED, candidates=(candidate,), selected=candidate
    )
    freshness = FreshnessResult(
        safe_to_dispatch=True,
        execution_ref=candidate.execution_ref,
        outcome=ResolutionOutcome.RESOLVED,
        reason="unchanged since resolution",
    )
    trace = GroundingTrace.build(
        spec=TargetSpec(role="button", name="Submit"),
        observation=observation,
        resolution=resolution,
        freshness=freshness,
        dispatched=True,
        dispatch_safety=DispatchSafety.CORRECT_TARGET_DISPATCH,
        scenario="unique_target_no_mutation",
        seed=42,
    )
    assert trace.resolution_outcome is ResolutionOutcome.RESOLVED
    assert trace.selected_summary is not None
    assert trace.selected_summary.name == "Submit"
    assert trace.dispatch_safety is DispatchSafety.CORRECT_TARGET_DISPATCH
    assert trace.seed == 42
    assert len(trace.candidate_summaries) == 1
