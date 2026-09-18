"""Unit tests for phase0/schemas/app_capability.py. No real desktop
control - pure dataclass/serialization behavior."""

from __future__ import annotations

from phase0.schemas.app_capability import (
    AppArchitecture,
    AppCapabilityRecord,
    CapabilityState,
    TreeQualityObservations,
)


def _make_record(**overrides) -> AppCapabilityRecord:
    defaults = dict(
        application="Test App",
        bundle_identifier="com.test.app",
        pid=1234,
        architecture=AppArchitecture.COCOA,
        installed=True,
        ax_application_creation=CapabilityState.SUPPORTED,
        window_discovery=CapabilityState.SUPPORTED,
        tree_traversal=CapabilityState.SUPPORTED,
        semantic_read=CapabilityState.SUPPORTED,
        semantic_action_availability=CapabilityState.SUPPORTED,
        semantic_action_verified=CapabilityState.SUPPORTED,
        value_mutation_availability=CapabilityState.SUPPORTED,
        value_mutation_verified=CapabilityState.SUPPORTED,
        background_inspection=CapabilityState.SUPPORTED,
        background_action=CapabilityState.SUPPORTED,
        occluded_inspection=CapabilityState.SUPPORTED,
        occluded_action=CapabilityState.SUPPORTED,
    )
    defaults.update(overrides)
    return AppCapabilityRecord(**defaults)


def test_to_dict_serializes_enum_values_not_enum_objects():
    record = _make_record()
    d = record.to_dict()
    assert d["architecture"] == "cocoa"
    assert d["ax_application_creation"] == "SUPPORTED"
    assert isinstance(d["architecture"], str)


def test_to_dict_includes_tree_quality_and_defaults_to_empty_collections():
    record = _make_record()
    d = record.to_dict()
    assert d["limitations"] == []
    assert d["evidence_references"] == []
    assert d["interference_classifications"] == []
    assert d["tree_quality"] == TreeQualityObservations().to_dict()


def test_tree_quality_to_dict_round_trips_all_fields():
    tq = TreeQualityObservations(
        element_count=42,
        max_depth_observed=5,
        actionable_controls=7,
        elements_with_identifier=3,
        elements_with_meaningful_label=10,
        distinct_roles_seen=6,
        web_content_exposed=True,
        truncated=True,
        notes="hit the node cap",
    )
    d = tq.to_dict()
    assert d == {
        "element_count": 42,
        "max_depth_observed": 5,
        "actionable_controls": 7,
        "elements_with_identifier": 3,
        "elements_with_meaningful_label": 10,
        "distinct_roles_seen": 6,
        "web_content_exposed": True,
        "truncated": True,
        "notes": "hit the node cap",
    }


def test_not_installed_record_uses_not_installed_state_consistently():
    record = _make_record(
        installed=False,
        ax_application_creation=CapabilityState.NOT_INSTALLED,
        window_discovery=CapabilityState.NOT_INSTALLED,
        tree_traversal=CapabilityState.NOT_INSTALLED,
        semantic_read=CapabilityState.NOT_INSTALLED,
        semantic_action_availability=CapabilityState.NOT_INSTALLED,
        semantic_action_verified=CapabilityState.NOT_INSTALLED,
        value_mutation_availability=CapabilityState.NOT_INSTALLED,
        value_mutation_verified=CapabilityState.NOT_INSTALLED,
        background_inspection=CapabilityState.NOT_INSTALLED,
        background_action=CapabilityState.NOT_INSTALLED,
        occluded_inspection=CapabilityState.NOT_INSTALLED,
        occluded_action=CapabilityState.NOT_INSTALLED,
        pid=None,
    )
    d = record.to_dict()
    assert d["installed"] is False
    assert d["pid"] is None
    assert all(
        d[field] == "NOT_INSTALLED"
        for field in (
            "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
            "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
            "value_mutation_verified", "background_inspection", "background_action",
            "occluded_inspection", "occluded_action",
        )
    )


def test_capability_state_values_match_the_spec_defined_vocabulary():
    expected = {
        "SUPPORTED",
        "SUPPORTED_WITH_LIMITATIONS",
        "UNSUPPORTED",
        "BLOCKED_PERMISSION",
        "NOT_INSTALLED",
        "NOT_TESTED_SAFETY",
        "INCONCLUSIVE",
    }
    assert {state.value for state in CapabilityState} == expected
