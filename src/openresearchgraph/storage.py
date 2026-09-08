from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .state import ResearchEvent, ResearchState, RunStatus, utc_now


class Repository:
    """Small SQLite repository for runs, events, checkpoints, memories, and demo data."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS research_runs (
            run_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            status TEXT NOT NULL,
            state_json TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_checkpoints (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            node TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES research_runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_checkpoints_run
            ON research_checkpoints(run_id, checkpoint_id DESC);
        CREATE TABLE IF NOT EXISTS research_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            role TEXT,
            message TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES research_runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_events_run
            ON research_events(run_id, sequence);
        CREATE TABLE IF NOT EXISTS short_memories (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            preferences_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS long_memories (
            memory_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS industry_metrics (
            sector TEXT NOT NULL,
            year INTEGER NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            PRIMARY KEY(sector, year, metric)
        );
        CREATE TABLE IF NOT EXISTS industry_observations (
            sector TEXT NOT NULL,
            region TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            effort_low INTEGER NOT NULL,
            effort_high INTEGER NOT NULL,
            PRIMARY KEY(sector, region, year, month, metric)
        );
        """
        seed_rows = [
            ("battery_storage", 2022, "installed_capacity", 13.1, "GWh"),
            ("battery_storage", 2023, "installed_capacity", 21.5, "GWh"),
            ("battery_storage", 2024, "installed_capacity", 34.7, "GWh"),
            ("thermal_storage", 2022, "installed_capacity", 4.2, "GWh"),
            ("thermal_storage", 2023, "installed_capacity", 5.1, "GWh"),
            ("thermal_storage", 2024, "installed_capacity", 6.6, "GWh"),
        ]
        observation_rows = [
            ("battery_storage", "north", 2023, 1, "installed_capacity", 4.6, "GWh", 5, 18),
            ("battery_storage", "north", 2023, 2, "installed_capacity", 5.1, "GWh", 6, 20),
            ("battery_storage", "south", 2023, 1, "installed_capacity", 5.7, "GWh", 8, 24),
            ("battery_storage", "south", 2023, 2, "installed_capacity", 6.1, "GWh", 8, 26),
            ("battery_storage", "north", 2024, 1, "installed_capacity", 7.9, "GWh", 7, 22),
            ("battery_storage", "north", 2024, 2, "installed_capacity", 8.7, "GWh", 9, 28),
            ("battery_storage", "south", 2024, 1, "installed_capacity", 8.4, "GWh", 10, 30),
            ("battery_storage", "south", 2024, 2, "installed_capacity", 9.7, "GWh", 10, 30),
            ("thermal_storage", "north", 2023, 1, "installed_capacity", 1.1, "GWh", 5, 12),
            ("thermal_storage", "north", 2023, 2, "installed_capacity", 1.3, "GWh", 5, 14),
            ("thermal_storage", "south", 2023, 1, "installed_capacity", 1.2, "GWh", 6, 15),
            ("thermal_storage", "south", 2023, 2, "installed_capacity", 1.5, "GWh", 6, 16),
            ("thermal_storage", "north", 2024, 1, "installed_capacity", 1.5, "GWh", 6, 16),
            ("thermal_storage", "north", 2024, 2, "installed_capacity", 1.7, "GWh", 6, 18),
            ("thermal_storage", "south", 2024, 1, "installed_capacity", 1.6, "GWh", 7, 19),
            ("thermal_storage", "south", 2024, 2, "installed_capacity", 1.8, "GWh", 7, 20),
        ]
        with self._lock, self._connection() as connection:
            connection.executescript(schema)
            connection.executemany(
                """INSERT OR IGNORE INTO industry_metrics
                (sector, year, metric, value, unit) VALUES (?, ?, ?, ?, ?)""",
                seed_rows,
            )
            connection.executemany(
                """INSERT OR IGNORE INTO industry_observations
                (sector, region, year, month, metric, value, unit, effort_low, effort_high)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                observation_rows,
            )

    def create_run(self, state: ResearchState) -> None:
        encoded = json.dumps(state, ensure_ascii=False)
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO research_runs
                (run_id, query, status, state_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    state["run_id"],
                    state["query"],
                    state["status"],
                    encoded,
                    state.get("error"),
                    state["created_at"],
                    state["updated_at"],
                ),
            )

    def update_run(self, state: ResearchState) -> None:
        state["updated_at"] = utc_now()
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE research_runs
                SET status=?, state_json=?, error=?, updated_at=? WHERE run_id=?""",
                (
                    state["status"],
                    json.dumps(state, ensure_ascii=False),
                    state.get("error"),
                    state["updated_at"],
                    state["run_id"],
                ),
            )

    def get_run(self, run_id: str) -> ResearchState | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT state_json FROM research_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT run_id, query, status, error, created_at, updated_at
                FROM research_runs ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_checkpoint(self, state: ResearchState, node: str) -> int:
        encoded = json.dumps(state, ensure_ascii=False)
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO research_checkpoints
                (run_id, node, state_json, created_at) VALUES (?, ?, ?, ?)""",
                (state["run_id"], node, encoded, utc_now()),
            )
            checkpoint_id = int(cursor.lastrowid)
        self.update_run(state)
        return checkpoint_id

    def latest_checkpoint(self, run_id: str) -> ResearchState | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT state_json FROM research_checkpoints
                WHERE run_id=? ORDER BY checkpoint_id DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
        return json.loads(row["state_json"]) if row else self.get_run(run_id)

    def append_event(self, event: ResearchEvent) -> ResearchEvent:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO research_events
                (run_id, kind, role, message, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.run_id,
                    event.kind,
                    event.role.value if event.role else None,
                    event.message,
                    json.dumps(event.data, ensure_ascii=False),
                    event.created_at,
                ),
            )
            event.sequence = int(cursor.lastrowid)
        return event

    def events_after(self, run_id: str, sequence: int = 0) -> list[ResearchEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT sequence, run_id, kind, role, message, data_json, created_at
                FROM research_events WHERE run_id=? AND sequence>?
                ORDER BY sequence ASC""",
                (run_id, sequence),
            ).fetchall()
        return [
            ResearchEvent(
                sequence=row["sequence"],
                run_id=row["run_id"],
                kind=row["kind"],
                role=row["role"],
                message=row["message"],
                data=json.loads(row["data_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def upsert_short_memory(
        self, session_id: str, summary: str, preferences: dict[str, Any]
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO short_memories
                (session_id, summary, preferences_json, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                summary=excluded.summary,
                preferences_json=excluded.preferences_json,
                updated_at=excluded.updated_at""",
                (session_id, summary, json.dumps(preferences, ensure_ascii=False), utc_now()),
            )

    def get_short_memory(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT summary, preferences_json, updated_at FROM short_memories
                WHERE session_id=?""",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "summary": row["summary"],
            "preferences": json.loads(row["preferences_json"]),
            "updated_at": row["updated_at"],
        }

    def put_long_memory(
        self,
        memory_id: str,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO long_memories
                (memory_id, content, embedding_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    memory_id,
                    content,
                    json.dumps(embedding),
                    json.dumps(metadata, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def all_long_memories(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT memory_id, content, embedding_json, metadata_json FROM long_memories"
            ).fetchall()
        return [
            {
                "memory_id": row["memory_id"],
                "content": row["content"],
                "embedding": json.loads(row["embedding_json"]),
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def mark_failed(self, state: ResearchState, error: str) -> None:
        state["status"] = RunStatus.FAILED
        state["error"] = error
        self.update_run(state)
