"""SQLite journal durability and deterministic replay (M3, task item C7).

What is tested here: reopen/reconstruct, WAL mode, duplicate-event
protection, schema-version refusal, deterministic materialization, and
refusal to materialize corrupted/out-of-order lifecycles. What is NOT
tested: power loss / filesystem-level durability (no such fault injection
exists in this harness; synchronous=FULL is configured but unproven here).
"""

from __future__ import annotations

import sqlite3

import pytest

from computer_agent.journal import SCHEMA_VERSION, DuplicateEvent, EventType as E, Journal, SchemaVersionError
from computer_agent.state import JournalIntegrityError, Phase, replay
from computer_agent.verification import Indeterminate

STEPS = [{"step_id": "s1", "kind": "k", "args": {}, "effect_class": "A", "target_spec": {"name": "X"}}]


def _intent(j, aid="s1.a1"):
    j.append("t", E.ACTION_INTENT_PERSISTED, f"{aid}/0/I", {"kind": "k", "args": {}, "effect_class": "A",
                                                           "target_spec": {"name": "X"}},
             step_id="s1", action_id=aid)


@pytest.fixture
def j(tmp_path):
    journal = Journal(tmp_path / "j.db")
    journal.append("t", E.TASK_CREATED, "t/TASK_CREATED", {"steps": STEPS, "granted_kinds": ["k"]})
    yield journal
    journal.close()


def test_wal_mode_and_reopen_reconstructs(j, tmp_path):
    assert j._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert j._db.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    _intent(j)
    j.append("t", E.DISPATCH_STARTED, "s1.a1/1/D", {"dispatch": 1, "before": {"x": 1}}, step_id="s1",
             action_id="s1.a1")
    assert (tmp_path / "j.db-wal").exists()
    # a second, independent connection sees committed events without any checkpoint/close
    other = Journal(tmp_path / "j.db")
    s = replay(other.events("t"))
    assert s.actions["s1.a1"].phase == Phase.DISPATCH_STARTED and s.actions["s1.a1"].before == {"x": 1}
    other.close()


def test_duplicate_event_rejected(j):
    _intent(j)
    with pytest.raises(DuplicateEvent):
        _intent(j)
    assert len(j.events("t")) == 2  # the failed insert left nothing behind


def test_schema_version_mismatch_refused(tmp_path):
    Journal(tmp_path / "j.db").close()
    con = sqlite3.connect(tmp_path / "j.db")
    con.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION + 1),))
    con.commit()
    con.close()
    with pytest.raises(SchemaVersionError):
        Journal(tmp_path / "j.db")


def test_replay_is_deterministic_and_indeterminate_round_trips(j):
    _intent(j)
    j.append("t", E.DISPATCH_STARTED, "s1.a1/1/D", {"dispatch": 1, "before": Indeterminate("offline")},
             step_id="s1", action_id="s1.a1")
    a, b = replay(j.events("t")), replay(j.events("t"))
    assert repr(a) == repr(b)
    assert isinstance(a.actions["s1.a1"].before, Indeterminate)


@pytest.mark.parametrize("bad", [
    "dispatch_without_intent", "commit_without_verification", "commit_after_failure",
    "step_complete_without_commit", "event_before_task", "dispatch_number_skip", "second_live_intent",
])
def test_corrupted_lifecycles_refused(tmp_path, bad):
    j = Journal(tmp_path / "j.db")
    if bad == "event_before_task":
        _intent(j)
        with pytest.raises(JournalIntegrityError):
            replay(j.events("t"))
        return
    j.append("t", E.TASK_CREATED, "t/TC", {"steps": STEPS, "granted_kinds": ["k"]})
    ids = dict(step_id="s1", action_id="s1.a1")
    if bad == "dispatch_without_intent":
        j.append("t", E.DISPATCH_STARTED, "x", {"dispatch": 1, "before": {}}, **ids)
    else:
        _intent(j)
        if bad == "second_live_intent":
            _intent(j, "s1.a2")
        elif bad == "step_complete_without_commit":
            j.append("t", E.STEP_COMPLETED, "s", step_id="s1")
        elif bad == "dispatch_number_skip":
            j.append("t", E.DISPATCH_STARTED, "d", {"dispatch": 2, "before": {}}, **ids)
        else:
            j.append("t", E.DISPATCH_STARTED, "d", {"dispatch": 1, "before": {}}, **ids)
            if bad == "commit_without_verification":
                j.append("t", E.ACTION_COMMITTED, "c", {}, **ids)
            else:
                j.append("t", E.OBSERVED_AFTER, "o", {"observations": []}, **ids)
                j.append("t", E.VERIFICATION_RECORDED, "v", {"outcome": "VERIFIED_FAILURE"}, **ids)
                j.append("t", E.ACTION_COMMITTED, "c", {}, **ids)
    with pytest.raises(JournalIntegrityError):
        replay(j.events("t"))
    j.close()
