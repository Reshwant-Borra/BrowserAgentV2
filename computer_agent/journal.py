"""Durable append-only event journal (M3): SQLite, WAL mode, synchronous=FULL.

See `docs/DECISIONS.md` D-019. The journal is recovery truth: controller
state is rebuilt by folding its events (`computer_agent.state.replay`),
never from in-memory pre-crash state or model context.

Every `append` is its own committed transaction before it returns, so an
event the controller has "written" survives process death. Each event has a
deterministic `event_id` (UNIQUE): recording the same logical lifecycle
event twice -- e.g. a second DISPATCH_STARTED for the same action attempt --
is rejected with `DuplicateEvent` instead of silently doubling history.

Opaque live `ExecutionRef`s and model state are never persisted; payloads
are compact JSON (semantic TargetSpec, args, observed state, verdicts).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .verification import Indeterminate

SCHEMA_VERSION = 1


class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    OBSERVED = "OBSERVED"
    TARGET_RESOLVED = "TARGET_RESOLVED"
    TARGET_REJECTED = "TARGET_REJECTED"
    POLICY_ALLOWED = "POLICY_ALLOWED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    ACTION_INTENT_PERSISTED = "ACTION_INTENT_PERSISTED"
    FRESHNESS_PASSED = "FRESHNESS_PASSED"
    FRESHNESS_FAILED = "FRESHNESS_FAILED"
    ACTION_ABANDONED = "ACTION_ABANDONED"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    DISPATCH_RETURNED = "DISPATCH_RETURNED"
    OBSERVED_AFTER = "OBSERVED_AFTER"
    VERIFICATION_RECORDED = "VERIFICATION_RECORDED"
    OUTCOME_RECONCILED = "OUTCOME_RECONCILED"
    ACTION_COMMITTED = "ACTION_COMMITTED"
    ACTION_FAILED = "ACTION_FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_BLOCKED = "STEP_BLOCKED"
    TASK_COMPLETED = "TASK_COMPLETED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    STATE_RECONSTRUCTED = "STATE_RECONSTRUCTED"


class DuplicateEvent(Exception):
    pass


class SchemaVersionError(Exception):
    pass


@dataclass(frozen=True)
class Event:
    seq: int
    event_id: str
    task_id: str
    type: EventType
    step_id: str | None
    action_id: str | None
    payload: dict[str, Any]
    schema_version: int


def _encode(value: Any) -> Any:
    if isinstance(value, Indeterminate):
        return {"__indeterminate__": value.reason}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__indeterminate__"}:
            return Indeterminate(value["__indeterminate__"])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL,
    step_id TEXT,
    action_id TEXT,
    payload TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_task ON events (task_id, seq);
"""


class Journal:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._db = sqlite3.connect(self.path, isolation_level=None)  # explicit transactions only
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_DDL)
        row = self._db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            self._db.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        elif int(row[0]) != SCHEMA_VERSION:
            raise SchemaVersionError(f"journal schema {row[0]} != supported {SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    def append(
        self,
        task_id: str,
        type: EventType,
        event_id: str,
        payload: dict[str, Any] | None = None,
        *,
        step_id: str | None = None,
        action_id: str | None = None,
    ) -> None:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute(
                "INSERT INTO events (event_id, task_id, type, step_id, action_id, payload, schema_version,"
                " recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, task_id, type.value, step_id, action_id,
                 json.dumps(_encode(payload or {}), sort_keys=True), SCHEMA_VERSION, time.time()),
            )
            self._db.execute("COMMIT")
        except sqlite3.IntegrityError:
            self._db.execute("ROLLBACK")
            raise DuplicateEvent(event_id) from None

    def next_seq(self) -> int:
        return (self._db.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]) + 1

    def events(self, task_id: str) -> list[Event]:
        rows = self._db.execute(
            "SELECT seq, event_id, task_id, type, step_id, action_id, payload, schema_version"
            " FROM events WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()
        return [Event(s, e, t, EventType(ty), st, a, _decode(json.loads(p)), v) for s, e, t, ty, st, a, p, v in rows]

    def events_since(self, task_id: str, since_seq: int) -> list[Event]:
        """Events for `task_id` strictly after `since_seq`, in order.

        Lets a caller that already holds a `TaskState` materialized through
        `since_seq` (see `computer_agent.state.advance`) fetch and fold only
        what changed, instead of re-reading and re-replaying full history.
        """
        rows = self._db.execute(
            "SELECT seq, event_id, task_id, type, step_id, action_id, payload, schema_version"
            " FROM events WHERE task_id=? AND seq>? ORDER BY seq", (task_id, since_seq)).fetchall()
        return [Event(s, e, t, EventType(ty), st, a, _decode(json.loads(p)), v) for s, e, t, ty, st, a, p, v in rows]
