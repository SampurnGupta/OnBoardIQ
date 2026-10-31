"""Storage backends for the Blackboard Service.

SQLite for local development, Firestore for cloud deployment,
behind a common repository interface.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from onboardiq.schema import (
    Blackboard,
    GuardrailEvent,
)


class BlackboardError(Exception):
    """Base exception for blackboard storage errors."""


class RunNotFoundError(BlackboardError):
    """Raised when a run_id does not exist."""


class VersionMismatchError(BlackboardError):
    """Raised when expected_version does not match current version (optimistic concurrency)."""

    def __init__(self, current_version: int, expected_version: int):
        super().__init__(
            f"Version conflict: current version is {current_version}, expected {expected_version}"
        )
        self.current_version = current_version
        self.expected_version = expected_version


class BlackboardStore(ABC):
    """Abstract repository for storing Blackboard state and events."""

    @abstractmethod
    def create_run(self, board: Blackboard) -> Blackboard:
        """Create and store an initial Blackboard run."""

    @abstractmethod
    def get_run(self, run_id: str) -> Blackboard | None:
        """Retrieve full Blackboard state for a run."""

    @abstractmethod
    def apply_event(
        self,
        run_id: str,
        agent_id: str,
        zone: str,
        op: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> tuple[Blackboard, dict[str, Any]]:
        """Atomically apply a zone update, bump version, and append to the event log."""

    @abstractmethod
    def append_guardrail_event(self, run_id: str, event: GuardrailEvent) -> None:
        """Record a security guardrail event into the system zone without version checks."""

    @abstractmethod
    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        """Retrieve immutable event history in ascending chronological order."""


class SQLiteBlackboardStore(BlackboardStore):
    """SQLite implementation of BlackboardStore.

    Maintains run snapshots and an append-only event log.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._memory_conn = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if db_path == ":memory:"
            else None
        )
        if self._memory_conn:
            self._memory_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._memory_conn:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    zone TEXT NOT NULL,
                    op TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                """
            )

    def create_run(self, board: Blackboard) -> Blackboard:
        now_iso = datetime.now(UTC).isoformat()
        board_data = board.model_dump_json()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, version, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (board.run_id, board.version, board_data, now_iso, now_iso),
            )
            initial_event_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO events (event_id, run_id, agent_id, zone, op, payload, timestamp, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial_event_id,
                    board.run_id,
                    "system.init",
                    "all",
                    "init",
                    json.dumps({"mode": board.mode.value, "pattern": board.pattern.value}),
                    now_iso,
                    board.version,
                ),
            )
        return board

    def get_run(self, run_id: str) -> Blackboard | None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute("SELECT data FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Blackboard.model_validate_json(row["data"])

    def apply_event(
        self,
        run_id: str,
        agent_id: str,
        zone: str,
        op: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> tuple[Blackboard, dict[str, Any]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT version, data FROM runs WHERE run_id = ?", (run_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise RunNotFoundError(f"Run {run_id} not found")

            current_version = row["version"]
            if current_version != expected_version:
                raise VersionMismatchError(
                    current_version=current_version, expected_version=expected_version
                )

            board_dict = json.loads(row["data"])

            # Apply zone update to current state
            if zone not in board_dict:
                raise BlackboardError(f"Unknown zone '{zone}' on blackboard")

            if op == "replace":
                board_dict[zone] = payload
            elif op == "update":
                if isinstance(board_dict[zone], dict):
                    board_dict[zone].update(payload)
                else:
                    board_dict[zone] = payload
            elif op == "append":
                # For list fields inside a zone or list zone
                target_field = payload.get("field")
                item = payload.get("item")
                if target_field and isinstance(board_dict[zone], dict):
                    board_dict[zone].setdefault(target_field, []).append(item)
                else:
                    raise BlackboardError("Append op requires 'field' and 'item' in payload")
            else:
                # Default behavior: merge dict or set
                board_dict[zone] = payload

            # Increment version
            new_version = current_version + 1
            board_dict["version"] = new_version

            # Validate against Pydantic schema
            updated_board = Blackboard.model_validate(board_dict)
            now_iso = datetime.now(UTC).isoformat()
            event_id = str(uuid.uuid4())

            event_record = {
                "event_id": event_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "zone": zone,
                "op": op,
                "payload": payload,
                "timestamp": now_iso,
                "version": new_version,
            }

            conn.execute(
                """
                UPDATE runs
                SET version = ?, data = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (new_version, updated_board.model_dump_json(), now_iso, run_id),
            )
            conn.execute(
                """
                INSERT INTO events (event_id, run_id, agent_id, zone, op, payload, timestamp, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    agent_id,
                    zone,
                    op,
                    json.dumps(payload),
                    now_iso,
                    new_version,
                ),
            )

            return updated_board, event_record

    def append_guardrail_event(self, run_id: str, event: GuardrailEvent) -> None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT version, data FROM runs WHERE run_id = ?", (run_id,)
            )
            row = cursor.fetchone()
            if not row:
                return

            current_version = row["version"]
            board_dict = json.loads(row["data"])

            system_zone = board_dict.setdefault("system", {})
            events_list = system_zone.setdefault("guardrail_events", [])
            events_list.append(event.model_dump(mode="json"))

            updated_board = Blackboard.model_validate(board_dict)
            now_iso = datetime.now(UTC).isoformat()

            conn.execute(
                """
                UPDATE runs
                SET data = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (updated_board.model_dump_json(), now_iso, run_id),
            )

            conn.execute(
                """
                INSERT INTO events (event_id, run_id, agent_id, zone, op, payload, timestamp, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    run_id,
                    event.agent_id,
                    "system",
                    "guardrail_event",
                    event.model_dump_json(),
                    now_iso,
                    current_version,
                ),
            )

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT event_id, run_id, agent_id, zone, op, payload, timestamp, version
                FROM events
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            )
            records = []
            for row in cursor.fetchall():
                payload = json.loads(row["payload"]) if row["payload"] else {}
                records.append(
                    {
                        "event_id": row["event_id"],
                        "run_id": row["run_id"],
                        "agent_id": row["agent_id"],
                        "zone": row["zone"],
                        "op": row["op"],
                        "payload": payload,
                        "timestamp": row["timestamp"],
                        "version": row["version"],
                    }
                )
            return records
