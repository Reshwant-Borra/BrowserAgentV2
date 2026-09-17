import pytest

from phase0.schemas.evidence import (
    SCHEMA_VERSION,
    ActionMechanism,
    ActionOutcome,
    EvidenceReference,
    ExperimentObservation,
    InterferenceClassification,
    Measurement,
    Platform,
    SchemaValidationError,
)


def _make_observation(**overrides) -> ExperimentObservation:
    defaults = dict(
        schema_version=SCHEMA_VERSION,
        experiment_id="unit_test_experiment",
        run_id="run-1",
        trial_id="trial-0000",
        timestamp="2026-01-01T00:00:00+00:00",
        platform=Platform.MACOS,
        os_version=Measurement.of("15.0"),
        hardware={"machine": "arm64"},
        action_type="click_button",
        action_mechanism=ActionMechanism.PLAYWRIGHT_SEMANTIC,
        target_application=Measurement.of("chromium"),
        target_process=Measurement.unavailable("not tracked"),
        target_window=Measurement.of("Fixture Page 1"),
        foreground_app_before=Measurement.of({"name": "Terminal"}),
        foreground_app_after=Measurement.of({"name": "Terminal"}),
        focused_window_before=Measurement.of({"title": "w1"}),
        focused_window_after=Measurement.of({"title": "w1"}),
        focused_element_before=Measurement.of({"role": "AXTextArea"}),
        focused_element_after=Measurement.of({"role": "AXTextArea"}),
        cursor_before=Measurement.of({"x": 1.0, "y": 2.0}),
        cursor_after=Measurement.of({"x": 1.0, "y": 2.0}),
        cursor_moved=False,
        foreground_changed=False,
        focus_changed=False,
        action_latency_ms=12.5,
        expected_postcondition="#counter becomes '1'",
        observed_postcondition=Measurement.of({"expected": "1", "observed": "1"}),
        postcondition_success=True,
        action_outcome=ActionOutcome.SUCCESS,
        error=None,
        classification=InterferenceClassification.BACKGROUND_SAFE,
        evidence=[EvidenceReference(kind="log", path="phase0/results/x.log")],
    )
    defaults.update(overrides)
    return ExperimentObservation(**defaults)


def test_round_trip_preserves_all_fields():
    obs = _make_observation()
    data = obs.to_dict()
    restored = ExperimentObservation.from_dict(data)
    assert restored.to_dict() == data


def test_to_dict_uses_plain_json_types():
    obs = _make_observation()
    data = obs.to_dict()
    assert data["platform"] == "macos"
    assert data["action_mechanism"] == "playwright_semantic"
    assert data["classification"] == "BACKGROUND_SAFE"
    assert isinstance(data["evidence"], list)
    assert data["evidence"][0] == {"kind": "log", "path": "phase0/results/x.log", "description": None}


def test_measurement_unavailable_requires_reason():
    with pytest.raises(SchemaValidationError):
        Measurement(available=False, value=None, reason=None)


def test_measurement_unavailable_helper():
    m = Measurement.unavailable("permission denied")
    assert m.available is False
    assert m.reason == "permission denied"
    assert m.to_dict() == {"available": False, "value": None, "reason": "permission denied"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("experiment_id"),
        lambda d: d.pop("cursor_before"),
        lambda d: d.pop("classification"),
    ],
)
def test_from_dict_rejects_missing_required_field(mutate):
    data = _make_observation().to_dict()
    mutate(data)
    with pytest.raises(SchemaValidationError):
        ExperimentObservation.from_dict(data)


def test_from_dict_rejects_bad_enum_value():
    data = _make_observation().to_dict()
    data["classification"] = "NOT_A_REAL_CLASSIFICATION"
    with pytest.raises(SchemaValidationError):
        ExperimentObservation.from_dict(data)


def test_from_dict_rejects_wrong_schema_version():
    data = _make_observation().to_dict()
    data["schema_version"] = "0.0.1"
    with pytest.raises(SchemaValidationError):
        ExperimentObservation.from_dict(data)


def test_from_dict_rejects_non_object():
    with pytest.raises(SchemaValidationError):
        ExperimentObservation.from_dict(["not", "an", "object"])


def test_from_dict_rejects_malformed_measurement():
    data = _make_observation().to_dict()
    data["cursor_before"] = "not-a-measurement-object"
    with pytest.raises(SchemaValidationError):
        ExperimentObservation.from_dict(data)


def test_evidence_reference_round_trip():
    ref = EvidenceReference(kind="screenshot", path="phase0/results/shots/1.png", description="post-click")
    restored = EvidenceReference.from_dict(ref.to_dict())
    assert restored == ref


def test_evidence_reference_missing_field_rejected():
    with pytest.raises(SchemaValidationError):
        EvidenceReference.from_dict({"kind": "screenshot"})
