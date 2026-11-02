from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.storage.database import Database

_AGENT_NAMESPACE = uuid.UUID("4f8f1f41-91b3-4cc4-90f8-91a5f3628209")


class DuplicateSpecError(Exception):
    """Raised when an agent version already exists."""


class SpecNotFoundError(Exception):
    """Raised when a requested agent version does not exist."""


@dataclass(frozen=True, slots=True)
class AgentSpecRecord:
    agent_id: str
    spec: AgentSpec
    digest: str
    created_at: datetime


class SpecStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, spec: AgentSpec) -> AgentSpecRecord:
        agent_id = agent_id_for_name(spec.name)
        created_at = datetime.now(UTC)
        timestamp = created_at.isoformat()
        try:
            with self._database.connection:
                self._database.connection.execute(
                    """
                    INSERT INTO agents(agent_id, name, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(agent_id) DO NOTHING
                    """,
                    (agent_id, spec.name, timestamp),
                )
                self._database.connection.execute(
                    """
                    INSERT INTO agent_specs(agent_id, version, digest, spec_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id,
                        spec.version,
                        spec.digest(),
                        spec.model_dump_json(),
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateSpecError(
                f"{spec.name} version {spec.version} already exists"
            ) from error

        return AgentSpecRecord(
            agent_id=agent_id,
            spec=spec,
            digest=spec.digest(),
            created_at=created_at,
        )

    def get(self, agent_id: str, version: str) -> AgentSpecRecord:
        row = self._database.connection.execute(
            """
            SELECT agent_id, digest, spec_json, created_at
            FROM agent_specs
            WHERE agent_id = ? AND version = ?
            """,
            (agent_id, version),
        ).fetchone()
        if row is None:
            raise SpecNotFoundError(f"agent {agent_id} version {version} does not exist")
        return _record_from_row(row)

    def list(self) -> list[AgentSpecRecord]:
        rows = self._database.connection.execute(
            """
            SELECT agent_id, digest, spec_json, created_at
            FROM agent_specs
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [_record_from_row(row) for row in rows]


def agent_id_for_name(name: str) -> str:
    normalized_name = name.strip().casefold()
    return f"agent_{uuid.uuid5(_AGENT_NAMESPACE, normalized_name).hex}"


def _record_from_row(row: sqlite3.Row) -> AgentSpecRecord:
    return AgentSpecRecord(
        agent_id=row["agent_id"],
        spec=AgentSpec.model_validate_json(row["spec_json"]),
        digest=row["digest"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
