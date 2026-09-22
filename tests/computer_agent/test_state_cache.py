"""`Controller.state` incremental cache (perf optimization, no new semantics).

`Controller.state(task_id)` is called many times per action lifecycle
(`_drive_step`, `_attempt`, `_verify_and_settle`, `_settle`, `_recover`, ...).
Before this change it called `replay(self.j.events(task_id))` every time:
a full SQLite scan of the task's entire history plus a full re-fold, so a
task with N events did O(N^2) work in total. `Controller` now keeps a
per-task `TaskState` and folds only `Journal.events_since(...)` on each
call via `computer_agent.state.advance`.

This must not change *what* is computed -- only how much work it takes to
get there. Two properties are asserted: identical results to a fresh full
replay at every step of a real multi-action run, and a real drop in rows
read from the journal.
"""

from __future__ import annotations

import random

import pytest

from computer_agent.controller import Controller
from computer_agent.journal import Journal
from computer_agent.state import replay
from computer_agent.types import EffectClass

from .fixtures.fixture_c import KIND_CLASS, WorldClient, make_steps, new_world, spec_for

TASK = "task-1"


def _uncached_state(journal, task_id):
    """Oracle: what `Controller.state` used to compute, unconditionally."""
    return replay(journal.events(task_id))


def test_events_since_returns_exact_suffix(tmp_path):
    from computer_agent.journal import EventType as E

    j = Journal(tmp_path / "j.db")
    j.append("t", E.TASK_CREATED, "t/TC", {"steps": [], "granted_kinds": []})
    j.append("t", E.RECOVERY_STARTED, "t/R1")
    j.append("t", E.RECOVERY_STARTED, "t/R2")
    all_events = j.events("t")
    assert [e.type for e in j.events_since("t", 0)] == [e.type for e in all_events]
    assert j.events_since("t", all_events[0].seq) == all_events[1:]
    assert j.events_since("t", all_events[-1].seq) == []
    j.close()


def test_cached_state_matches_uncached_replay_throughout_a_run(tmp_path):
    rng = random.Random(42)
    steps = make_steps(list(EffectClass), rng)
    world_path = tmp_path / "world.json"
    new_world(world_path, rng)

    journal = Journal(tmp_path / "journal.db")
    world = WorldClient(world_path)
    ctrl = Controller(journal, world, spec_for)
    ctrl.create_task(TASK, steps, list(KIND_CLASS))

    full_scans: list[int] = []  # rows returned by each full events() call
    since_calls: list[tuple[int, int]] = []  # (since_seq, rows returned) per events_since() call
    real_events, real_events_since = journal.events, journal.events_since

    def spying_events(task_id):
        rows = real_events(task_id)
        full_scans.append(len(rows))
        return rows

    def spying_events_since(task_id, since_seq):
        rows = real_events_since(task_id, since_seq)
        since_calls.append((since_seq, len(rows)))
        return rows

    journal.events = spying_events  # type: ignore[method-assign]
    journal.events_since = spying_events_since  # type: ignore[method-assign]

    final = ctrl.run(TASK)

    # exactly one cold full scan during the whole run (cache population);
    # every later call is incremental, with non-decreasing, strictly
    # advancing floors -- never a second re-scan from the beginning.
    assert len(full_scans) == 1
    assert since_calls, "expected at least one cached (events_since) call after warmup"
    floors = [floor for floor, _ in since_calls]
    assert floors == sorted(floors)
    assert floors[0] == full_scans[0]  # first incremental call starts exactly where the full scan left off

    assert final.status == "COMPLETED"
    # oracle: a from-scratch replay of the whole journal must agree exactly
    # (this call legitimately triggers its own full events() scan; checked after)
    oracle = _uncached_state(journal, TASK)
    assert repr(oracle) == repr(ctrl.state(TASK))
    assert oracle.event_count == ctrl.state(TASK).event_count

    journal.close()


def test_new_controller_instance_starts_cold_and_still_agrees(tmp_path):
    """A restarted process (new Controller, empty cache) must reconstruct
    identical state from the journal alone -- the cache is never authoritative."""
    rng = random.Random(7)
    steps = make_steps([EffectClass.IDEMPOTENCY_KEY, EffectClass.STATE_SET], rng)
    world_path = tmp_path / "world.json"
    new_world(world_path, rng)

    journal = Journal(tmp_path / "journal.db")
    ctrl1 = Controller(journal, WorldClient(world_path), spec_for)
    ctrl1.create_task(TASK, steps, list(KIND_CLASS))
    ctrl1.run(TASK)
    s1 = ctrl1.state(TASK)

    ctrl2 = Controller(journal, WorldClient(world_path), spec_for)  # fresh instance, empty cache
    s2 = ctrl2.state(TASK)

    assert repr(s1) == repr(s2)
    journal.close()


def test_state_cache_reduces_total_rows_scanned_vs_uncached_baseline(tmp_path):
    """Direct before/after comparison: total events folded across every
    `state()` call in a run, cached vs. the old always-full-replay behavior."""
    rng = random.Random(3)
    steps = make_steps(list(EffectClass), rng)
    world_path = tmp_path / "world.json"
    new_world(world_path, rng)

    journal = Journal(tmp_path / "journal.db")
    ctrl = Controller(journal, WorldClient(world_path), spec_for)
    ctrl.create_task(TASK, steps, list(KIND_CLASS))

    cached_rows_folded = 0
    real_events = journal.events
    real_events_since = journal.events_since

    def counting_events(task_id):
        nonlocal cached_rows_folded
        rows = real_events(task_id)
        cached_rows_folded += len(rows)
        return rows

    def counting_events_since(task_id, since_seq):
        nonlocal cached_rows_folded
        rows = real_events_since(task_id, since_seq)
        cached_rows_folded += len(rows)
        return rows

    journal.events = counting_events  # type: ignore[method-assign]
    journal.events_since = counting_events_since  # type: ignore[method-assign]
    ctrl.run(TASK)
    total_events = len(real_events(TASK))
    journal.close()

    # cached total work is bounded by (a fixed few full builds) + (one pass
    # over the journal overall) -- never quadratic in event count. With >1
    # state() call in this run and >1 event, the cached total must be far
    # below calls_made * total_events (the old behavior's cost).
    assert cached_rows_folded <= total_events * 3
    assert total_events > 5  # sanity: this run actually produced meaningful history
