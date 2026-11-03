from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from agent_crossbar.runtime.base import ModelProvider
from agent_crossbar.runtime.native import EchoProvider, ToolDemoProvider
from agent_crossbar.runtime.openai_compat import OpenAICompatibleProvider

_OPENAI_BASE_URL = "AGENT_CROSSBAR_OPENAI_BASE_URL"
_OPENAI_API_KEY = "AGENT_CROSSBAR_OPENAI_API_KEY"
_OPENAI_MODEL = "AGENT_CROSSBAR_OPENAI_MODEL"
_OPENAI_REQUIRED_VARIABLES = (
    _OPENAI_BASE_URL,
    _OPENAI_API_KEY,
    _OPENAI_MODEL,
)


class ProviderConfigurationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    provider_type: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    configured: bool
    missing_configuration: tuple[str, ...] = ()
    configuration_error: str | None = Field(default=None, max_length=500)


class _ProviderEntry:
    def __init__(self, profile: ProviderProfile, provider: ModelProvider | None) -> None:
        self.profile = profile
        self.provider = provider


class ProviderCatalog:
    def __init__(self, entries: Mapping[str, _ProviderEntry]) -> None:
        self._entries = dict(entries)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> ProviderCatalog:
        entries: dict[str, _ProviderEntry] = {
            "local.echo": _ProviderEntry(
                profile=ProviderProfile(
                    id="local.echo",
                    label="Offline echo",
                    provider_type="deterministic",
                    model="deterministic-echo",
                    configured=True,
                ),
                provider=EchoProvider(),
            ),
            "local.tool-demo": _ProviderEntry(
                profile=ProviderProfile(
                    id="local.tool-demo",
                    label="Offline tool demo",
                    provider_type="deterministic_tool_loop",
                    model="deterministic-tool-demo",
                    configured=True,
                ),
                provider=ToolDemoProvider(),
            ),
        }

        values = {name: environ.get(name, "").strip() for name in _OPENAI_REQUIRED_VARIABLES}
        missing = tuple(name for name in _OPENAI_REQUIRED_VARIABLES if not values[name])
        model = values[_OPENAI_MODEL] or "not configured"
        provider: ModelProvider | None = None
        configuration_error: str | None = None
        if not missing:
            try:
                provider = OpenAICompatibleProvider(
                    base_url=values[_OPENAI_BASE_URL],
                    api_key=values[_OPENAI_API_KEY],
                    model=values[_OPENAI_MODEL],
                )
            except ValueError:
                configuration_error = "The OpenAI-compatible provider configuration is invalid."

        entries["openai.default"] = _ProviderEntry(
            profile=ProviderProfile(
                id="openai.default",
                label="OpenAI-compatible",
                provider_type="openai_chat_completions",
                model=model,
                configured=provider is not None,
                missing_configuration=missing,
                configuration_error=configuration_error,
            ),
            provider=provider,
        )
        return cls(entries)

    def list_public(self) -> list[ProviderProfile]:
        return [entry.profile for entry in self._entries.values()]

    def provider_for(self, profile_id: str) -> ModelProvider:
        entry = self._entries.get(profile_id)
        if entry is None or entry.provider is None:
            raise ProviderConfigurationError(
                "provider_not_configured",
                "The selected model provider is not configured.",
            )
        return entry.provider
