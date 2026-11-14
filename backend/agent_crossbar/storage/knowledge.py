from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from agent_crossbar.domain.knowledge import KnowledgeDocumentCreate
from agent_crossbar.storage.database import Database

_CHUNK_SIZE = 1_000
_CHUNK_OVERLAP = 120
_MIN_SOFT_BREAK = 500
_SOFT_BREAK = re.compile(r"[\n。！？.!?；;]\s*")
_RRF_K = 60
_EMBEDDING_BATCH_SIZE = 32
_ASCII_NEEDLE = re.compile(r"[a-z0-9][a-z0-9_.:/-]{1,}", re.IGNORECASE)
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


class KnowledgeNotFoundError(Exception):
    """Raised when a knowledge document does not exist."""


class EmbeddingClient(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    document_id: str
    title: str
    source_name: str | None
    content_digest: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    document_id: str
    chunk_id: str
    title: str
    source_name: str | None
    content: str
    excerpt: str
    rank: int
    position: int
    score: float
    retrieval_mode: str
    lexical_rank: int | None = None
    vector_rank: int | None = None
    lexical_score: float | None = None
    vector_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "source_name": self.source_name,
            "content": self.content,
            "excerpt": self.excerpt,
            "rank": self.rank,
            "position": self.position,
            "score": round(self.score, 6),
            "retrieval_mode": self.retrieval_mode,
            "lexical_rank": self.lexical_rank,
            "vector_rank": self.vector_rank,
            "lexical_score": (
                round(self.lexical_score, 6)
                if self.lexical_score is not None
                else None
            ),
            "vector_score": (
                round(self.vector_score, 6)
                if self.vector_score is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    mode: str
    results: list[KnowledgeHit]
    degraded_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "degraded_reason": self.degraded_reason,
            "results": [hit.as_dict() for hit in self.results],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeIndexStatus:
    state: str
    configured_model: str | None
    indexed_model: str | None
    dimensions: int | None
    indexed_chunks: int
    expected_chunks: int
    last_error: str | None
    updated_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "configured_model": self.configured_model,
            "indexed_model": self.indexed_model,
            "dimensions": self.dimensions,
            "indexed_chunks": self.indexed_chunks,
            "expected_chunks": self.expected_chunks,
            "last_error": self.last_error,
            "updated_at": self.updated_at.isoformat(),
        }


class KnowledgeStore:
    def __init__(
        self,
        database: Database,
        *,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._database = database
        self._embedder = embedder

    def set_embedder(self, embedder: EmbeddingClient | None) -> None:
        self._embedder = embedder

    async def ingest(self, value: KnowledgeDocumentCreate) -> KnowledgeDocumentRecord:
        content = value.content.replace("\r\n", "\n").replace("\r", "\n")
        content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        identity = f"{value.source_name or value.title}\0{content_digest}".encode()
        document_id = f"doc_{hashlib.sha256(identity).hexdigest()[:24]}"
        chunks = _chunk(content)
        now = datetime.now(timezone.utc).isoformat()

        with self._database.write_lock, self._database.connection:
            existing = self._database.connection.execute(
                "SELECT created_at FROM knowledge_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            self._database.connection.execute(
                """
                INSERT INTO knowledge_documents(
                    document_id, title, source_name, content, content_digest,
                    chunk_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    source_name = excluded.source_name,
                    content = excluded.content,
                    content_digest = excluded.content_digest,
                    chunk_count = excluded.chunk_count,
                    updated_at = excluded.updated_at
                """,
                (
                    document_id,
                    value.title,
                    value.source_name,
                    content,
                    content_digest,
                    len(chunks),
                    created_at,
                    now,
                ),
            )
            self._database.connection.execute(
                "DELETE FROM knowledge_fts WHERE document_id = ?",
                (document_id,),
            )
            self._database.connection.execute(
                "DELETE FROM knowledge_chunks WHERE document_id = ?",
                (document_id,),
            )
            chunk_rows = [
                (
                    _chunk_id(document_id, position, chunk_text),
                    document_id,
                    position,
                    chunk_text,
                )
                for position, chunk_text in enumerate(chunks)
            ]
            self._database.connection.executemany(
                """
                INSERT INTO knowledge_chunks(chunk_id, document_id, position, content)
                VALUES (?, ?, ?, ?)
                """,
                chunk_rows,
            )
            self._database.connection.executemany(
                """
                INSERT INTO knowledge_fts(chunk_id, document_id, title, content)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (chunk_id, document_id, value.title, chunk_text)
                    for chunk_id, _, _, chunk_text in chunk_rows
                ],
            )

        if self._embedder is not None:
            try:
                await self._index_rows(chunk_rows)
                self._refresh_index_state()
            except Exception as error:
                self._record_index_error(error)
        return self.get(document_id)

    def get(self, document_id: str) -> KnowledgeDocumentRecord:
        row = self._database.connection.execute(
            """
            SELECT document_id, title, source_name, content_digest, chunk_count,
                   created_at, updated_at
            FROM knowledge_documents
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            raise KnowledgeNotFoundError(f"knowledge document {document_id} does not exist")
        return _document_from_row(row)

    def list(self) -> list[KnowledgeDocumentRecord]:
        rows = self._database.connection.execute(
            """
            SELECT document_id, title, source_name, content_digest, chunk_count,
                   created_at, updated_at
            FROM knowledge_documents
            ORDER BY updated_at DESC, rowid DESC
            """
        ).fetchall()
        return [_document_from_row(row) for row in rows]

    def delete(self, document_id: str) -> None:
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                "DELETE FROM knowledge_documents WHERE document_id = ?",
                (document_id,),
            )
            if cursor.rowcount == 1:
                self._database.connection.execute(
                    "DELETE FROM knowledge_fts WHERE document_id = ?",
                    (document_id,),
                )
        if cursor.rowcount != 1:
            raise KnowledgeNotFoundError(f"knowledge document {document_id} does not exist")
        self._refresh_index_state()

    def search(self, query: str, *, limit: int = 6) -> list[KnowledgeHit]:
        """Return lexical hits for synchronous callers that do not need fusion."""
        return self._search_lexical(query, limit=limit)

    async def search_with_mode(
        self,
        query: str,
        *,
        limit: int = 6,
        mode: str = "auto",
    ) -> KnowledgeSearchResult:
        normalized = query.strip()
        if not normalized:
            return KnowledgeSearchResult(mode="lexical", results=[])
        if limit < 1 or limit > 20:
            raise ValueError("knowledge search limit must be between 1 and 20")
        if mode not in {"auto", "lexical", "vector", "hybrid"}:
            raise ValueError("knowledge search mode must be auto, lexical, vector, or hybrid")
        if mode == "lexical":
            return KnowledgeSearchResult(
                mode="lexical",
                results=self._search_lexical(normalized, limit=limit),
            )

        lexical = self._search_lexical(normalized, limit=limit * 3)
        if self._embedder is None:
            return KnowledgeSearchResult(
                mode="lexical",
                results=lexical[:limit] if mode in {"auto", "hybrid"} else [],
                degraded_reason="embedding_not_configured",
            )

        status = await self.index_status()
        if status.state in {"stale", "error", "lexical", "empty"}:
            reason = {
                "stale": "index_stale",
                "error": "embedding_unavailable",
                "lexical": "embedding_not_configured",
                "empty": "index_empty",
            }[status.state]
            return KnowledgeSearchResult(
                mode="lexical",
                results=lexical[:limit] if mode in {"auto", "hybrid"} else [],
                degraded_reason=reason,
            )

        try:
            query_vector = (await self._embedder.embed([normalized]))[0]
        except Exception:
            return KnowledgeSearchResult(
                mode="lexical",
                results=lexical[:limit] if mode in {"auto", "hybrid"} else [],
                degraded_reason="embedding_unavailable",
            )

        vector = self._vector_search(query_vector, model=self._embedder.model, limit=limit * 3)
        if mode == "vector":
            return KnowledgeSearchResult(
                mode="vector",
                results=[replace(hit, retrieval_mode="vector") for hit in vector[:limit]],
                degraded_reason=None if vector else "no_semantic_matches",
            )
        if not vector and lexical:
            return KnowledgeSearchResult(
                mode="lexical",
                results=lexical[:limit],
                degraded_reason="no_semantic_matches",
            )
        if not lexical:
            return KnowledgeSearchResult(
                mode="vector",
                results=[
                    replace(hit, retrieval_mode="vector")
                    for hit in vector[:limit]
                ],
            )
        if not vector:
            return KnowledgeSearchResult(mode="lexical", results=lexical[:limit])

        fused = _reciprocal_rank_fusion(lexical, vector)
        return KnowledgeSearchResult(mode="hybrid", results=fused[:limit])

    async def index_status(self) -> KnowledgeIndexStatus:
        row = self._database.connection.execute(
            """
            SELECT model, dimensions, indexed_chunks, state, last_error, updated_at
            FROM knowledge_embedding_state
            WHERE singleton_id = 1
            """
        ).fetchone()
        expected = int(
            self._database.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunks"
            ).fetchone()[0]
        )
        indexed = int(
            self._database.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunk_embeddings"
            ).fetchone()[0]
        )
        indexed_model = row["model"] if row is not None else None
        configured_model = self._embedder.model if self._embedder is not None else None

        if self._embedder is None:
            state = "lexical"
        elif expected == 0:
            state = "empty"
        elif indexed_model and configured_model and indexed_model != configured_model:
            state = "stale"
        elif row is not None and row["state"] == "error":
            state = "error"
        elif indexed < expected:
            state = "partial"
        elif indexed_model == configured_model:
            state = "ready"
        else:
            state = "empty"

        return KnowledgeIndexStatus(
            state=state,
            configured_model=configured_model,
            indexed_model=indexed_model,
            dimensions=row["dimensions"] if row is not None else None,
            indexed_chunks=indexed,
            expected_chunks=expected,
            last_error=row["last_error"] if row is not None else None,
            updated_at=(
                datetime.fromisoformat(row["updated_at"])
                if row is not None
                else datetime.now(timezone.utc)
            ),
        )

    async def rebuild_index(self) -> KnowledgeIndexStatus:
        if self._embedder is None:
            self._refresh_index_state()
            return await self.index_status()

        with self._database.write_lock, self._database.connection:
            self._database.connection.execute("DELETE FROM knowledge_chunk_embeddings")
        rows = self._database.connection.execute(
            """
            SELECT chunk_id, document_id, position, content
            FROM knowledge_chunks
            ORDER BY document_id, position
            """
        ).fetchall()
        chunk_rows = [
            (row["chunk_id"], row["document_id"], row["position"], row["content"])
            for row in rows
        ]
        try:
            await self._index_rows(chunk_rows)
            self._refresh_index_state()
        except Exception as error:
            self._record_index_error(error)
        return await self.index_status()

    def _search_lexical(self, query: str, *, limit: int) -> list[KnowledgeHit]:
        normalized = query.strip()
        if not normalized:
            return []
        if limit < 1 or limit > 60:
            raise ValueError("knowledge search limit must be between 1 and 60")

        rows: list[sqlite3.Row] = []
        for fts_query in _fts_queries(normalized):
            try:
                rows = self._database.connection.execute(
                    """
                    SELECT f.chunk_id, f.document_id, f.title, f.content,
                           c.position, d.source_name,
                           bm25(knowledge_fts) AS search_score,
                           'bm25' AS score_kind
                    FROM knowledge_fts AS f
                    JOIN knowledge_chunks AS c
                      ON c.chunk_id = f.chunk_id AND c.document_id = f.document_id
                    JOIN knowledge_documents AS d ON d.document_id = f.document_id
                    WHERE knowledge_fts MATCH ?
                    ORDER BY search_score ASC, d.updated_at DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if rows:
                break

        if not rows:
            wildcard = f"%{_escape_like(normalized)}%"
            rows = self._database.connection.execute(
                """
                SELECT c.chunk_id, c.document_id, d.title, c.content,
                       c.position, d.source_name,
                       0.0 AS search_score,
                       'literal' AS score_kind
                FROM knowledge_chunks AS c
                JOIN knowledge_documents AS d ON d.document_id = c.document_id
                WHERE c.content LIKE ? ESCAPE '!'
                   OR d.title LIKE ? ESCAPE '!'
                ORDER BY d.updated_at DESC, c.position ASC
                LIMIT ?
                """,
                (wildcard, wildcard, limit),
            ).fetchall()

        terms = _literal_terms(normalized)
        if not rows and len(terms) > 1:
            term_conditions = " AND ".join(
                "(c.content LIKE ? ESCAPE '!' OR d.title LIKE ? ESCAPE '!')"
                for _ in terms
            )
            term_values = [
                value
                for term in terms
                for value in (f"%{_escape_like(term)}%", f"%{_escape_like(term)}%")
            ]
            rows = self._database.connection.execute(
                f"""
                SELECT c.chunk_id, c.document_id, d.title, c.content,
                       c.position, d.source_name,
                       0.0 AS search_score,
                       'literal' AS score_kind
                FROM knowledge_chunks AS c
                JOIN knowledge_documents AS d ON d.document_id = c.document_id
                WHERE {term_conditions}
                ORDER BY d.updated_at DESC, c.position ASC
                LIMIT ?
                """,
                (*term_values, limit),
            ).fetchall()

        return [
            KnowledgeHit(
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                title=row["title"],
                source_name=row["source_name"],
                content=row["content"],
                excerpt=_excerpt(row["content"], normalized),
                rank=rank,
                position=int(row["position"]),
                score=_normalized_relevance(
                    score_kind=row["score_kind"],
                    raw_score=float(row["search_score"]),
                ),
                retrieval_mode="lexical",
                lexical_rank=rank,
                lexical_score=_normalized_relevance(
                    score_kind=row["score_kind"],
                    raw_score=float(row["search_score"]),
                ),
            )
            for rank, row in enumerate(rows)
        ]

    def _vector_search(
        self,
        query_vector: list[float],
        *,
        model: str,
        limit: int,
    ) -> list[KnowledgeHit]:
        rows = self._database.connection.execute(
            """
            SELECT e.chunk_id, e.document_id, e.dimensions, e.vector,
                   c.content, c.position, d.title, d.source_name
            FROM knowledge_chunk_embeddings AS e
            JOIN knowledge_chunks AS c
              ON c.chunk_id = e.chunk_id AND c.document_id = e.document_id
            JOIN knowledge_documents AS d ON d.document_id = e.document_id
            WHERE e.model = ?
            """,
            (model,),
        ).fetchall()
        ranked: list[tuple[float, sqlite3.Row]] = []
        query_norm = math.sqrt(sum(value * value for value in query_vector))
        for row in rows:
            vector = _decode_vector(row["vector"], int(row["dimensions"]))
            if len(vector) != len(query_vector):
                continue
            denominator = query_norm * math.sqrt(sum(value * value for value in vector))
            if denominator <= 1e-12:
                continue
            score = sum(a * b for a, b in zip(query_vector, vector, strict=True)) / denominator
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], item[1]["document_id"], item[1]["position"]))
        return [
            KnowledgeHit(
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                title=row["title"],
                source_name=row["source_name"],
                content=row["content"],
                excerpt=_excerpt(row["content"], ""),
                rank=rank,
                position=int(row["position"]),
                score=score,
                retrieval_mode="vector",
                vector_rank=rank,
                vector_score=score,
            )
            for rank, (score, row) in enumerate(ranked[:limit])
        ]

    async def _index_rows(
        self,
        rows: list[tuple[str, str, int, str]],
    ) -> None:
        embedder = self._embedder
        if embedder is None:
            return
        for start in range(0, len(rows), _EMBEDDING_BATCH_SIZE):
            batch = rows[start : start + _EMBEDDING_BATCH_SIZE]
            vectors = await embedder.embed([row[3] for row in batch])
            if len(vectors) != len(batch):
                raise ValueError("embedding provider returned the wrong number of vectors")
            dimensions = len(vectors[0]) if vectors else 0
            if dimensions <= 0 or any(len(vector) != dimensions for vector in vectors):
                raise ValueError("embedding vectors must have consistent dimensions")
            with self._database.write_lock, self._database.connection:
                self._database.connection.executemany(
                    """
                    INSERT INTO knowledge_chunk_embeddings(
                        chunk_id, document_id, model, dimensions, content_digest, vector
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        document_id = excluded.document_id,
                        model = excluded.model,
                        dimensions = excluded.dimensions,
                        content_digest = excluded.content_digest,
                        vector = excluded.vector
                    """,
                    [
                        (
                            row[0],
                            row[1],
                            embedder.model,
                            dimensions,
                            hashlib.sha256(row[3].encode("utf-8")).hexdigest(),
                            _encode_vector(vector),
                        )
                        for row, vector in zip(batch, vectors, strict=True)
                    ],
                )

    def _refresh_index_state(self) -> None:
        expected = int(
            self._database.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunks"
            ).fetchone()[0]
        )
        row = self._database.connection.execute(
            """
            SELECT model, dimensions, COUNT(*) AS indexed_chunks
            FROM knowledge_chunk_embeddings
            GROUP BY model, dimensions
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """
        ).fetchone()
        indexed = int(row["indexed_chunks"]) if row is not None else 0
        model = row["model"] if row is not None else None
        dimensions = row["dimensions"] if row is not None else None
        if self._embedder is None:
            state = "lexical"
            model = None
            dimensions = None
        elif expected == 0:
            state = "empty"
        elif indexed >= expected:
            state = "ready"
        else:
            state = "partial"
        self._write_index_state(
            model=model,
            dimensions=dimensions,
            indexed_chunks=indexed,
            state=state,
            error=None,
        )

    def _record_index_error(self, error: Exception) -> None:
        current = self._database.connection.execute(
            "SELECT model, dimensions FROM knowledge_embedding_state WHERE singleton_id = 1"
        ).fetchone()
        expected = int(
            self._database.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunks"
            ).fetchone()[0]
        )
        indexed = int(
            self._database.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunk_embeddings"
            ).fetchone()[0]
        )
        self._write_index_state(
            model=current["model"] if current is not None else None,
            dimensions=current["dimensions"] if current is not None else None,
            indexed_chunks=min(indexed, expected),
            state="error",
            error=type(error).__name__,
        )

    def _write_index_state(
        self,
        *,
        model: str | None,
        dimensions: int | None,
        indexed_chunks: int,
        state: str,
        error: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO knowledge_embedding_state(
                    singleton_id, model, dimensions, indexed_chunks,
                    state, last_error, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    model = excluded.model,
                    dimensions = excluded.dimensions,
                    indexed_chunks = excluded.indexed_chunks,
                    state = excluded.state,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (model, dimensions, indexed_chunks, state, error, now),
            )


def _reciprocal_rank_fusion(
    lexical: list[KnowledgeHit],
    vector: list[KnowledgeHit],
) -> list[KnowledgeHit]:
    by_chunk: dict[str, dict[str, Any]] = {}
    for hit in lexical:
        by_chunk[hit.chunk_id] = {
            "base": hit,
            "lexical_rank": hit.lexical_rank,
            "vector_rank": hit.vector_rank,
            "lexical_score": hit.lexical_score,
            "vector_score": hit.vector_score,
            "rrf": 1.0 / (_RRF_K + (hit.lexical_rank or 0) + 1),
        }
    for hit in vector:
        entry = by_chunk.get(hit.chunk_id)
        if entry is None:
            entry = {
                "base": hit,
                "lexical_rank": None,
                "vector_rank": hit.vector_rank,
                "lexical_score": None,
                "vector_score": hit.vector_score,
                "rrf": 0.0,
            }
            by_chunk[hit.chunk_id] = entry
        entry["vector_rank"] = hit.vector_rank
        entry["vector_score"] = hit.vector_score
        entry["rrf"] += 1.0 / (_RRF_K + (hit.vector_rank or 0) + 1)

    ordered = sorted(
        by_chunk.values(),
        key=lambda entry: (
            -float(entry["rrf"]),
            entry["base"].document_id,
            entry["base"].position,
        ),
    )
    top_score = float(ordered[0]["rrf"]) if ordered else 1.0
    return [
        replace(
            entry["base"],
            rank=rank,
            score=float(entry["rrf"]) / top_score,
            retrieval_mode="hybrid",
            lexical_rank=entry["lexical_rank"],
            vector_rank=entry["vector_rank"],
            lexical_score=entry["lexical_score"],
            vector_score=entry["vector_score"],
        )
        for rank, entry in enumerate(ordered)
    ]


def _encode_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _decode_vector(value: bytes, dimensions: int) -> list[float]:
    if len(value) != dimensions * 4:
        raise ValueError("stored embedding vector has an invalid size")
    return list(struct.unpack(f"<{dimensions}f", value))


def _chunk(content: str) -> list[str]:
    if len(content) <= _CHUNK_SIZE:
        return [content.strip()]

    chunks: list[str] = []
    start = 0
    while start < len(content):
        target_end = min(start + _CHUNK_SIZE, len(content))
        end = target_end
        if target_end < len(content):
            window = content[start + _MIN_SOFT_BREAK : target_end]
            breaks = list(_SOFT_BREAK.finditer(window))
            if breaks:
                end = start + _MIN_SOFT_BREAK + breaks[-1].end()
        text = content[start:end].strip()
        if text:
            chunks.append(text)
        if end >= len(content):
            break
        next_start = max(start + 1, end - _CHUNK_OVERLAP)
        while next_start < end and content[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def _chunk_id(document_id: str, position: int, content: str) -> str:
    digest = hashlib.sha256(
        f"{document_id}\0{position}\0{content}".encode()
    ).hexdigest()
    return f"chk_{digest[:24]}"


def _excerpt(content: str, query: str, *, limit: int = 360) -> str:
    position = content.lower().find(query.lower()) if query else -1
    if position < 0:
        position = 0
    start = max(0, position - 100)
    end = min(len(content), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


def _escape_like(value: str) -> str:
    return (
        value.replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_")
    )


def _literal_terms(value: str) -> list[str]:
    return [term for term in value.split() if term][:8]


def _fts_queries(value: str) -> list[str]:
    if len(value) < 3:
        return []
    exact = _quote_fts(value)
    terms = _literal_terms(value)
    queries = [exact]
    if len(terms) > 1:
        queries.append(" AND ".join(_quote_fts(term) for term in terms))

    needles = _lexical_needles(value)
    if needles:
        queries.append(" OR ".join(_quote_fts(needle) for needle in needles))
    return list(dict.fromkeys(queries))


def _lexical_needles(value: str) -> list[str]:
    """Extract identifier-like tokens and CJK trigrams for broad FTS recall."""
    needles: list[str] = []
    for match in _ASCII_NEEDLE.finditer(value):
        token = match.group(0).strip("._:/-")
        if len(token) >= 2:
            needles.append(token)

    for run in _CJK_RUN.findall(value):
        if len(run) <= 3:
            needles.append(run)
            continue
        needles.extend(run[index : index + 3] for index in range(len(run) - 2))

    unique: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        normalized = needle.casefold()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(needle)
    return unique[:32]


def _quote_fts(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _normalized_relevance(*, score_kind: str, raw_score: float) -> float:
    if score_kind == "literal":
        return 1.0
    bounded = max(-60.0, min(60.0, raw_score))
    return 1.0 / (1.0 + math.exp(bounded))


def _document_from_row(row: sqlite3.Row) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        document_id=row["document_id"],
        title=row["title"],
        source_name=row["source_name"],
        content_digest=row["content_digest"],
        chunk_count=row["chunk_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
