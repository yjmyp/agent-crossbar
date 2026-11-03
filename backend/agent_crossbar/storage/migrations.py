from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3


def migrate(connection: sqlite3.Connection) -> None:
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"database schema version {current_version} is newer than supported "
            f"version {SCHEMA_VERSION}"
        )
    if current_version < 1:
        _migration_one(connection)
    if current_version < 2:
        _migration_two(connection)
    if current_version < 3:
        _migration_three(connection)
    if current_version < SCHEMA_VERSION:
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


def _migration_two(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            spec_version TEXT NOT NULL,
            input_text TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN (
                    'queued',
                    'running',
                    'completed',
                    'failed',
                    'cancelled',
                    'interrupted'
                )
            ),
            output TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (agent_id, spec_version)
                REFERENCES agent_specs(agent_id, version)
        );

        CREATE INDEX runs_created_at_idx ON runs(created_at DESC);
        CREATE INDEX runs_agent_id_idx ON runs(agent_id, spec_version);

        CREATE TABLE run_events (
            run_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            step_id TEXT,
            correlation_id TEXT,
            payload_json TEXT NOT NULL,
            usage_json TEXT,
            cost_usd TEXT,
            PRIMARY KEY (run_id, sequence),
            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE INDEX run_events_type_idx ON run_events(run_id, type);
        """
    )


def _migration_three(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE evaluation_datasets (
            dataset_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT NOT NULL,
            cases_json TEXT NOT NULL,
            digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(name, version)
        );

        CREATE INDEX evaluation_datasets_created_at_idx
        ON evaluation_datasets(created_at DESC);

        CREATE TABLE evaluation_batches (
            batch_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            spec_version TEXT NOT NULL,
            baseline_batch_id TEXT,
            status TEXT NOT NULL CHECK (
                status IN ('queued', 'running', 'completed', 'failed', 'cancelled')
            ),
            gate_status TEXT NOT NULL CHECK (
                gate_status IN ('not_evaluated', 'pass', 'regression')
            ),
            metrics_json TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (dataset_id)
                REFERENCES evaluation_datasets(dataset_id),
            FOREIGN KEY (agent_id, spec_version)
                REFERENCES agent_specs(agent_id, version),
            FOREIGN KEY (baseline_batch_id)
                REFERENCES evaluation_batches(batch_id)
        );

        CREATE INDEX evaluation_batches_created_at_idx
        ON evaluation_batches(created_at DESC);
        CREATE INDEX evaluation_batches_dataset_idx
        ON evaluation_batches(dataset_id, created_at DESC);

        CREATE TABLE evaluation_case_results (
            batch_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN (
                    'pending', 'running', 'passed', 'failed', 'error', 'cancelled'
                )
            ),
            run_id TEXT,
            latency_ms INTEGER,
            output TEXT,
            failure_reason TEXT,
            PRIMARY KEY (batch_id, case_id),
            FOREIGN KEY (batch_id)
                REFERENCES evaluation_batches(batch_id) ON DELETE CASCADE,
            FOREIGN KEY (run_id)
                REFERENCES runs(run_id)
        );
        """
    )
