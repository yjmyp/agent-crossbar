from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_crossbar.domain.evaluation import (
    EvaluationDataset,
    EvaluationStatus,
)
from agent_crossbar.storage.database import Database


class DatasetNotFoundError(Exception):
    """Raised when an evaluation dataset does not exist."""


class DuplicateDatasetError(Exception):
    """Raised when a dataset name and version already exist."""


class DatasetInUseError(Exception):
    """Raised when attempting to delete a dataset referenced by a batch."""


class EvaluationBatchNotFoundError(Exception):
    """Raised when an evaluation batch does not exist."""


class EvaluationCaseNotFoundError(Exception):
    """Raised when a case result does not exist in a batch."""


@dataclass(frozen=True, slots=True)
class EvaluationDatasetRecord:
    dataset_id: str
    dataset: EvaluationDataset
    digest: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    case_id: str
    case_name: str
    status: EvaluationStatus
    run_id: str | None
    latency_ms: int | None
    output: str | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class EvaluationBatchRecord:
    batch_id: str
    dataset_id: str
    agent_id: str
    spec_version: str
    baseline_batch_id: str | None
    status: EvaluationStatus
    gate_status: str
    metrics: dict[str, Any]
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    results: tuple[EvaluationCaseResult, ...]


class EvaluationStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create_dataset(self, dataset: EvaluationDataset) -> EvaluationDatasetRecord:
        dataset_id = f"dataset_{uuid.uuid4().hex}"
        created_at = datetime.now(UTC)
        try:
            with self._database.write_lock, self._database.connection:
                self._database.connection.execute(
                    """
                    INSERT INTO evaluation_datasets(
                        dataset_id, name, version, description, cases_json, digest, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        dataset.name,
                        dataset.version,
                        dataset.description,
                        dataset.model_dump_json(),
                        dataset.digest(),
                        created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateDatasetError(
                f"{dataset.name} version {dataset.version} already exists"
            ) from error
        return EvaluationDatasetRecord(
            dataset_id=dataset_id,
            dataset=dataset,
            digest=dataset.digest(),
            created_at=created_at,
        )

    def get_dataset(self, dataset_id: str) -> EvaluationDatasetRecord:
        row = self._database.connection.execute(
            """
            SELECT dataset_id, cases_json, digest, created_at
            FROM evaluation_datasets
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchone()
        if row is None:
            raise DatasetNotFoundError(f"evaluation dataset {dataset_id} does not exist")
        return _dataset_from_row(row)

    def list_datasets(self) -> list[EvaluationDatasetRecord]:
        rows = self._database.connection.execute(
            """
            SELECT dataset_id, cases_json, digest, created_at
            FROM evaluation_datasets
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [_dataset_from_row(row) for row in rows]

    def delete_dataset(self, dataset_id: str) -> None:
        self.get_dataset(dataset_id)
        count = self._database.connection.execute(
            "SELECT COUNT(*) FROM evaluation_batches WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()[0]
        if count:
            raise DatasetInUseError(
                f"evaluation dataset {dataset_id} is referenced by {count} batch(es)"
            )
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                "DELETE FROM evaluation_datasets WHERE dataset_id = ?",
                (dataset_id,),
            )

    def create_batch(
        self,
        *,
        dataset_id: str,
        agent_id: str,
        spec_version: str,
        baseline_batch_id: str | None = None,
    ) -> EvaluationBatchRecord:
        dataset = self.get_dataset(dataset_id)
        if baseline_batch_id is not None:
            baseline = self.get_batch(baseline_batch_id)
            if baseline.dataset_id != dataset_id:
                raise ValueError("baseline batch must use the same evaluation dataset")

        batch_id = f"eval_{uuid.uuid4().hex}"
        created_at = datetime.now(UTC)
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO evaluation_batches(
                    batch_id, dataset_id, agent_id, spec_version, baseline_batch_id,
                    status, gate_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    dataset_id,
                    agent_id,
                    spec_version,
                    baseline_batch_id,
                    EvaluationStatus.QUEUED.value,
                    "not_evaluated",
                    created_at.isoformat(),
                ),
            )
            self._database.connection.executemany(
                """
                INSERT INTO evaluation_case_results(batch_id, case_id, case_name, status)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        batch_id,
                        case.case_id,
                        case.name,
                        EvaluationStatus.PENDING.value,
                    )
                    for case in dataset.dataset.cases
                ],
            )
        return self.get_batch(batch_id)

    def get_batch(self, batch_id: str) -> EvaluationBatchRecord:
        row = self._database.connection.execute(
            """
            SELECT batch_id, dataset_id, agent_id, spec_version, baseline_batch_id,
                   status, gate_status, metrics_json, error_json, created_at,
                   started_at, finished_at
            FROM evaluation_batches
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        if row is None:
            raise EvaluationBatchNotFoundError(
                f"evaluation batch {batch_id} does not exist"
            )
        result_rows = self._database.connection.execute(
            """
            SELECT case_id, case_name, status, run_id, latency_ms, output, failure_reason
            FROM evaluation_case_results
            WHERE batch_id = ?
            ORDER BY rowid ASC
            """,
            (batch_id,),
        ).fetchall()
        return _batch_from_rows(row, result_rows)

    def list_batches(self, *, limit: int = 100) -> list[EvaluationBatchRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = self._database.connection.execute(
            """
            SELECT batch_id
            FROM evaluation_batches
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self.get_batch(row["batch_id"]) for row in rows]

    def mark_batch_running(self, batch_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE evaluation_batches
                SET status = ?, started_at = ?
                WHERE batch_id = ? AND status = ?
                """,
                (
                    EvaluationStatus.RUNNING.value,
                    now,
                    batch_id,
                    EvaluationStatus.QUEUED.value,
                ),
            )
        if cursor.rowcount != 1:
            self.get_batch(batch_id)
            raise ValueError(f"evaluation batch {batch_id} cannot start")

    def update_case_result(
        self,
        batch_id: str,
        case_id: str,
        *,
        status: EvaluationStatus,
        run_id: str | None = None,
        latency_ms: int | None = None,
        output: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE evaluation_case_results
                SET status = ?, run_id = ?, latency_ms = ?, output = ?, failure_reason = ?
                WHERE batch_id = ? AND case_id = ?
                """,
                (
                    status.value,
                    run_id,
                    latency_ms,
                    output,
                    failure_reason,
                    batch_id,
                    case_id,
                ),
            )
        if cursor.rowcount != 1:
            raise EvaluationCaseNotFoundError(
                f"evaluation case {case_id} does not exist in batch {batch_id}"
            )

    def finish_batch(
        self,
        batch_id: str,
        *,
        status: EvaluationStatus,
        gate_status: str,
        metrics: dict[str, Any],
        error: dict[str, Any] | None = None,
    ) -> None:
        if status not in {
            EvaluationStatus.COMPLETED,
            EvaluationStatus.FAILED,
            EvaluationStatus.CANCELLED,
        }:
            raise ValueError(f"{status.value} is not a terminal evaluation status")
        if gate_status not in {"not_evaluated", "pass", "regression"}:
            raise ValueError(f"unsupported gate status {gate_status}")
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE evaluation_batches
                SET status = ?, gate_status = ?, metrics_json = ?, error_json = ?,
                    finished_at = ?
                WHERE batch_id = ? AND status = ?
                """,
                (
                    status.value,
                    gate_status,
                    json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                    (
                        json.dumps(error, ensure_ascii=False, sort_keys=True)
                        if error is not None
                        else None
                    ),
                    now,
                    batch_id,
                    EvaluationStatus.RUNNING.value,
                ),
            )
        if cursor.rowcount != 1:
            self.get_batch(batch_id)
            raise ValueError(f"evaluation batch {batch_id} cannot be finalized")


def _dataset_from_row(row: sqlite3.Row) -> EvaluationDatasetRecord:
    return EvaluationDatasetRecord(
        dataset_id=row["dataset_id"],
        dataset=EvaluationDataset.model_validate_json(row["cases_json"]),
        digest=row["digest"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _batch_from_rows(
    row: sqlite3.Row,
    result_rows: list[sqlite3.Row],
) -> EvaluationBatchRecord:
    return EvaluationBatchRecord(
        batch_id=row["batch_id"],
        dataset_id=row["dataset_id"],
        agent_id=row["agent_id"],
        spec_version=row["spec_version"],
        baseline_batch_id=row["baseline_batch_id"],
        status=EvaluationStatus(row["status"]),
        gate_status=row["gate_status"],
        metrics=json.loads(row["metrics_json"]) if row["metrics_json"] is not None else {},
        error=json.loads(row["error_json"]) if row["error_json"] is not None else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=(
            datetime.fromisoformat(row["started_at"]) if row["started_at"] is not None else None
        ),
        finished_at=(
            datetime.fromisoformat(row["finished_at"]) if row["finished_at"] is not None else None
        ),
        results=tuple(
            EvaluationCaseResult(
                case_id=result["case_id"],
                case_name=result["case_name"],
                status=EvaluationStatus(result["status"]),
                run_id=result["run_id"],
                latency_ms=result["latency_ms"],
                output=result["output"],
                failure_reason=result["failure_reason"],
            )
            for result in result_rows
        ),
    )
