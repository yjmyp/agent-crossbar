from asyncio import run
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from agent_crossbar.api.app import AppSettings, create_app
from agent_crossbar.runtime.catalog import ProviderCatalog
from fastapi.testclient import TestClient

_AUTHORIZATION = {"Authorization": "Bearer integration-token"}


class DeterministicEmbedder:
    model = "test-embedding-v1"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, text="provider must not be called")
        )
    )
    app = create_app(
        AppSettings(
            database_path=tmp_path / "knowledge.db",
            launch_token="integration-token",
        ),
        provider_catalog=ProviderCatalog.from_environment(
            {},
            http_client=provider_client,
        ),
    )
    with TestClient(app) as test_client:
        yield test_client
    run(provider_client.aclose())


@pytest.fixture
def semantic_client(tmp_path: Path) -> Iterator[TestClient]:
    provider_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, text="provider must not be called")
        )
    )
    app = create_app(
        AppSettings(
            database_path=tmp_path / "knowledge.db",
            launch_token="integration-token",
        ),
        provider_catalog=ProviderCatalog.from_environment(
            {},
            http_client=provider_client,
        ),
        embedding_client=DeterministicEmbedder(
            {
                (
                    "发布前必须完成冒烟测试。"
                    "如果鉴权失败，先检查桌面宿主生成的回环令牌。"
                ): [0.6, 0.8],
                "冒烟测试": [1.0, 0.0],
            }
        ),
    )
    with TestClient(app) as test_client:
        yield test_client
    run(provider_client.aclose())


def ingest(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/v1/knowledge/documents",
        headers=_AUTHORIZATION,
        json={
            "title": "交付手册",
            "source_name": "runbook.md",
            "content": (
                "发布前必须完成冒烟测试。"
                "如果鉴权失败，先检查桌面宿主生成的回环令牌。"
            ),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_chinese_search_returns_ranked_content_and_excerpt(client: TestClient) -> None:
    document = ingest(client)

    response = client.get(
        "/v1/knowledge/search",
        headers=_AUTHORIZATION,
        params={"q": "冒烟测试", "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "冒烟测试"
    assert len(payload["results"]) == 1
    hit = payload["results"][0]
    assert hit["document_id"] == document["document_id"]
    assert hit["content"]
    assert "冒烟测试" in hit["content"]
    assert hit["excerpt"]
    assert "冒烟测试" in hit["excerpt"]
    assert hit["rank"] == 0
    assert hit["position"] == 0
    assert isinstance(hit["score"], float)


def test_search_requires_the_per_launch_token(client: TestClient) -> None:
    response = client.get("/v1/knowledge/search", params={"q": "冒烟测试"})

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"q": "   "}, "knowledge query"),
        ({"q": "x" * 501}, "knowledge query"),
        ({"q": "冒烟", "limit": 0}, "knowledge search limit"),
        ({"q": "冒烟", "limit": 21}, "knowledge search limit"),
    ],
)
def test_search_rejects_out_of_bounds_query_parameters(
    client: TestClient,
    params: dict[str, object],
    message: str,
) -> None:
    response = client.get(
        "/v1/knowledge/search",
        headers=_AUTHORIZATION,
        params=params,
    )

    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


def test_search_accepts_limit_boundaries(client: TestClient) -> None:
    ingest(client)

    for limit in (1, 20):
        response = client.get(
            "/v1/knowledge/search",
            headers=_AUTHORIZATION,
            params={"q": "冒烟测试", "limit": limit},
        )
        assert response.status_code == 200


def test_embedding_ingest_is_awaited_and_search_exposes_hybrid_mode(
    semantic_client: TestClient,
) -> None:
    document = ingest(semantic_client)

    response = semantic_client.get(
        "/v1/knowledge/search",
        headers=_AUTHORIZATION,
        params={"q": "冒烟测试", "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "hybrid"
    assert payload["degraded_reason"] is None
    assert payload["results"][0]["document_id"] == document["document_id"]
    assert payload["results"][0]["retrieval_mode"] == "hybrid"
    assert payload["results"][0]["lexical_rank"] == 0
    assert payload["results"][0]["vector_rank"] == 0


def test_embedding_index_status_and_rebuild_are_observable(
    semantic_client: TestClient,
) -> None:
    ingest(semantic_client)

    status_response = semantic_client.get(
        "/v1/knowledge/index",
        headers=_AUTHORIZATION,
    )
    rebuild_response = semantic_client.post(
        "/v1/knowledge/index/rebuild",
        headers=_AUTHORIZATION,
    )

    assert status_response.status_code == 200
    assert status_response.json() == {
        "state": "ready",
        "configured_model": "test-embedding-v1",
        "indexed_model": "test-embedding-v1",
        "dimensions": 2,
        "indexed_chunks": 1,
        "expected_chunks": 1,
        "last_error": None,
        "updated_at": status_response.json()["updated_at"],
    }
    assert rebuild_response.status_code == 200
    assert rebuild_response.json()["state"] == "ready"
    assert rebuild_response.json()["indexed_chunks"] == 1


def test_embedding_runtime_configuration_can_be_reloaded_and_removed(
    client: TestClient,
) -> None:
    configured = client.put(
        "/v1/knowledge/embedding/configuration",
        headers=_AUTHORIZATION,
        json={
            "base_url": "https://embedding.example/v1",
            "api_key": "must-not-leak",
            "model": "embedding-a",
        },
    )
    removed = client.delete(
        "/v1/knowledge/embedding/configuration",
        headers=_AUTHORIZATION,
    )

    assert configured.status_code == 200
    assert configured.json()["configured_model"] == "embedding-a"
    assert "must-not-leak" not in configured.text
    assert removed.status_code == 200
    assert removed.json()["configured_model"] is None
    assert removed.json()["state"] == "lexical"
