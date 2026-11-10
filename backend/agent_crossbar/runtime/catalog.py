from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from agent_crossbar.domain.urls import is_loopback_host
from agent_crossbar.runtime.base import ModelProvider, ProviderRequest
from agent_crossbar.runtime.messages import ConversationMessage
from agent_crossbar.runtime.native import DelegationDemoProvider, EchoProvider, ToolDemoProvider
from agent_crossbar.runtime.openai_compat import OpenAICompatibleProvider

_OPENAI_BASE_URL = "AGENT_CROSSBAR_OPENAI_BASE_URL"
_OPENAI_API_KEY = "AGENT_CROSSBAR_OPENAI_API_KEY"
_OPENAI_MODEL = "AGENT_CROSSBAR_OPENAI_MODEL"
_OPENAI_REQUIRED_VARIABLES = (
    _OPENAI_BASE_URL,
    _OPENAI_API_KEY,
    _OPENAI_MODEL,
)
_CONNECTION_TEST_FAILED_MESSAGE = (
    "The model connection could not be verified. Check the base URL, model name, "
    "API key, network access, and provider availability."
)


class OpenAIConnectionConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    base_url: str = Field(min_length=1, max_length=2_048)
    api_key: SecretStr = Field(min_length=1, max_length=16_384)
    model: str = Field(min_length=1, max_length=200)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value.rstrip("/"))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an explicit HTTP(S) endpoint")
        if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
            raise ValueError("remote model base_url must use HTTPS")
        return value


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
    def __init__(
        self,
        entries: Mapping[str, _ProviderEntry],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._entries = dict(entries)
        self._http_client = http_client
        self._lock = RLock()

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> ProviderCatalog:
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
            "local.delegate-demo": _ProviderEntry(
                profile=ProviderProfile(
                    id="local.delegate-demo",
                    label="Offline delegation demo",
                    provider_type="deterministic_delegation",
                    model="deterministic-delegation",
                    configured=True,
                ),
                provider=DelegationDemoProvider(),
            ),
        }

        values = {name: environ.get(name, "").strip() for name in _OPENAI_REQUIRED_VARIABLES}
        missing = tuple(name for name in _OPENAI_REQUIRED_VARIABLES if not values[name])
        model = values[_OPENAI_MODEL] or "not configured"
        provider: ModelProvider | None = None
        configuration_error: str | None = None
        if not missing:
            try:
                config = OpenAIConnectionConfig(
                    base_url=values[_OPENAI_BASE_URL],
                    api_key=values[_OPENAI_API_KEY],
                    model=values[_OPENAI_MODEL],
                )
                provider = OpenAICompatibleProvider(
                    base_url=config.base_url,
                    api_key=config.api_key.get_secret_value(),
                    model=config.model,
                    client=http_client,
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
        return cls(entries, http_client=http_client)

    def list_public(self) -> list[ProviderProfile]:
        with self._lock:
            return [entry.profile for entry in self._entries.values()]

    def provider_for(self, profile_id: str) -> ModelProvider:
        with self._lock:
            entry = self._entries.get(profile_id)
            if entry is None or entry.provider is None:
                raise ProviderConfigurationError(
                    "provider_not_configured",
                    "The selected model provider is not configured.",
                )
            return entry.provider

    def configure_openai(self, config: OpenAIConnectionConfig) -> ProviderProfile:
        provider = OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key.get_secret_value(),
            model=config.model,
            client=self._http_client,
        )
        profile = ProviderProfile(
            id="openai.default",
            label="OpenAI-compatible",
            provider_type="openai_chat_completions",
            model=config.model,
            configured=True,
        )
        with self._lock:
            self._entries["openai.default"] = _ProviderEntry(
                profile=profile,
                provider=provider,
            )
        return profile

    def remove_openai(self) -> ProviderProfile:
        profile = ProviderProfile(
            id="openai.default",
            label="OpenAI-compatible",
            provider_type="openai_chat_completions",
            model="not configured",
            configured=False,
            missing_configuration=_OPENAI_REQUIRED_VARIABLES,
        )
        with self._lock:
            self._entries["openai.default"] = _ProviderEntry(
                profile=profile,
                provider=None,
            )
        return profile

    async def test_openai_connection(self) -> None:
        provider = self.provider_for("openai.default")
        if not isinstance(provider, OpenAICompatibleProvider):
            raise ProviderConfigurationError(
                "provider_not_configured",
                "The OpenAI-compatible provider is not configured.",
            )

        try:
            await provider.complete(
                ProviderRequest(
                    messages=(
                        ConversationMessage(
                            role="system",
                            content="This is an explicit Agent Crossbar connection test.",
                        ),
                        ConversationMessage(
                            role="user",
                            content="Reply with exactly OK.",
                        ),
                    ),
                    tools=(),
                    model_profile="openai.default",
                    turn=1,
                )
            )
        except Exception:
            raise ProviderConfigurationError(
                "provider_connection_failed",
                _CONNECTION_TEST_FAILED_MESSAGE,
            ) from None
