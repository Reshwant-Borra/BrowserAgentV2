"""Evidence schema for the Mac Application Capability Matrix
(docs/BUILD_SPEC.md section 3's "representative native and custom
applications" requirement).

This is deliberately a *survey*-shaped record, not a per-trial
`ExperimentObservation` (phase0/schemas/evidence.py) - each capability
field here is a considered verdict, not a raw measurement. Per-trial
evidence backing a verdict still goes through the existing
`ExperimentObservation`/`ResultWriter` pipeline; `evidence_references`
below points at those JSONL files.

`CapabilityState` deliberately has more than SUPPORTED/UNSUPPORTED so a
successful AX call is never conflated with a verified capability (see
docs/BUILD_SPEC.md section 3: "Do not mark an AX action
BACKGROUND_PROVEN without measurement" - the same discipline applied
here to app-level capability claims).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class CapabilityState(str, Enum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_LIMITATIONS = "SUPPORTED_WITH_LIMITATIONS"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED_PERMISSION = "BLOCKED_PERMISSION"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_TESTED_SAFETY = "NOT_TESTED_SAFETY"
    INCONCLUSIVE = "INCONCLUSIVE"


class AppArchitecture(str, Enum):
    COCOA = "cocoa"
    SWIFTUI = "swiftui"
    WEBKIT = "webkit"
    CHROMIUM = "chromium"
    ELECTRON = "electron"
    SYSTEM_UI = "system_ui"
    UNKNOWN = "unknown"


@dataclass
class TreeQualityObservations:
    """Bounded structural summary only - never raw AXValue/text content
    from a real application (docs/BUILD_SPEC.md section 5)."""

    element_count: Optional[int] = None
    max_depth_observed: Optional[int] = None
    actionable_controls: Optional[int] = None
    elements_with_identifier: Optional[int] = None
    elements_with_meaningful_label: Optional[int] = None
    distinct_roles_seen: Optional[int] = None
    web_content_exposed: Optional[bool] = None
    truncated: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "element_count": self.element_count,
            "max_depth_observed": self.max_depth_observed,
            "actionable_controls": self.actionable_controls,
            "elements_with_identifier": self.elements_with_identifier,
            "elements_with_meaningful_label": self.elements_with_meaningful_label,
            "distinct_roles_seen": self.distinct_roles_seen,
            "web_content_exposed": self.web_content_exposed,
            "truncated": self.truncated,
            "notes": self.notes,
        }


@dataclass
class AppCapabilityRecord:
    application: str
    bundle_identifier: Optional[str]
    pid: Optional[int]
    architecture: AppArchitecture
    installed: bool

    ax_application_creation: CapabilityState
    window_discovery: CapabilityState
    tree_traversal: CapabilityState
    semantic_read: CapabilityState
    semantic_action_availability: CapabilityState
    semantic_action_verified: CapabilityState
    value_mutation_availability: CapabilityState
    value_mutation_verified: CapabilityState
    background_inspection: CapabilityState
    background_action: CapabilityState
    occluded_inspection: CapabilityState
    occluded_action: CapabilityState

    interference_classifications: List[str] = field(default_factory=list)
    tree_quality: TreeQualityObservations = field(default_factory=TreeQualityObservations)
    limitations: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "application": self.application,
            "bundle_identifier": self.bundle_identifier,
            "pid": self.pid,
            "architecture": self.architecture.value,
            "installed": self.installed,
            "ax_application_creation": self.ax_application_creation.value,
            "window_discovery": self.window_discovery.value,
            "tree_traversal": self.tree_traversal.value,
            "semantic_read": self.semantic_read.value,
            "semantic_action_availability": self.semantic_action_availability.value,
            "semantic_action_verified": self.semantic_action_verified.value,
            "value_mutation_availability": self.value_mutation_availability.value,
            "value_mutation_verified": self.value_mutation_verified.value,
            "background_inspection": self.background_inspection.value,
            "background_action": self.background_action.value,
            "occluded_inspection": self.occluded_inspection.value,
            "occluded_action": self.occluded_action.value,
            "interference_classifications": list(self.interference_classifications),
            "tree_quality": self.tree_quality.to_dict(),
            "limitations": list(self.limitations),
            "evidence_references": list(self.evidence_references),
        }
