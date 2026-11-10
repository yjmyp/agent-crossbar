import pytest
from agent_crossbar.domain.mcp import MCPServerCreate
from agent_crossbar.runtime.catalog import OpenAIConnectionConfig
from agent_crossbar.runtime.embeddings import OpenAICompatibleEmbeddingClient
from pydantic import ValidationError


def test_mcp_rejects_remote_plain_http() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        MCPServerCreate(
            label="Remote",
            transport="http",
            url="http://mcp.example.test/mcp",
        )


def test_mcp_allows_loopback_http_for_local_development() -> None:
    server = MCPServerCreate(
        label="Local",
        transport="http",
        url="http://127.0.0.1:8765/mcp",
    )
    assert server.url == "http://127.0.0.1:8765/mcp"


def test_model_connection_rejects_remote_plain_http() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        OpenAIConnectionConfig(
            base_url="http://model.example.test/v1",
            api_key="key",
            model="model-a",
        )


def test_model_connection_allows_loopback_http() -> None:
    config = OpenAIConnectionConfig(
        base_url="http://localhost:11434/v1",
        api_key="key",
        model="model-a",
    )
    assert config.base_url == "http://localhost:11434/v1"


def test_embedding_client_rejects_remote_plain_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleEmbeddingClient(
            base_url="http://embedding.example.test/v1",
            api_key="key",
            model="embed-a",
        )
