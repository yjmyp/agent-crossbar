from __future__ import annotations

from pathlib import Path

from agent_crossbar.domain.knowledge import KnowledgeDocumentCreate
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.knowledge import KnowledgeStore


class DeterministicEmbedder:
    model = "test-embedding-v1"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


async def test_chinese_and_english_search_return_citations(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = KnowledgeStore(database)
    document = await store.ingest(
        KnowledgeDocumentCreate(
            title="Agent 交付手册",
            source_name="runbook.md",
            content="端侧智能体需要超时控制、幂等执行和可观测性。Fallback must cite evidence.",
        )
    )

    chinese = store.search("幂等执行")
    english = store.search("cite evidence")

    assert chinese[0].document_id == document.document_id
    assert chinese[0].chunk_id.startswith("chk_")
    assert chinese[0].as_dict()["content"] == (
        "端侧智能体需要超时控制、幂等执行和可观测性。"
        "Fallback must cite evidence."
    )
    assert chinese[0].as_dict()["rank"] == 0
    assert english[0].source_name == "runbook.md"
    database.close()


async def test_short_query_and_special_characters_are_literal(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = KnowledgeStore(database)
    await store.ingest(
        KnowledgeDocumentCreate(
            title="Symbols",
            content="Use A_B and 100% safely. 中文两字可检索。",
        )
    )

    assert store.search("A_B")
    assert store.search("100%")
    assert store.search("中文")
    assert store.search("missing%") == []
    database.close()


async def test_search_returns_zero_based_rank_separate_from_bm25_score(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = KnowledgeStore(database)
    stronger = await store.ingest(
        KnowledgeDocumentCreate(
            title="Strong match",
            content="delivery evidence delivery evidence delivery evidence",
        )
    )
    weaker = await store.ingest(
        KnowledgeDocumentCreate(
            title="Weak match",
            content="delivery evidence appears once",
        )
    )

    hits = store.search("delivery evidence", limit=2)

    assert [hit.document_id for hit in hits] == [
        stronger.document_id,
        weaker.document_id,
    ]
    assert [hit.rank for hit in hits] == [0, 1]
    assert hits[0].score != hits[1].score
    assert hits[0].score > hits[1].score
    assert all(0.0 < hit.score <= 1.0 for hit in hits)
    database.close()


async def test_reingest_preserves_creation_time_and_delete_removes_hits(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = KnowledgeStore(database)
    payload = KnowledgeDocumentCreate(title="Manual", content="Stable lifecycle evidence.")
    first = await store.ingest(payload)
    second = await store.ingest(payload)

    assert second.created_at == first.created_at
    assert store.search("lifecycle")

    store.delete(first.document_id)
    assert store.search("lifecycle") == []
    database.close()


async def test_hybrid_search_fuses_lexical_and_vector_rankings(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    lexical_content = "发布审批需要双人复核。"
    semantic_content = "上线之前要有两名同事共同确认。"
    query = "发布前如何复核"
    embedder = DeterministicEmbedder(
        {
            lexical_content: [0.5, 0.866],
            semantic_content: [0.0, 1.0],
            query: [0.1, 0.995],
        }
    )
    store = KnowledgeStore(database, embedder=embedder)

    lexical_document = await store.ingest(
        KnowledgeDocumentCreate(title="审批规则", content=lexical_content)
    )
    semantic_document = await store.ingest(
        KnowledgeDocumentCreate(title="发布语义规范", content=semantic_content)
    )

    response = await store.search_with_mode(query, limit=2)

    assert response.mode == "vector"
    assert response.results[0].document_id == semantic_document.document_id
    assert response.results[1].document_id == lexical_document.document_id
    assert response.results[0].vector_rank == 0
    assert response.results[0].lexical_rank is None
    database.close()


async def test_hybrid_search_uses_rrf_when_both_channels_match(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    both_content = "Agent deployment audit requires evidence and rollback."
    semantic_content = "Agent rollout needs a trace."
    query = "Agent deployment audit"
    embedder = DeterministicEmbedder(
        {
            both_content: [1.0, 0.0],
            semantic_content: [0.0, 1.0],
            query: [0.72, 0.69],
        }
    )
    store = KnowledgeStore(database, embedder=embedder)

    both = await store.ingest(
        KnowledgeDocumentCreate(title="Deployment", content=both_content)
    )
    await store.ingest(
        KnowledgeDocumentCreate(title="Audit", content=semantic_content)
    )

    response = await store.search_with_mode(query, limit=2)

    assert response.mode == "hybrid"
    assert response.results[0].document_id == both.document_id
    assert response.results[0].lexical_rank == 0
    assert response.results[0].vector_rank == 0
    assert response.results[0].score > response.results[1].score
    database.close()


async def test_embedding_failure_degrades_to_lexical_without_losing_results(
    tmp_path: Path,
) -> None:
    class FailingEmbedder:
        model = "unavailable"

        async def embed(self, _: list[str]) -> list[list[float]]:
            raise RuntimeError("provider unavailable")

    database = Database(tmp_path / "crossbar.db")
    lexical_store = KnowledgeStore(database)
    await lexical_store.ingest(
        KnowledgeDocumentCreate(title="Runbook", content="Rollback requires evidence.")
    )
    store = KnowledgeStore(database, embedder=FailingEmbedder())

    response = await store.search_with_mode("Rollback evidence")

    assert response.mode == "lexical"
    assert response.degraded_reason == "embedding_unavailable"
    assert response.results[0].title == "Runbook"
    database.close()


async def test_model_change_marks_embedding_index_stale_until_rebuild(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "crossbar.db")
    first = DeterministicEmbedder({"evidence": [1.0, 0.0]})
    first_store = KnowledgeStore(database, embedder=first)
    await first_store.ingest(
        KnowledgeDocumentCreate(title="Evidence", content="evidence")
    )
    assert (await first_store.index_status()).state == "ready"

    second = DeterministicEmbedder({"evidence": [1.0, 0.0]})
    second.model = "test-embedding-v2"
    second_store = KnowledgeStore(database, embedder=second)
    status = await second_store.index_status()

    assert status.state == "stale"
    assert status.indexed_model == "test-embedding-v1"
    assert status.configured_model == "test-embedding-v2"

    rebuilt = await second_store.rebuild_index()

    assert rebuilt.state == "ready"
    assert rebuilt.indexed_model == "test-embedding-v2"
    assert rebuilt.indexed_chunks == 1
    database.close()
