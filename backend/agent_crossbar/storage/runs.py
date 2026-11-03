from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.storage.database import Database


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    }
)


class RunNotFoundError(Exception):
    """Raised when a requested run does not exist."""


class DuplicateEventError(Exception):
    """Raised when a run event sequence has already been persisted."""


class RunStateError(Exception):
    """Raised when a run status transition is not allowed."""


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    agent_id: str
    spec_version: str
    input_text: str
    status: RunStatus
    output: str | None
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, *, agent_id: str, spec_version: str, input_text: str) -> RunRecord:
        run_id = f"run_{uuid.uuid4().hex}"
        now = datetime.now(UTC)
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO runs(run_id, agent_id, spec_version, input_text, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    agent_id,
                    spec_version,
                    input_text,
                    RunStatus.QUEUED.value,
                    now.isoformat(),
                ),
            )
        return self.get(run_id)

    def get(self, run_id: str) -> RunRecord:
        row = self._database.connection.execute(
            """
            SELECT run_id, agent_id, spec_version, input_text, status, output, error_json,
                   created_at, started_at, finished_at
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise RunNotFoundError(f"run {run_id} does not exist")
        return _run_from_row(row)

    def list(self, *, limit: int = 100) -> list[RunRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = self._database.connection.execute(
            """
            SELECT run_id, agent_id, spec_version, input_text, status, output, error_json,
                   created_at, started_at, finished_at
            FROM runs
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_run_from_row(row) for row in rows]

    def mark_running(self, run_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE runs
                SET status = ?, started_at = ?
                WHERE run_id = ? AND status = ?
                """,
                (RunStatus.RUNNING.value, now, run_id, RunStatus.QUEUED.value),
            )
        if cursor.rowcount != 1:
            current = self.get(run_id)
            raise RunStateError(f"run {run_id} cannot start from status {current.status.value}")

    def mark_terminal(
        self,
        run_id: str,
        status: RunStatus,
        *,
        output: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if status not in TERMINAL_RUN_STATUSES:
            raise ValueError(f"{status.value} is not a terminal run status")
        now = datetime.now(UTC).isoformat()
        error_json = (
            json.dumps(error, ensure_ascii=False, sort_keys=True) if error is not None else None
        )
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE runs
                SET status = ?, output = ?, error_json = ?, finished_at = ?
                WHERE run_id = ? AND status IN (?, ?)
                """,
                (
                    status.value,
                    output,
                    error_json,
                    now,
                    run_id,
                    RunStatus.QUEUED.value,
                    RunStatus.RUNNING.value,
                ),
            )
        if cursor.rowcount != 1:
            current = self.get(run_id)
            raise RunStateError(
                f"run {run_id} cannot transition from {current.status.value} to {status.value}"
            )

    def append_event(self, run_id: str, event: RuntimeEvent) -> None:
        if event.run_id != run_id:
            raise ValueError("event run_id must match the target run")
        usage_json = (
            event.usage.model_dump_json() if event.usage is not None else None
        )
        try:
            with self._database.write_lock, self._database.connection:
                self._database.connection.execute(
                    """
                    INSERT INTO run_events(
                        run_id, sequence, type, timestamp, step_id, correlation_id,
                        payload_json, usage_json, cost_usd
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        event.sequence,
                        event.type.value,
                        event.timestamp.isoformat(),
                        event.step_id,
                        event.correlation_id,
                        json.dumps(
                            event.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        usage_json,
                        str(event.cost_usd) if event.cost_usd is not None else None,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateEventError(
                f"run {run_id} already has event sequence {event.sequence}"
            ) from error

    def list_events(self, run_id: str, *, after_sequence: int = 0) -> list[RuntimeEvent]:
        rows = self._database.connection.execute(
            """
            SELECT run_id, sequence, type, timestamp, step_id, correlation_id,
                   payload_json, usage_json, cost_usd
            FROM run_events
            WHERE run_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (run_id, after_sequence),
        ).fetchall()
        return [_event_from_row(row) for row in rows]


def _run_from_row(row: sqlite3.Row) -> RunRecord:
    error = json.loads(row["error_json"]) if row["error_json"] is not None else None
    return RunRecord(
        run_id=row["run_id"],
        agent_id=row["agent_id"],
        spec_version=row["spec_version"],
        input_text=row["input_text"],
        status=RunStatus(row["status"]),
        output=row["output"],
        error=error,
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=(
            datetime.fromisoformat(row["started_at"]) if row["started_at"] is not None else None
        ),
        finished_at=(
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] is not None else None
        ),
    )


def _event_from_row(row: sqlite3.Row) -> RuntimeEvent:
    return RuntimeEvent.model_validate(
        {
            "run_id": row["run_id"],
            "sequence": row["sequence"],
            "type": RuntimeEventType(row["type"]),
            "timestamp": row["timestamp"],
            "step_id": row["step_id"],
            "correlation_id": row["correlation_id"],
            "payload": json.loads(row["payload_json"]),
            "usage": json.loads(row["usage_json"]) if row["usage_json"] is not None else None,
            "cost_usd": Decimal(row["cost_usd"]) if row["cost_usd"] is not None else None,
        }
    )
