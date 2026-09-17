from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Journal states.
#   RECEIVED   command written down, nothing actuated yet
#   ACTUATING  a physical action was started and has not reported back
#   COMPLETED  the physical action finished; terminal, never demoted
#   FAILED     the attempt stopped before or during execution and may be retried
RECEIVED = "RECEIVED"
ACTUATING = "ACTUATING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StoredCommand:
    command_id: str
    state: str
    payload: dict
    error: str | None
    result: dict | None = None


class EdgeStore:
    """Small durable journal used by the garage edge daemon.

    A command is written to SQLite before hardware execution. If the daemon
    crashes after hardware execution but before cloud ACK, the local COMPLETED
    state prevents a duplicate physical action when the cloud redelivers it.

    COMPLETED is terminal. A failure that happens *after* the coil pulse (a dead
    socket, a refused ACK) must never rewrite the journal to FAILED: the cloud
    would redeliver the command and the bay would open a second time with the
    courier already gone. ``mark_failed`` therefore refuses to demote a
    COMPLETED row, and the result of the completed action is stored so a
    redelivery can be answered from the journal instead of from the hardware.
    """

    def __init__(self, path: str = "edge-state.db"):
        self.path = str(Path(path))
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(commands)")}
            if "result_json" not in columns:
                conn.execute("ALTER TABLE commands ADD COLUMN result_json TEXT")

    @staticmethod
    def _row(row) -> StoredCommand:
        raw_result = row["result_json"] if "result_json" in row.keys() else None
        result = None
        if raw_result:
            try:
                result = json.loads(raw_result)
            except ValueError:
                result = None
        return StoredCommand(
            row["command_id"],
            row["state"],
            json.loads(row["payload_json"]),
            row["error"],
            result,
        )

    def remember(self, command_id: str, payload: dict) -> StoredCommand:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM commands WHERE command_id = ?", (command_id,)).fetchone()
            if row:
                return self._row(row)
            now = _now()
            conn.execute(
                "INSERT INTO commands(command_id,state,payload_json,received_at,updated_at) VALUES(?,?,?,?,?)",
                (command_id, RECEIVED, raw, now, now),
            )
        return StoredCommand(command_id, RECEIVED, payload, None, None)

    def mark_actuating(self, command_id: str) -> None:
        """Record that a physical action is about to start.

        A row left in ACTUATING means the daemon stopped mid-actuation. The
        outcome of that pulse is unknown, so the command is not replayed on the
        hardware; the daemon reports it as indeterminate instead.
        """
        with self._conn() as conn:
            conn.execute(
                "UPDATE commands SET state=?, updated_at=? WHERE command_id=? AND state<>?",
                (ACTUATING, _now(), command_id, COMPLETED),
            )

    def mark_completed(self, command_id: str, result: dict | None = None):
        raw_result = None
        if result is not None:
            try:
                raw_result = json.dumps(result, separators=(",", ":"), sort_keys=True, default=str)
            except (TypeError, ValueError):
                raw_result = None
        with self._conn() as conn:
            conn.execute(
                "UPDATE commands SET state=?, updated_at=?, error=NULL, result_json=? WHERE command_id=?",
                (COMPLETED, _now(), raw_result, command_id),
            )

    def mark_failed(self, command_id: str, error: str) -> bool:
        """Record a failure. Returns False when the row was already COMPLETED.

        A COMPLETED row describes a physical action that already happened; no
        later transport error may turn it back into work to redo.
        """
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE commands SET state=?, updated_at=?, error=? WHERE command_id=? AND state<>?",
                (FAILED, _now(), error[:1000], command_id, COMPLETED),
            )
            return cursor.rowcount > 0

    def get(self, command_id: str) -> StoredCommand | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM commands WHERE command_id = ?", (command_id,)).fetchone()
        if not row:
            return None
        return self._row(row)
