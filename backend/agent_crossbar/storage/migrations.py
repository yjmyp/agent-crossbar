from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 7


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
    if current_version < 4:
        _migration_four(connection)
    if current_version < 5:
        _migration_five(connection)
    if current_version < 6:
        _migration_six(connection)
    if current_version < 7:
        _migration_seven(connection)
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


def _migration_four(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        ALTER TABLE runs ADD COLUMN parent_run_id TEXT REFERENCES runs(run_id);
        ALTER TABLE runs ADD COLUMN root_run_id TEXT;
        ALTER TABLE runs ADD COLUMN delegation_depth INTEGER NOT NULL DEFAULT 0;
        UPDATE runs SET root_run_id = run_id WHERE root_run_id IS NULL;

        CREATE INDEX runs_parent_run_id_idx ON runs(parent_run_id, created_at);
        CREATE INDEX runs_root_run_id_idx ON runs(root_run_id, created_at);

        CREATE TABLE mcp_servers (
            server_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            transport TEXT NOT NULL CHECK (transport IN ('stdio', 'http')),
            command TEXT,
            url TEXT,
            args_json TEXT NOT NULL,
            env_keys_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE mcp_tools (
            server_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            exposed_name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            input_schema_json TEXT NOT NULL,
            discovered_at TEXT NOT NULL,
            PRIMARY KEY (server_id, tool_name),
            FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE
        );

        CREATE INDEX mcp_tools_server_id_idx ON mcp_tools(server_id);

        CREATE TABLE knowledge_documents (
            document_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_name TEXT,
            content TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX knowledge_documents_created_at_idx
        ON knowledge_documents(created_at DESC);

        CREATE TABLE knowledge_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (document_id)
                REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
            UNIQUE(document_id, position)
        );

        CREATE INDEX knowledge_chunks_document_id_idx
        ON knowledge_chunks(document_id, position);

        CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            title,
            content,
            tokenize = 'trigram'
        );
        """
    )


def _migration_five(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE knowledge_embedding_state (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            model TEXT,
            dimensions INTEGER,
            indexed_chunks INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL CHECK (
                state IN ('lexical', 'empty', 'ready', 'partial', 'stale', 'error')
            ),
            last_error TEXT,
            updated_at TEXT NOT NULL
        );

        INSERT INTO knowledge_embedding_state(
            singleton_id, state, updated_at
        )
        VALUES (1, 'lexical', CURRENT_TIMESTAMP);

        CREATE TABLE knowledge_chunk_embeddings (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL CHECK (dimensions > 0),
            content_digest TEXT NOT NULL,
            vector BLOB NOT NULL,
            FOREIGN KEY (chunk_id)
                REFERENCES knowledge_chunks(chunk_id) ON DELETE CASCADE,
            FOREIGN KEY (document_id)
                REFERENCES knowledge_documents(document_id) ON DELETE CASCADE
        );

        CREATE INDEX knowledge_chunk_embeddings_document_id_idx
        ON knowledge_chunk_embeddings(document_id);
        CREATE INDEX knowledge_chunk_embeddings_model_idx
        ON knowledge_chunk_embeddings(model);
        """
    )


def _migration_six(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE workers (
            worker_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            base_url TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            spec_version TEXT NOT NULL,
            credential_ref TEXT NOT NULL,
            max_concurrency INTEGER NOT NULL CHECK (
                max_concurrency BETWEEN 1 AND 32
            ),
            timeout_seconds INTEGER NOT NULL CHECK (
                timeout_seconds BETWEEN 1 AND 86400
            ),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX workers_agent_version_idx
        ON workers(agent_id, spec_version, enabled, created_at);
        """
    )

def _migration_seven(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE security_reviews (
            review_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            root TEXT NOT NULL,
            base TEXT,
            staged INTEGER NOT NULL DEFAULT 0 CHECK (staged IN (0, 1)),
            verdict TEXT NOT NULL CHECK (verdict IN ('block', 'fix', 'ship')),
            policy_name TEXT NOT NULL,
            run_id TEXT,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE INDEX security_reviews_created_at_idx
        ON security_reviews(created_at DESC);
        CREATE INDEX security_reviews_verdict_idx
        ON security_reviews(verdict, created_at DESC);

        CREATE TABLE security_waivers (
            waiver_id TEXT PRIMARY KEY,
            rule_id TEXT NOT NULL,
            file_pattern TEXT NOT NULL,
            owner TEXT NOT NULL,
            reason TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        );

        CREATE INDEX security_waivers_active_idx
        ON security_waivers(revoked_at, expires_at);
        """
    )
