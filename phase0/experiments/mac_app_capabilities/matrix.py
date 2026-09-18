"""Mac Application Capability Matrix.

Breadth experiment (docs/BUILD_SPEC.md section 3's "representative
native and custom applications" requirement): determine, per
representative real macOS application, how much of AXUIElement's
semantic surface (discovery, read, action, value mutation, background
operation, occlusion tolerance) actually works - not a 500-trial
reliability campaign, a capability survey.

This reuses the existing measurement pipeline unmodified:
`ExperimentRunner` / `ActionSpec` / `MacObserver` / `classify_interference`
/ `ResultWriter` (phase0/harness/*) and `_reactivate_and_wait` /
`launch_overlay` (already used by the browser/AX campaigns). It adds
*what* is exercised per application and how the resulting
`ExperimentObservation`s are rolled up into an `AppCapabilityRecord`
(phase0/schemas/app_capability.py); it does not change how interference
is measured.

Safety posture: see phase0/experiments/mac_app_capabilities/targets.py.
Only the Cocoa AX fixture and disposable Safari/Chrome/VS Code scratch
windows/pages get verified action/value-mutation trials. Finder, Notes,
Calendar, and System Settings only ever get read-only discovery/tree
inspection and a non-mutating "read is stable" background/occlusion
probe - `semantic_action_verified` and `value_mutation_verified` are
recorded `NOT_TESTED_SAFETY` for those four, per this milestone's
instruction to prefer that over forcing an unsafe test.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from phase0.experiments.macos_ax import ax_elements
from phase0.experiments.macos_ax.experiment import _get_frontmost_pid, _reactivate_and_wait
from phase0.experiments.macos_ax.fixture_process import FixtureLaunchError, launch_fixture
from phase0.experiments.mac_app_capabilities import ax_introspection as axi
from phase0.experiments.mac_app_capabilities import targets as targets_mod
from phase0.experiments.mac_app_capabilities.targets import ResolvedTarget, TargetUnavailable
from phase0.experiments.overlay_process import OverlayLaunchError, launch_overlay
from phase0.fixtures.mac_ax_fixture_app import WINDOW_TITLE as FIXTURE_WINDOW_TITLE
from phase0.harness.observers_macos import (
    MacObserver,
    accessibility_trusted,
    is_macos,
    pyobjc_available,
    warm_up_ax_focus_tree,
)
from phase0.harness.persistence import ResultWriter, read_results, summarize, write_summary
from phase0.harness.runner import ActionSpec, ExperimentRunner
from phase0.schemas.app_capability import AppArchitecture, AppCapabilityRecord, CapabilityState, TreeQualityObservations
from phase0.schemas.evidence import ActionMechanism, ExperimentObservation, InterferenceClassification, Measurement

try:
    import AppKit

    _APPKIT_AVAILABLE = True
except Exception:  # pragma: no cover - non-macOS
    AppKit = None  # type: ignore[assignment]
    _APPKIT_AVAILABLE = False

EXPERIMENT_ID = "mac_app_capabilities"
BACKGROUND_OCCLUSION_TRIALS = 3
FIXTURE_PAGE_TITLE = "Phase0 Fixture Page 1"


class MatrixBlocked(RuntimeError):
    """Raised when the whole matrix cannot run at all (no macOS, no
    pyobjc, no Accessibility permission). Individual per-app failures
    never raise this - they become BLOCKED_PERMISSION/NOT_INSTALLED
    records instead."""


_ALL_CAPABILITY_FIELDS = (
    "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
    "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
    "value_mutation_verified", "background_inspection", "background_action",
    "occluded_inspection", "occluded_action",
)


def _mark_remaining(record: AppCapabilityRecord, state: CapabilityState, *field_names: str) -> None:
    """Sets specific not-yet-decided fields to `state`. Used at an early
    return so an app that IS installed/reachable never keeps the
    `_base_record` NOT_INSTALLED placeholder on fields the probe simply
    didn't get to - that would misreport a real capability gap as a
    missing application."""
    for name in field_names:
        setattr(record, name, state)


def _close_window_via_ax(window) -> bool:
    close_button = axi.find_descendant(
        window,
        lambda e: axi.copy_attr(e, "AXRole")[0] == "AXButton" and axi.copy_attr(e, "AXSubrole")[0] == "AXCloseButton",
        max_depth=4,
    )
    if close_button is None:
        return False
    return axi.perform_action(close_button, "AXPress") == 0


def _quit_if_launched(bundle_id: str, resolved: ResolvedTarget) -> None:
    if not resolved.launched_by_probe or not _APPKIT_AVAILABLE:
        return
    apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    for app in apps:
        app.terminate()


def _aggregate_capability(
    observations: List[ExperimentObservation],
    *,
    require_postcondition: bool = True,
) -> Tuple[CapabilityState, List[str]]:
    """Rolls up repeated trials into one considered verdict, never
    upgrading to SUPPORTED from partial/unmeasured data (same discipline
    as phase0/harness/classification.py's own precedence rules)."""
    notes: List[str] = []
    if not observations:
        return CapabilityState.INCONCLUSIVE, ["no trials were run"]

    if all(o.classification == InterferenceClassification.UNSUPPORTED for o in observations):
        return CapabilityState.UNSUPPORTED, notes

    if any(o.classification == InterferenceClassification.ERROR for o in observations):
        notes.append("at least one trial errored before interference could be measured")
        return CapabilityState.INCONCLUSIVE, notes

    if require_postcondition:
        # A postcondition that definitively failed (False) is a known
        # capability gap - the action/mutation ran without error but did
        # not do what it claims - distinct from one that was simply
        # never measured (None), which is genuinely unknown. Conflating
        # the two would hide a real "doesn't work" finding behind
        # INCONCLUSIVE (observed directly: Chrome's AXPress on a plain
        # HTML button returns success but never fires the click
        # handler, while the identical trial on Safari does).
        if any(o.postcondition_success is False for o in observations):
            notes.append("action/mutation executed without error but the expected postcondition did not hold")
            return CapabilityState.UNSUPPORTED, notes
        if not all(o.postcondition_success is True for o in observations):
            notes.append("postcondition could not be measured on at least one trial")
            return CapabilityState.INCONCLUSIVE, notes

    any_interference = any(
        o.classification
        not in (InterferenceClassification.BACKGROUND_SAFE, InterferenceClassification.UNSUPPORTED, InterferenceClassification.ERROR)
        and o.classification != InterferenceClassification.INCONCLUSIVE
        for o in observations
    )
    any_inconclusive = any(o.classification == InterferenceClassification.INCONCLUSIVE for o in observations)

    if any_interference:
        notes.append("measured interference on at least one trial (see interference_classifications)")
        return CapabilityState.SUPPORTED_WITH_LIMITATIONS, notes
    if any_inconclusive:
        notes.append("focus/foreground signal unmeasurable on at least one trial")
        return CapabilityState.INCONCLUSIVE, notes
    return CapabilityState.SUPPORTED, notes


def _run_condition_trials(
    *,
    runner: ExperimentRunner,
    writer: ResultWriter,
    holder_pid: Optional[int],
    condition: str,
    action_type: str,
    make_spec: Callable[[], ActionSpec],
    trials: int,
    with_overlay: bool,
) -> List[ExperimentObservation]:
    observations: List[ExperimentObservation] = []
    overlay_handle = None
    try:
        if holder_pid is not None:
            _reactivate_and_wait(holder_pid)
        if with_overlay:
            try:
                overlay_handle = launch_overlay()
            except OverlayLaunchError:
                return observations
        for i in range(trials):
            spec = make_spec()
            spec.action_type = f"{condition}__{action_type}"
            obs = runner.run_trial(f"{condition}-trial-{i:02d}-{action_type}", spec)
            writer.write(obs)
            observations.append(obs)
    finally:
        if overlay_handle is not None:
            overlay_handle.terminate()
    return observations


def _stable_read_spec(
    *,
    get_element: Callable[[], object],
    attribute: str,
    target_application: Measurement,
    target_process: Measurement,
    target_window: Measurement,
    focus_pid: Optional[int],
) -> ActionSpec:
    """A read-only, non-mutating trial: read `attribute` off whatever
    `get_element()` resolves to, then read it again. The real
    postcondition is stability (the same value both times) - a
    legitimate, verifiable, harmless probe for apps where an actual
    invoke/mutate action would risk touching real user data."""

    def execute():
        element = get_element()
        if element is None:
            raise RuntimeError("target element not found")
        value, _err = axi.copy_attr(element, attribute)
        return value

    def verify(first_value):
        element = get_element()
        if element is None:
            return False, Measurement.of({"first": first_value, "second": None})
        second_value, _err = axi.copy_attr(element, attribute)
        success = second_value == first_value
        return success, Measurement.of({"first": first_value, "second": second_value})

    return ActionSpec(
        action_type="ax_stable_read",
        action_mechanism=ActionMechanism.MACOS_AX_READ,
        expected_postcondition=f"repeated AX read of {attribute} on the same element is stable",
        execute=execute,
        verify=verify,
        target_application=target_application,
        target_process=target_process,
        target_window=target_window,
        focus_pid=focus_pid,
    )


def _tree_quality_from_stats(stats: axi.TreeWalkStats) -> TreeQualityObservations:
    return TreeQualityObservations(
        element_count=stats.node_count,
        max_depth_observed=stats.max_depth,
        actionable_controls=stats.actionable_count,
        elements_with_identifier=stats.identifier_count,
        elements_with_meaningful_label=stats.labeled_count,
        distinct_roles_seen=len(stats.roles_seen),
        web_content_exposed=stats.web_area_present,
        truncated=stats.truncated,
    )


def _base_record(
    *,
    application: str,
    bundle_identifier: Optional[str],
    architecture: AppArchitecture,
    installed: bool,
) -> AppCapabilityRecord:
    return AppCapabilityRecord(
        application=application,
        bundle_identifier=bundle_identifier,
        pid=None,
        architecture=architecture,
        installed=installed,
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
    )


def _probe_generic_read_only_app(
    *,
    key: str,
    display_name: str,
    bundle_id: str,
    architecture: AppArchitecture,
    resolver,
    runner: ExperimentRunner,
    writer: ResultWriter,
    holder_pid: Optional[int],
) -> AppCapabilityRecord:
    """Discovery/read/tree-quality plus a non-mutating background/
    occlusion probe. No action/mutation is ever invoked against these
    real applications' own data (Finder/Notes/Calendar/System
    Settings)."""
    record = _base_record(application=display_name, bundle_identifier=bundle_id, architecture=architecture, installed=True)

    try:
        with resolver() as resolved:
            record.pid = resolved.pid
            ax_app = axi.create_application_element(resolved.pid)
            if ax_app is None or not axi.wait_for_ax_bootstrap(ax_app):
                record.ax_application_creation = CapabilityState.INCONCLUSIVE
                record.limitations.append("AX application element never became readable (AXRole never succeeded)")
                _mark_remaining(record, CapabilityState.INCONCLUSIVE, *_ALL_CAPABILITY_FIELDS[1:])
                return record
            record.ax_application_creation = CapabilityState.SUPPORTED

            windows = axi.list_windows(ax_app)
            deadline = time.monotonic() + 3.0
            while not windows and time.monotonic() < deadline:
                time.sleep(0.2)
                windows = axi.list_windows(ax_app)
            if not windows:
                record.window_discovery = CapabilityState.INCONCLUSIVE
                record.tree_traversal = CapabilityState.INCONCLUSIVE
                record.semantic_read = CapabilityState.INCONCLUSIVE
                record.limitations.append("no AXWindows exposed at probe time")
                target_root = ax_app
            else:
                record.window_discovery = CapabilityState.SUPPORTED
                target_root = windows[0]
                stats = axi.walk_tree(target_root)
                record.tree_quality = _tree_quality_from_stats(stats)
                record.tree_traversal = CapabilityState.SUPPORTED if stats.node_count > 1 else CapabilityState.SUPPORTED_WITH_LIMITATIONS
                record.semantic_read = (
                    CapabilityState.SUPPORTED
                    if (stats.labeled_count > 0 or stats.identifier_count > 0)
                    else CapabilityState.SUPPORTED_WITH_LIMITATIONS
                )
                if stats.actionable_count == 0:
                    record.limitations.append("no actionable (AXActions-exposing) elements found within traversal bounds")

            record.semantic_action_availability = CapabilityState.NOT_TESTED_SAFETY
            record.semantic_action_verified = CapabilityState.NOT_TESTED_SAFETY
            record.value_mutation_availability = CapabilityState.NOT_TESTED_SAFETY
            record.value_mutation_verified = CapabilityState.NOT_TESTED_SAFETY
            record.limitations.append(
                "action/value-mutation trials skipped by design: this application holds real user data "
                "(files, notes, events, or system settings) and no scratch/disposable target is available"
            )

            target_application = Measurement.of(display_name)
            target_process = Measurement.of(resolved.pid)
            title_val, _ = axi.copy_attr(target_root, "AXTitle")
            target_window = Measurement.of(str(title_val)) if title_val else Measurement.unavailable("no AXTitle")

            def get_element():
                return target_root

            bg_obs = _run_condition_trials(
                runner=runner,
                writer=writer,
                holder_pid=holder_pid,
                condition="background",
                action_type="stable_read",
                make_spec=lambda: _stable_read_spec(
                    get_element=get_element,
                    attribute="AXTitle",
                    target_application=target_application,
                    target_process=target_process,
                    target_window=target_window,
                    focus_pid=resolved.pid,
                ),
                trials=BACKGROUND_OCCLUSION_TRIALS,
                with_overlay=False,
            )
            record.background_inspection, bg_notes = _aggregate_capability(bg_obs, require_postcondition=True)
            record.limitations += bg_notes
            record.background_action = CapabilityState.NOT_TESTED_SAFETY

            occ_obs = _run_condition_trials(
                runner=runner,
                writer=writer,
                holder_pid=holder_pid,
                condition="occluded",
                action_type="stable_read",
                make_spec=lambda: _stable_read_spec(
                    get_element=get_element,
                    attribute="AXTitle",
                    target_application=target_application,
                    target_process=target_process,
                    target_window=target_window,
                    focus_pid=resolved.pid,
                ),
                trials=BACKGROUND_OCCLUSION_TRIALS,
                with_overlay=True,
            )
            record.occluded_inspection, occ_notes = _aggregate_capability(occ_obs, require_postcondition=True)
            record.limitations += occ_notes
            record.occluded_action = CapabilityState.NOT_TESTED_SAFETY

            record.interference_classifications = sorted({o.classification.value for o in bg_obs + occ_obs})

            if resolved.launched_scratch_window and key == "finder":
                _close_window_via_ax(target_root)
            _quit_if_launched(bundle_id, resolved)

    except TargetUnavailable as exc:
        record.installed = False
        record.pid = None
        record.ax_application_creation = CapabilityState.NOT_INSTALLED
        record.window_discovery = CapabilityState.NOT_INSTALLED
        record.tree_traversal = CapabilityState.NOT_INSTALLED
        record.semantic_read = CapabilityState.NOT_INSTALLED
        record.semantic_action_availability = CapabilityState.NOT_INSTALLED
        record.semantic_action_verified = CapabilityState.NOT_INSTALLED
        record.value_mutation_availability = CapabilityState.NOT_INSTALLED
        record.value_mutation_verified = CapabilityState.NOT_INSTALLED
        record.background_inspection = CapabilityState.NOT_INSTALLED
        record.background_action = CapabilityState.NOT_INSTALLED
        record.occluded_inspection = CapabilityState.NOT_INSTALLED
        record.occluded_action = CapabilityState.NOT_INSTALLED
        record.limitations.append(str(exc))

    if holder_pid is not None:
        _reactivate_and_wait(holder_pid)
    return record


def _probe_web_fixture_app(
    *,
    display_name: str,
    bundle_id: str,
    architecture: AppArchitecture,
    resolver,
    runner: ExperimentRunner,
    writer: ResultWriter,
    holder_pid: Optional[int],
) -> AppCapabilityRecord:
    """Safari/Chrome: full verified action + value-mutation trials
    against the existing local, network-free
    `phase0/fixtures/browser_page1.html` fixture - the same page the
    browser non-interference campaign already uses - loaded in a brand
    new window, never the operator's real tabs/profile."""
    record = _base_record(application=display_name, bundle_identifier=bundle_id, architecture=architecture, installed=True)

    try:
        with resolver() as resolved:
            record.pid = resolved.pid
            ax_app = axi.create_application_element(resolved.pid)
            if ax_app is None or not axi.wait_for_ax_bootstrap(ax_app):
                record.ax_application_creation = CapabilityState.INCONCLUSIVE
                record.limitations.append("AX application element never became readable")
                _mark_remaining(record, CapabilityState.INCONCLUSIVE, *_ALL_CAPABILITY_FIELDS[1:])
                return record
            record.ax_application_creation = CapabilityState.SUPPORTED

            # Poll rather than a single snapshot read: the window can take
            # a moment to register with AX after `open` launches/targets
            # the app, even though the process itself is already alive
            # (observed directly while building this probe - a single
            # immediate AXWindows read can transiently see zero windows).
            target_window = None
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and target_window is None:
                windows = axi.list_windows(ax_app)
                for w in windows:
                    title, _ = axi.copy_attr(w, "AXTitle")
                    if title and FIXTURE_PAGE_TITLE in str(title):
                        target_window = w
                        break
                if target_window is None and windows:
                    target_window = windows[0]
                if target_window is None:
                    time.sleep(0.2)

            if target_window is None:
                record.window_discovery = CapabilityState.INCONCLUSIVE
                record.limitations.append("could not find the fixture-page window")
                _mark_remaining(record, CapabilityState.INCONCLUSIVE, *_ALL_CAPABILITY_FIELDS[2:])
                return record
            record.window_discovery = CapabilityState.SUPPORTED

            # Poll: a just-opened page can still be loading when the
            # first AX read lands (observed directly - a single
            # immediate check missed a WebArea that a repeat check
            # moments later found), a distinct thing from Chromium's
            # on-demand AX tree below.
            # Chrome's own chrome (toolbar/tab strip) nests deeper before
            # reaching web content than Safari's - bounded search depth
            # is widened for Chromium specifically (observed directly:
            # depth 6 hit the traversal cap on Chrome's window without
            # reaching AXWebArea at all).
            web_area_search_depth = 12 if architecture == AppArchitecture.CHROMIUM else 6
            web_area = None
            warmed_up = False
            deadline = time.monotonic() + 5.0
            while web_area is None and time.monotonic() < deadline:
                web_area = axi.find_by_role(target_window, "AXWebArea", max_depth=web_area_search_depth)
                if web_area is None:
                    if architecture == AppArchitecture.CHROMIUM and not warmed_up:
                        # Chromium builds its content AX subtree on demand
                        # - see phase0/CAMPAIGN_REPORT.md section M. Warm
                        # it up via the existing, already-proven mechanism
                        # before concluding web content is unreachable.
                        warm_up_ax_focus_tree(resolved.pid)
                        warmed_up = True
                    time.sleep(0.3)
            if web_area is not None and warmed_up:
                record.limitations.append("required warm_up_ax_focus_tree before web content AX subtree was reachable")

            traversal_root = web_area if web_area is not None else target_window
            stats = axi.walk_tree(traversal_root)
            record.tree_quality = _tree_quality_from_stats(stats)
            record.tree_traversal = CapabilityState.SUPPORTED if stats.node_count > 1 else CapabilityState.SUPPORTED_WITH_LIMITATIONS
            record.semantic_read = CapabilityState.SUPPORTED if web_area is not None else CapabilityState.UNSUPPORTED
            if web_area is None:
                record.limitations.append("AXWebArea never appeared - web content is not exposed to AX from this process")
                record.semantic_action_availability = CapabilityState.UNSUPPORTED
                record.semantic_action_verified = CapabilityState.UNSUPPORTED
                record.value_mutation_availability = CapabilityState.UNSUPPORTED
                record.value_mutation_verified = CapabilityState.UNSUPPORTED
                record.background_inspection = CapabilityState.INCONCLUSIVE
                record.background_action = CapabilityState.UNSUPPORTED
                record.occluded_inspection = CapabilityState.INCONCLUSIVE
                record.occluded_action = CapabilityState.UNSUPPORTED
                return record

            button = axi.find_by_role_and_title(web_area, "AXButton", "Increment")
            text_field = axi.find_by_role(web_area, "AXTextField")

            def find_counter():
                # Re-located fresh every call, never a held reference:
                # WebKit appears to rebuild a <span>'s AXUIElement when
                # its text content changes (observed directly - a
                # reference captured before the press read back as an AX
                # error/empty after it), unlike the Cocoa fixture's
                # in-place AXStaticText mutation. Matched by "value is a
                # plain digit string" so it still matches after the
                # counter increments past its initial "0".
                return axi.find_descendant(
                    web_area,
                    lambda e: axi.copy_attr(e, "AXRole")[0] in ("AXStaticText", "AXTextField")
                    and str(axi.copy_attr(e, "AXValue")[0] or "").isdigit(),
                )

            counter = find_counter()

            record.semantic_action_availability = CapabilityState.SUPPORTED if button is not None else CapabilityState.UNSUPPORTED
            record.value_mutation_availability = CapabilityState.SUPPORTED if text_field is not None else CapabilityState.UNSUPPORTED

            target_application = Measurement.of(display_name)
            target_process = Measurement.of(resolved.pid)
            target_window_m = Measurement.of(FIXTURE_PAGE_TITLE)

            if button is not None and counter is not None:

                def action_execute():
                    before_el = find_counter()
                    before, _ = axi.copy_attr(before_el, "AXValue")
                    fresh_button = axi.find_by_role_and_title(web_area, "AXButton", "Increment") or button
                    err = axi.perform_action(fresh_button, "AXPress")
                    return before, err

                def action_verify(result):
                    before, _err = result
                    after_el = find_counter()
                    after, _ = axi.copy_attr(after_el, "AXValue")
                    success = after is not None and after != before
                    return success, Measurement.of({"before": before, "after": after})

                def make_action_spec():
                    return ActionSpec(
                        action_type="ax_web_invoke_press_action",
                        action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                        expected_postcondition="pressing the Increment AXButton changes the counter's AXValue",
                        execute=action_execute,
                        verify=action_verify,
                        target_application=target_application,
                        target_process=target_process,
                        target_window=target_window_m,
                        focus_pid=resolved.pid,
                    )

                baseline_obs = _run_condition_trials(
                    runner=runner, writer=writer, holder_pid=holder_pid, condition="baseline",
                    action_type="invoke_press_action", make_spec=make_action_spec, trials=1, with_overlay=False,
                )
                record.semantic_action_verified, _ = _aggregate_capability(baseline_obs)

                bg_obs = _run_condition_trials(
                    runner=runner, writer=writer, holder_pid=holder_pid, condition="background",
                    action_type="invoke_press_action", make_spec=make_action_spec,
                    trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=False,
                )
                record.background_action, bg_notes = _aggregate_capability(bg_obs)
                record.limitations += bg_notes

                occ_obs = _run_condition_trials(
                    runner=runner, writer=writer, holder_pid=holder_pid, condition="occluded",
                    action_type="invoke_press_action", make_spec=make_action_spec,
                    trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=True,
                )
                record.occluded_action, occ_notes = _aggregate_capability(occ_obs)
                record.limitations += occ_notes
                record.interference_classifications = sorted(
                    {o.classification.value for o in baseline_obs + bg_obs + occ_obs}
                )
            else:
                record.semantic_action_verified = CapabilityState.UNSUPPORTED
                record.background_action = CapabilityState.UNSUPPORTED
                record.occluded_action = CapabilityState.UNSUPPORTED

            if text_field is not None:
                scratch_value = "phase0-mac-app-caps-scratch"

                def mutate_execute():
                    fresh_field = axi.find_by_role(web_area, "AXTextField") or text_field
                    return axi.set_attr(fresh_field, "AXValue", scratch_value)

                def mutate_verify(_result):
                    fresh_field = axi.find_by_role(web_area, "AXTextField") or text_field
                    observed, _ = axi.copy_attr(fresh_field, "AXValue")
                    success = observed == scratch_value
                    return success, Measurement.of({"expected": scratch_value, "observed": observed})

                mutate_spec = ActionSpec(
                    action_type="ax_web_set_text_value",
                    action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                    expected_postcondition=f"AXValue of the text field becomes {scratch_value!r}",
                    execute=mutate_execute,
                    verify=mutate_verify,
                    target_application=target_application,
                    target_process=target_process,
                    target_window=target_window_m,
                    focus_pid=resolved.pid,
                )
                mutate_obs = runner.run_trial("baseline-trial-00-set_text_value", mutate_spec)
                writer.write(mutate_obs)
                record.value_mutation_verified, _ = _aggregate_capability([mutate_obs])

                if record.background_inspection == CapabilityState.NOT_INSTALLED:
                    # Neither action nor mutation trials above already
                    # covered background/occlusion (button was missing);
                    # fall back to a read-only probe on the text field.
                    read_bg_obs = _run_condition_trials(
                        runner=runner, writer=writer, holder_pid=holder_pid, condition="background",
                        action_type="stable_read",
                        make_spec=lambda: _stable_read_spec(
                            get_element=lambda: text_field, attribute="AXValue",
                            target_application=target_application, target_process=target_process,
                            target_window=target_window_m, focus_pid=resolved.pid,
                        ),
                        trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=False,
                    )
                    record.background_inspection, _ = _aggregate_capability(read_bg_obs)
            else:
                record.value_mutation_verified = CapabilityState.UNSUPPORTED

            if record.background_inspection == CapabilityState.NOT_INSTALLED:
                record.background_inspection = record.background_action
            if record.occluded_inspection == CapabilityState.NOT_INSTALLED:
                record.occluded_inspection = record.occluded_action

            _close_window_via_ax(target_window)

    except TargetUnavailable as exc:
        record.installed = False
        record.limitations.append(str(exc))
        for field_name in (
            "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
            "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
            "value_mutation_verified", "background_inspection", "background_action",
            "occluded_inspection", "occluded_action",
        ):
            setattr(record, field_name, CapabilityState.NOT_INSTALLED)

    if holder_pid is not None:
        _reactivate_and_wait(holder_pid)
    return record


def _probe_vscode(
    *,
    display_name: str,
    bundle_id: str,
    resolver,
    runner: ExperimentRunner,
    writer: ResultWriter,
    holder_pid: Optional[int],
) -> AppCapabilityRecord:
    """Electron representative. Discovery/read + background/occlusion
    only - the Monaco editor surface is largely custom-drawn canvas, and
    no scratch document is saved/typed into to avoid an unsaved-changes
    prompt on window close."""
    record = _base_record(
        application=display_name, bundle_identifier=bundle_id, architecture=AppArchitecture.ELECTRON, installed=True
    )

    try:
        with resolver() as resolved:
            record.pid = resolved.pid
            ax_app = axi.create_application_element(resolved.pid)
            if ax_app is None or not axi.wait_for_ax_bootstrap(ax_app):
                record.ax_application_creation = CapabilityState.INCONCLUSIVE
                record.limitations.append("AX application element never became readable")
                _mark_remaining(record, CapabilityState.INCONCLUSIVE, *_ALL_CAPABILITY_FIELDS[1:])
                return record
            record.ax_application_creation = CapabilityState.SUPPORTED

            windows = axi.list_windows(ax_app)
            deadline = time.monotonic() + 5.0
            while not windows and time.monotonic() < deadline:
                time.sleep(0.2)
                windows = axi.list_windows(ax_app)
            if not windows:
                record.window_discovery = CapabilityState.INCONCLUSIVE
                record.limitations.append("no AXWindows exposed at probe time")
                _mark_remaining(record, CapabilityState.INCONCLUSIVE, *_ALL_CAPABILITY_FIELDS[2:])
                return record
            record.window_discovery = CapabilityState.SUPPORTED
            window = windows[0]

            stats = axi.walk_tree(window)
            needed_warmup = stats.node_count <= 1
            if needed_warmup:
                warm_up_ax_focus_tree(resolved.pid)
                stats = axi.walk_tree(window)
                record.limitations.append(
                    "initial traversal returned almost nothing before warm_up_ax_focus_tree "
                    "(Electron/Chromium on-demand AX tree - same mechanism as the Chrome finding "
                    "in phase0/CAMPAIGN_REPORT.md section M)"
                )
            record.tree_quality = _tree_quality_from_stats(stats)
            record.tree_traversal = CapabilityState.SUPPORTED if stats.node_count > 1 else CapabilityState.SUPPORTED_WITH_LIMITATIONS
            record.semantic_read = CapabilityState.SUPPORTED if (stats.labeled_count > 0 or stats.identifier_count > 0) else CapabilityState.SUPPORTED_WITH_LIMITATIONS
            if stats.node_count <= 1:
                record.limitations.append("editor surface is largely opaque to AX (custom-drawn Monaco canvas)")

            record.semantic_action_availability = (
                CapabilityState.SUPPORTED_WITH_LIMITATIONS if stats.actionable_count > 0 else CapabilityState.UNSUPPORTED
            )
            record.semantic_action_verified = CapabilityState.NOT_TESTED_SAFETY
            record.value_mutation_availability = CapabilityState.NOT_TESTED_SAFETY
            record.value_mutation_verified = CapabilityState.NOT_TESTED_SAFETY
            record.limitations.append(
                "action/value-mutation trials skipped by design: typing into the editor risks an "
                "unsaved-changes prompt on window close"
            )

            title_val, _ = axi.copy_attr(window, "AXTitle")
            target_application = Measurement.of(display_name)
            target_process = Measurement.of(resolved.pid)
            target_window = Measurement.of(str(title_val)) if title_val else Measurement.unavailable("no AXTitle")

            bg_obs = _run_condition_trials(
                runner=runner, writer=writer, holder_pid=holder_pid, condition="background",
                action_type="stable_read",
                make_spec=lambda: _stable_read_spec(
                    get_element=lambda: window, attribute="AXTitle",
                    target_application=target_application, target_process=target_process,
                    target_window=target_window, focus_pid=resolved.pid,
                ),
                trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=False,
            )
            record.background_inspection, bg_notes = _aggregate_capability(bg_obs)
            record.limitations += bg_notes
            record.background_action = CapabilityState.NOT_TESTED_SAFETY

            occ_obs = _run_condition_trials(
                runner=runner, writer=writer, holder_pid=holder_pid, condition="occluded",
                action_type="stable_read",
                make_spec=lambda: _stable_read_spec(
                    get_element=lambda: window, attribute="AXTitle",
                    target_application=target_application, target_process=target_process,
                    target_window=target_window, focus_pid=resolved.pid,
                ),
                trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=True,
            )
            record.occluded_inspection, occ_notes = _aggregate_capability(occ_obs)
            record.limitations += occ_notes
            record.occluded_action = CapabilityState.NOT_TESTED_SAFETY
            record.interference_classifications = sorted({o.classification.value for o in bg_obs + occ_obs})

            _close_window_via_ax(window)

    except TargetUnavailable as exc:
        record.installed = False
        record.limitations.append(str(exc))
        for field_name in (
            "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
            "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
            "value_mutation_verified", "background_inspection", "background_action",
            "occluded_inspection", "occluded_action",
        ):
            setattr(record, field_name, CapabilityState.NOT_INSTALLED)

    if holder_pid is not None:
        _reactivate_and_wait(holder_pid)
    return record


def _probe_cocoa_fixture(
    *, runner: ExperimentRunner, writer: ResultWriter, holder_pid: Optional[int]
) -> AppCapabilityRecord:
    """The existing, unrestricted Cocoa AX fixture - full verified
    action + value-mutation trials, reusing
    phase0/experiments/macos_ax/ax_elements.py directly rather than the
    generic AX helpers, since it already has exact, purpose-built
    element getters."""
    record = _base_record(
        application="Phase 0 Cocoa AX Fixture", bundle_identifier=None, architecture=AppArchitecture.COCOA, installed=True
    )

    try:
        fixture = launch_fixture()
    except FixtureLaunchError as exc:
        record.installed = False
        record.limitations.append(str(exc))
        for field_name in (
            "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
            "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
            "value_mutation_verified", "background_inspection", "background_action",
            "occluded_inspection", "occluded_action",
        ):
            setattr(record, field_name, CapabilityState.NOT_INSTALLED)
        return record

    try:
        record.pid = fixture.pid
        # Poll: `launch_fixture()`'s readiness line fires once the window
        # object exists, which can be moments before it is enumerable via
        # AXWindows (same class of race seen with Safari/Chrome/VS Code
        # windows above).
        window = None
        deadline = time.monotonic() + 5.0
        while window is None and time.monotonic() < deadline:
            try:
                window = ax_elements.get_fixture_window(fixture.pid)
            except ax_elements.ElementNotFoundError:
                time.sleep(0.2)
        if window is None:
            window = ax_elements.get_fixture_window(fixture.pid)  # let it raise with a clear error
        record.ax_application_creation = CapabilityState.SUPPORTED
        record.window_discovery = CapabilityState.SUPPORTED

        stats = axi.walk_tree(window)
        record.tree_quality = _tree_quality_from_stats(stats)
        record.tree_traversal = CapabilityState.SUPPORTED
        record.semantic_read = CapabilityState.SUPPORTED
        record.semantic_action_availability = CapabilityState.SUPPORTED
        record.value_mutation_availability = CapabilityState.SUPPORTED

        target_application = Measurement.of("phase0_ax_fixture")
        target_process = Measurement.of(fixture.pid)
        target_window = Measurement.of(FIXTURE_WINDOW_TITLE)

        def make_action_spec():
            def execute():
                w = ax_elements.get_fixture_window(fixture.pid)
                button = ax_elements.get_press_button(w)
                return ax_elements.perform_action(button, "AXPress")

            def verify(_result):
                w = ax_elements.get_fixture_window(fixture.pid)
                counter = ax_elements.get_counter_label(w)
                observed = ax_elements.read_value(counter)
                return observed is not None and observed.startswith("pressed:"), Measurement.of({"observed": observed})

            return ActionSpec(
                action_type="ax_invoke_press_action",
                action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                expected_postcondition="fixture counter label changes after AXPress",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=target_window,
                focus_pid=fixture.pid,
            )

        baseline_obs = _run_condition_trials(
            runner=runner, writer=writer, holder_pid=holder_pid, condition="baseline",
            action_type="invoke_press_action", make_spec=make_action_spec, trials=1, with_overlay=False,
        )
        record.semantic_action_verified, _ = _aggregate_capability(baseline_obs)

        def make_mutation_spec():
            def execute():
                w = ax_elements.get_fixture_window(fixture.pid)
                field = ax_elements.get_text_field(w)
                return ax_elements.set_value(field, "phase0-mac-app-caps-scratch")

            def verify(_result):
                w = ax_elements.get_fixture_window(fixture.pid)
                field = ax_elements.get_text_field(w)
                observed = ax_elements.read_value(field)
                return observed == "phase0-mac-app-caps-scratch", Measurement.of({"observed": observed})

            return ActionSpec(
                action_type="ax_set_text_value",
                action_mechanism=ActionMechanism.MACOS_AX_MUTATE,
                expected_postcondition="fixture text field AXValue becomes the scratch string",
                execute=execute,
                verify=verify,
                target_application=target_application,
                target_process=target_process,
                target_window=target_window,
                focus_pid=fixture.pid,
            )

        mutation_obs = _run_condition_trials(
            runner=runner, writer=writer, holder_pid=holder_pid, condition="baseline",
            action_type="set_text_value", make_spec=make_mutation_spec, trials=1, with_overlay=False,
        )
        record.value_mutation_verified, _ = _aggregate_capability(mutation_obs)

        bg_obs = _run_condition_trials(
            runner=runner, writer=writer, holder_pid=holder_pid, condition="background",
            action_type="invoke_press_action", make_spec=make_action_spec,
            trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=False,
        )
        record.background_inspection, bg_i_notes = _aggregate_capability(bg_obs)
        record.background_action, bg_a_notes = _aggregate_capability(bg_obs)
        record.limitations += bg_i_notes + bg_a_notes

        occ_obs = _run_condition_trials(
            runner=runner, writer=writer, holder_pid=holder_pid, condition="occluded",
            action_type="invoke_press_action", make_spec=make_action_spec,
            trials=BACKGROUND_OCCLUSION_TRIALS, with_overlay=True,
        )
        record.occluded_inspection, occ_i_notes = _aggregate_capability(occ_obs)
        record.occluded_action, occ_a_notes = _aggregate_capability(occ_obs)
        record.limitations += occ_i_notes + occ_a_notes
        record.interference_classifications = sorted(
            {o.classification.value for o in baseline_obs + mutation_obs + bg_obs + occ_obs}
        )
    finally:
        fixture.terminate()

    if holder_pid is not None:
        _reactivate_and_wait(holder_pid)
    return record


def run_matrix(output_dir: Path, run_id: str, only_key: Optional[str] = None) -> Tuple[Path, List[AppCapabilityRecord]]:
    if not is_macos() or not pyobjc_available():
        raise MatrixBlocked("mac-app-capabilities requires macOS with pyobjc available")

    output_dir = Path(output_dir)
    results_path = output_dir / f"{EXPERIMENT_ID}-{run_id}.jsonl"
    writer = ResultWriter(results_path)
    observer = MacObserver()
    runner = ExperimentRunner(experiment_id=EXPERIMENT_ID, run_id=run_id, observer=observer)
    holder_pid = _get_frontmost_pid(observer)

    permission_ok = accessibility_trusted()

    records: List[AppCapabilityRecord] = []

    def _blocked_record(display_name: str, bundle_id: Optional[str], architecture: AppArchitecture) -> AppCapabilityRecord:
        rec = _base_record(application=display_name, bundle_identifier=bundle_id, architecture=architecture, installed=True)
        for field_name in (
            "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
            "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
            "value_mutation_verified", "background_inspection", "background_action",
            "occluded_inspection", "occluded_action",
        ):
            setattr(rec, field_name, CapabilityState.BLOCKED_PERMISSION)
        rec.limitations.append("accessibility_permission_not_granted")
        return rec

    plan = [
        ("finder", "Finder", "com.apple.finder", AppArchitecture.COCOA, "generic", targets_mod.finder_target),
        ("notes", "Notes", "com.apple.Notes", AppArchitecture.SWIFTUI, "generic", targets_mod.notes_target),
        ("calendar", "Calendar", "com.apple.iCal", AppArchitecture.COCOA, "generic", targets_mod.calendar_target),
        (
            "system_settings", "System Settings", "com.apple.systempreferences", AppArchitecture.SWIFTUI,
            "generic", targets_mod.system_settings_target,
        ),
        ("safari", "Safari", "com.apple.Safari", AppArchitecture.WEBKIT, "web", targets_mod.safari_target),
        ("chrome", "Google Chrome", "com.google.Chrome", AppArchitecture.CHROMIUM, "web", targets_mod.disposable_chrome_target),
        ("vscode", "Visual Studio Code", "com.microsoft.VSCode", AppArchitecture.ELECTRON, "vscode", targets_mod.vscode_target),
        ("cocoa_fixture", "Phase 0 Cocoa AX Fixture", None, AppArchitecture.COCOA, "fixture", None),
    ]

    for key, display_name, bundle_id, architecture, kind, resolver in plan:
        if only_key is not None and key != only_key:
            continue

        if not permission_ok:
            records.append(_blocked_record(display_name, bundle_id, architecture))
            continue

        if kind != "fixture" and bundle_id is not None and not targets_mod.app_installed(bundle_id):
            rec = _base_record(application=display_name, bundle_identifier=bundle_id, architecture=architecture, installed=False)
            for field_name in (
                "ax_application_creation", "window_discovery", "tree_traversal", "semantic_read",
                "semantic_action_availability", "semantic_action_verified", "value_mutation_availability",
                "value_mutation_verified", "background_inspection", "background_action",
                "occluded_inspection", "occluded_action",
            ):
                setattr(rec, field_name, CapabilityState.NOT_INSTALLED)
            records.append(rec)
            continue

        if kind == "generic":
            records.append(
                _probe_generic_read_only_app(
                    key=key, display_name=display_name, bundle_id=bundle_id, architecture=architecture,
                    resolver=resolver, runner=runner, writer=writer, holder_pid=holder_pid,
                )
            )
        elif kind == "web":
            records.append(
                _probe_web_fixture_app(
                    display_name=display_name, bundle_id=bundle_id, architecture=architecture,
                    resolver=resolver, runner=runner, writer=writer, holder_pid=holder_pid,
                )
            )
        elif kind == "vscode":
            records.append(
                _probe_vscode(
                    display_name=display_name, bundle_id=bundle_id, resolver=resolver,
                    runner=runner, writer=writer, holder_pid=holder_pid,
                )
            )
        elif kind == "fixture":
            records.append(_probe_cocoa_fixture(runner=runner, writer=writer, holder_pid=holder_pid))

    if results_path.exists():
        summary = summarize(read_results(results_path))
        write_summary(summary, output_dir / f"{EXPERIMENT_ID}-{run_id}-summary.json")

    matrix_path = output_dir / f"{EXPERIMENT_ID}-{run_id}-matrix.json"
    import json as _json

    matrix_path.write_text(_json.dumps([r.to_dict() for r in records], indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if holder_pid is not None:
        _reactivate_and_wait(holder_pid)

    return matrix_path, records
