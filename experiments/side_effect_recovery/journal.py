"""Append-only task journal for the side-effect protocol.

The journal is the only thing that survives a crash. Every write is committed
immediately, because anything still in a buffer when the process dies did not
happen as far as recovery is concerned.

Lifecycle recorded here (END_TO_END_SYSTEM_SPEC sections 4.5-4.7):

    OBSERVED -> INTENT_PREPARED -> INTENT_DISPATCHED -> ACTION_RESULT
             -> VERIFICATION -> INTENT_COMPLETED

The single load-bearing ordering rule:

    INTENT_DISPATCHED is committed BEFORE the browser is touched.

That is what makes the post-crash state machine decidable. Without it, a
PREPARED intent would be indistinguishable from an executed one.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional


class Journal:
    def __init__(self, path: str):
        self.path = path
        c = self._conn()
        c.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   seq INTEGER PRIMARY KEY AUTOINCREMENT,
                   t REAL, kind TEXT, intent_id TEXT, payload TEXT)"""
        )
        c.commit()
        c.close()

    def _conn(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        return c

    def append(self, kind: str, intent_id: Optional[str] = None, **payload):
        c = self._conn()
        try:
            c.execute(
                "INSERT INTO events(t, kind, intent_id, payload) VALUES (?,?,?,?)",
                (time.time(), kind, intent_id, json.dumps(payload)),
            )
        finally:
            c.close()

    def events(self) -> list[dict]:
        c = self._conn()
        try:
            rows = c.execute(
                "SELECT seq, t, kind, intent_id, payload FROM events ORDER BY seq"
            ).fetchall()
        finally:
            c.close()
        return [
            {"seq": r[0], "t": r[1], "kind": r[2], "intent_id": r[3],
             "payload": json.loads(r[4])}
            for r in rows
        ]

    # ------------------------------------------------------------------

    def open_intent(self) -> Optional[dict]:
        """The most recent intent that has not reached a terminal state."""
        state: dict[str, dict] = {}
        for e in self.events():
            iid = e["intent_id"]
            if not iid:
                continue
            s = state.setdefault(iid, {"intent_id": iid, "status": None, "data": {}})
            if e["kind"] == "INTENT_PREPARED":
                s["status"] = "PREPARED"
                s["data"] = e["payload"]
            elif e["kind"] == "INTENT_DISPATCHED":
                s["status"] = "DISPATCHED"
            elif e["kind"] == "ACTION_RESULT":
                s["status"] = "RESULT_RECORDED"
                s["result"] = e["payload"]
            elif e["kind"] == "VERIFICATION":
                s["status"] = "VERIFIED"
                s["verification"] = e["payload"]
            elif e["kind"] == "INTENT_COMPLETED":
                s["status"] = "COMPLETED"
            elif e["kind"] == "INTENT_ABANDONED":
                s["status"] = "ABANDONED"
        for iid in reversed(list(state)):
            if state[iid]["status"] not in ("COMPLETED", "ABANDONED"):
                return state[iid]
        return None
