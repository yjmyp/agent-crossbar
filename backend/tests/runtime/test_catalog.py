from __future__ import annotations

import json

import pytest
from agent_crossbar.runtime.catalog import (
    ProviderCatalog,
    ProviderConfigurationError,
)
from agent_crossbar.runtime.native import EchoProvider
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
        "local.echo",
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
