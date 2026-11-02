from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1


def migrate(connection: sqlite3.Connection) -> None:
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"database schema version {current_version} is newer than supported "
            f"version {SCHEMA_VERSION}"
        )
    if current_version == 0:
        _migration_one(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()


def _migration_one(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE agents (
            agent_id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE agent_specs (
            agent_id TEXT NOT NULL,
            version TEXT NOT NULL,
            digest TEXT NOT NULL,
            spec_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (agent_id, version),
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
        );

        CREATE INDEX agent_specs_created_at_idx
        ON agent_specs(created_at DESC);
        """
    )
