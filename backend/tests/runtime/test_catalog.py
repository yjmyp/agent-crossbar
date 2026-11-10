from __future__ import annotations

import json

import httpx
import pytest
from agent_crossbar.runtime.catalog import (
    OpenAIConnectionConfig,
    ProviderCatalog,
    ProviderConfigurationError,
)
from agent_crossbar.runtime.native import EchoProvider, ToolDemoProvider
from agent_crossbar.runtime.openai_compat import OpenAICompatibleProvider


def configured_environment() -> dict[str, str]:
    return {
        "AGENT_CROSSBAR_OPENAI_BASE_URL": "https://model.example/v1",
        "AGENT_CROSSBAR_OPENAI_API_KEY": "must-not-leak",
        "AGENT_CROSSBAR_OPENAI_MODEL": "model-a",
    }


def test_catalog_exposes_configuration_without_secret() -> None:
    catalog = ProviderCatalog.from_environment(configured_environment())

    payload = [profile.model_dump(mode="json") for profile in catalog.list_public()]

    assert "must-not-leak" not in json.dumps(payload)
    assert {profile.id for profile in catalog.list_public()} == {
        "local.delegate-demo",
        "local.echo",
        "local.tool-demo",
        "openai.default",
    }
    openai_profile = next(
        profile for profile in catalog.list_public() if profile.id == "openai.default"
    )
    assert openai_profile.configured is True
    assert openai_profile.model == "model-a"


def test_catalog_selects_the_registered_provider() -> None:
    catalog = ProviderCatalog.from_environment(configured_environment())

    assert isinstance(catalog.provider_for("local.echo"), EchoProvider)
    assert isinstance(catalog.provider_for("local.tool-demo"), ToolDemoProvider)
    assert isinstance(catalog.provider_for("openai.default"), OpenAICompatibleProvider)


def test_incomplete_openai_configuration_is_visible_but_not_selectable() -> None:
    catalog = ProviderCatalog.from_environment(
        {
            "AGENT_CROSSBAR_OPENAI_BASE_URL": "https://model.example/v1",
            "AGENT_CROSSBAR_OPENAI_API_KEY": "must-not-leak",
        }
    )

    profile = next(
        profile for profile in catalog.list_public() if profile.id == "openai.default"
    )
    assert profile.configured is False
    assert profile.missing_configuration == (
        "AGENT_CROSSBAR_OPENAI_MODEL",
    )
    assert "must-not-leak" not in json.dumps(profile.model_dump(mode="json"))

    with pytest.raises(ProviderConfigurationError) as error:
        catalog.provider_for("openai.default")

    assert error.value.code == "provider_not_configured"
    assert "must-not-leak" not in str(error.value)


def test_unknown_provider_profile_is_rejected() -> None:
    catalog = ProviderCatalog.from_environment({})

    with pytest.raises(ProviderConfigurationError) as error:
        catalog.provider_for("missing.profile")

    assert error.value.code == "provider_not_configured"


def test_invalid_openai_configuration_does_not_crash_catalog_startup() -> None:
    environment = configured_environment()
    environment["AGENT_CROSSBAR_OPENAI_BASE_URL"] = "file:///tmp/model"

    catalog = ProviderCatalog.from_environment(environment)

    profile = next(
        profile for profile in catalog.list_public() if profile.id == "openai.default"
    )
    assert profile.configured is False
    assert "must-not-leak" not in json.dumps(profile.model_dump(mode="json"))

    with pytest.raises(ProviderConfigurationError):
        catalog.provider_for("openai.default")


def test_catalog_can_install_and_replace_openai_configuration() -> None:
    catalog = ProviderCatalog.from_environment({})
    first = catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://first.example/v1",
            api_key="must-not-leak",
            model="model-a",
        )
    )
    second = catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://second.example/v1",
            api_key="replacement-secret",
            model="model-b",
        )
    )

    assert first.configured is True
    assert first.model == "model-a"
    assert second.configured is True
    assert second.model == "model-b"
    public_payload = json.dumps(
        [profile.model_dump(mode="json") for profile in catalog.list_public()]
    )
    assert "must-not-leak" not in public_payload
    assert "replacement-secret" not in public_payload
    assert isinstance(catalog.provider_for("openai.default"), OpenAICompatibleProvider)


def test_catalog_can_remove_openai_configuration() -> None:
    catalog = ProviderCatalog.from_environment({})
    catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://model.example/v1",
            api_key="must-not-leak",
            model="model-a",
        )
    )

    profile = catalog.remove_openai()

    assert profile.configured is False
    with pytest.raises(ProviderConfigurationError) as error:
        catalog.provider_for("openai.default")
    assert error.value.code == "provider_not_configured"
    assert "must-not-leak" not in str(error.value)


async def test_connection_test_uses_the_configured_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["model"] == "model-a"
        assert body["messages"] == [
            {
                "role": "system",
                "content": "This is an explicit Agent Crossbar connection test.",
            },
            {
                "role": "user",
                "content": "Reply with exactly OK.",
            },
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    catalog = ProviderCatalog.from_environment({}, http_client=http_client)
    catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://model.example/v1",
            api_key="test-secret",
            model="model-a",
        )
    )

    await catalog.test_openai_connection()

    await http_client.aclose()


async def test_connection_test_sanitizes_provider_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream-secret and must-not-leak")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    catalog = ProviderCatalog.from_environment({}, http_client=http_client)
    catalog.configure_openai(
        OpenAIConnectionConfig(
            base_url="https://model.example/v1",
            api_key="must-not-leak",
            model="model-a",
        )
    )

    with pytest.raises(ProviderConfigurationError) as error:
        await catalog.test_openai_connection()

    assert error.value.code == "provider_connection_failed"
    assert "upstream-secret" not in str(error.value)
    assert "must-not-leak" not in str(error.value)
    assert "Check the base URL" in str(error.value)
    await http_client.aclose()
