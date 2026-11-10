from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_crossbar.domain.worker import WorkerCreate
from agent_crossbar.storage.database import Database


class WorkerNotFoundError(Exception):
    """Raised when a requested worker is not registered."""


@dataclass(frozen=True, slots=True)
class WorkerRecord:
    worker_id: str
    label: str
    base_url: str
    agent_id: str
    spec_version: str
    credential_ref: str
    max_concurrency: int
    timeout_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class WorkerStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, value: WorkerCreate) -> WorkerRecord:
        worker_id = f"worker_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO workers(
                    worker_id, label, base_url, agent_id, spec_version,
                    credential_ref, max_concurrency, timeout_seconds, enabled,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    worker_id,
                    value.label,
                    value.base_url,
                    value.agent_id,
                    value.version,
                    value.credential_ref,
                    value.max_concurrency,
                    value.timeout_seconds,
                    int(value.enabled),
                    now,
                    now,
                ),
            )
        return self.get(worker_id)

    def get(self, worker_id: str) -> WorkerRecord:
        row = self._database.connection.execute(
            """
            SELECT worker_id, label, base_url, agent_id, spec_version,
                   credential_ref, max_concurrency, timeout_seconds, enabled,
                   created_at, updated_at
            FROM workers
            WHERE worker_id = ?
            """,
            (worker_id,),
        ).fetchone()
        if row is None:
            raise WorkerNotFoundError(f"worker {worker_id} does not exist")
        return _worker_from_row(row)

    def list(self) -> list[WorkerRecord]:
        rows = self._database.connection.execute(
            """
            SELECT worker_id, label, base_url, agent_id, spec_version,
                   credential_ref, max_concurrency, timeout_seconds, enabled,
                   created_at, updated_at
            FROM workers
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [_worker_from_row(row) for row in rows]

    def find_enabled(self, agent_id: str, version: str) -> WorkerRecord | None:
        rows = self.list_enabled(agent_id, version)
        return rows[0] if rows else None

    def list_enabled(self, agent_id: str, version: str) -> list[WorkerRecord]:
        rows = self._database.connection.execute(
            """
            SELECT worker_id, label, base_url, agent_id, spec_version,
                   credential_ref, max_concurrency, timeout_seconds, enabled,
                   created_at, updated_at
            FROM workers
            WHERE agent_id = ? AND spec_version = ? AND enabled = 1
            ORDER BY created_at ASC, rowid ASC
            """,
            (agent_id, version),
        ).fetchall()
        return [_worker_from_row(row) for row in rows]

    def set_enabled(self, worker_id: str, enabled: bool) -> WorkerRecord:
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                "UPDATE workers SET enabled = ?, updated_at = ? WHERE worker_id = ?",
                (int(enabled), now, worker_id),
            )
        if cursor.rowcount != 1:
            raise WorkerNotFoundError(f"worker {worker_id} does not exist")
        return self.get(worker_id)

    def delete(self, worker_id: str) -> None:
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                "DELETE FROM workers WHERE worker_id = ?",
                (worker_id,),
            )
        if cursor.rowcount != 1:
            raise WorkerNotFoundError(f"worker {worker_id} does not exist")


def _worker_from_row(row: sqlite3.Row) -> WorkerRecord:
    return WorkerRecord(
        worker_id=row["worker_id"],
        label=row["label"],
        base_url=row["base_url"],
        agent_id=row["agent_id"],
        spec_version=row["spec_version"],
        credential_ref=row["credential_ref"],
        max_concurrency=row["max_concurrency"],
        timeout_seconds=row["timeout_seconds"],
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
