"""Fixture A scenario builders: the adversarial cases the M1 campaign runs
against (docs/IMPLEMENTATION_PLAN.md M1, task item 3).

Every scenario constructs a `MutableUIGraph`, derives a `TargetSpec` from
one of its elements' *observable* attributes only (never a `true_id`),
records what resolving that spec against the pre-mutation state ought to
produce (`expected_t0_outcome`, checked by `campaign.run_trial` as an
internal consistency assertion -- not the safety grading itself), and
supplies a `mutate` callable applying the scenario's designated change
before the freshness check / dispatch attempt.

Noise elements are drawn from a vocabulary disjoint from every scenario's
own role/name choices, so randomized noise can never accidentally create
or resolve an unintended duplicate/collision.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from computer_agent.types import ResolutionOutcome, TargetSpec

from .fixture_a import MutableUIGraph

VISIBLE_ENABLED = {"enabled": True, "visible": True}

NOISE_ROLES = ("label", "separator", "icon", "tooltip", "progressbar")
NOISE_NAMES = ("Decoy1", "Decoy2", "Decoy3", "Filler", "Spacer")
NOISE_CONTAINERS = (None, "toolbar", "statusbar")


@dataclass
class TrialSetup:
    scenario: str
    graph: MutableUIGraph
    spec: TargetSpec
    expected_t0_outcome: ResolutionOutcome
    mutate: Callable[[], None]


def _add_noise(graph: MutableUIGraph, rng: random.Random) -> None:
    for _ in range(rng.randint(0, 5)):
        graph.add_element(
            rng.choice(NOISE_ROLES),
            rng.choice(NOISE_NAMES),
            container=rng.choice(NOISE_CONTAINERS),
            enabled=rng.choice([True, False]),
            visible=rng.choice([True, False]),
            bounds=(rng.randint(0, 800), rng.randint(0, 600), rng.randint(10, 100), rng.randint(10, 40)),
        )


def _noop() -> None:
    return None


def unique_target_no_mutation(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel", bounds=(10, 10, 80, 24))
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup("unique_target_no_mutation", graph, spec, ResolutionOutcome.RESOLVED, _noop)


def duplicate_labels_ambiguous_from_start(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel_a")
    graph.add_element("button", "Submit", container="panel_b")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "duplicate_labels_ambiguous_from_start", graph, spec, ResolutionOutcome.AMBIGUOUS, _noop
    )


def same_role_label_diff_container_disambiguated(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel_a")
    graph.add_element("button", "Submit", container="panel_b")
    _add_noise(graph, rng)
    spec = TargetSpec(
        role="button", name="Submit", container_hint="panel_a", state_constraints=VISIBLE_ENABLED
    )
    return TrialSetup(
        "same_role_label_diff_container_disambiguated", graph, spec, ResolutionOutcome.RESOLVED, _noop
    )


def absent_target_from_start(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup("absent_target_from_start", graph, spec, ResolutionOutcome.ABSENT, _noop)


def disabled_target_state_required(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel", enabled=False)
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup("disabled_target_state_required", graph, spec, ResolutionOutcome.ABSENT, _noop)


def disabled_target_state_not_required(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel", enabled=False)
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints={"visible": True})
    return TrialSetup(
        "disabled_target_state_not_required", graph, spec, ResolutionOutcome.RESOLVED, _noop
    )


def hidden_target_state_required(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel", visible=False)
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup("hidden_target_state_required", graph, spec, ResolutionOutcome.ABSENT, _noop)


def hidden_target_state_not_required(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel", visible=False)
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints={"enabled": True})
    return TrialSetup(
        "hidden_target_state_not_required", graph, spec, ResolutionOutcome.RESOLVED, _noop
    )


def target_removed_after_resolution(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "target_removed_after_resolution",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.remove_element(target_id),
    )


def target_replaced_same_semantics_after_resolution(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "target_replaced_same_semantics_after_resolution",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.replace_element(target_id),
    )


def target_replaced_different_semantics_after_resolution(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "target_replaced_different_semantics_after_resolution",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.replace_element(target_id, name="Cancel"),
    )


def controls_reordered_after_resolution(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "controls_reordered_after_resolution",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.reorder(rng),
    )


def ordinal_disambiguation_then_reorder(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(
        role="button", name="Submit", container_hint="panel", state_constraints=VISIBLE_ENABLED, ordinal=1
    )
    return TrialSetup(
        "ordinal_disambiguation_then_reorder",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.reorder(rng),
    )


def geometry_reflow_no_semantic_change(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel", bounds=(10, 10, 80, 24))
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "geometry_reflow_no_semantic_change",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.move(target_id, (400, 300, 80, 24)),
    )


def overlay_inserted_colliding(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "overlay_inserted_colliding",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.add_element("button", "Submit", container="panel"),
    )


def overlay_inserted_noncolliding(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "overlay_inserted_noncolliding",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.add_element("checkbox", "Newsletter", container="panel_overlay"),
    )


def mutation_immediately_before_dispatch_disable(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "mutation_immediately_before_dispatch_disable",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.set_enabled(target_id, False),
    )


def mutation_immediately_before_dispatch_hide(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "mutation_immediately_before_dispatch_hide",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.set_visible(target_id, False),
    )


def unsupported_empty_spec(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    spec = TargetSpec()
    return TrialSetup("unsupported_empty_spec", graph, spec, ResolutionOutcome.UNSUPPORTED, _noop)


def duplicate_labels_introduced_by_mutation(rng: random.Random) -> TrialSetup:
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    graph.add_element("button", "Submit", container="panel")
    _add_noise(graph, rng)
    spec = TargetSpec(role="button", name="Submit", state_constraints=VISIBLE_ENABLED)
    return TrialSetup(
        "duplicate_labels_introduced_by_mutation",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.add_element("button", "Submit", container="panel"),
    )


def container_reassigned_after_resolution(rng: random.Random) -> TrialSetup:
    """Same true_id, but the element's container changes in place (not a
    replace) after resolution -- exercises container_hint re-checking on
    an otherwise-identical element, distinct from the role/name mutations
    every other scenario uses."""
    graph = MutableUIGraph()
    _add_noise(graph, rng)
    target_id = graph.add_element("button", "Submit", container="panel_a")
    graph.add_element("button", "Submit", container="panel_b")  # never matches container_hint
    _add_noise(graph, rng)
    spec = TargetSpec(
        role="button", name="Submit", container_hint="panel_a", state_constraints=VISIBLE_ENABLED
    )
    return TrialSetup(
        "container_reassigned_after_resolution",
        graph,
        spec,
        ResolutionOutcome.RESOLVED,
        lambda: graph.set_container(target_id, "panel_b"),
    )


SCENARIOS: dict[str, Callable[[random.Random], TrialSetup]] = {
    "unique_target_no_mutation": unique_target_no_mutation,
    "duplicate_labels_ambiguous_from_start": duplicate_labels_ambiguous_from_start,
    "same_role_label_diff_container_disambiguated": same_role_label_diff_container_disambiguated,
    "absent_target_from_start": absent_target_from_start,
    "disabled_target_state_required": disabled_target_state_required,
    "disabled_target_state_not_required": disabled_target_state_not_required,
    "hidden_target_state_required": hidden_target_state_required,
    "hidden_target_state_not_required": hidden_target_state_not_required,
    "target_removed_after_resolution": target_removed_after_resolution,
    "target_replaced_same_semantics_after_resolution": target_replaced_same_semantics_after_resolution,
    "target_replaced_different_semantics_after_resolution": (
        target_replaced_different_semantics_after_resolution
    ),
    "controls_reordered_after_resolution": controls_reordered_after_resolution,
    "ordinal_disambiguation_then_reorder": ordinal_disambiguation_then_reorder,
    "geometry_reflow_no_semantic_change": geometry_reflow_no_semantic_change,
    "overlay_inserted_colliding": overlay_inserted_colliding,
    "overlay_inserted_noncolliding": overlay_inserted_noncolliding,
    "mutation_immediately_before_dispatch_disable": mutation_immediately_before_dispatch_disable,
    "mutation_immediately_before_dispatch_hide": mutation_immediately_before_dispatch_hide,
    "unsupported_empty_spec": unsupported_empty_spec,
    "duplicate_labels_introduced_by_mutation": duplicate_labels_introduced_by_mutation,
    "container_reassigned_after_resolution": container_reassigned_after_resolution,
}

SCENARIO_NAMES: tuple[str, ...] = tuple(SCENARIOS)


def build_trial(scenario_name: str, seed: int) -> TrialSetup:
    rng = random.Random(seed)
    return SCENARIOS[scenario_name](rng)
