from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from agent_crossbar.domain.urls import is_loopback_host

_EMBEDDING_BASE_URL = "AGENT_CROSSBAR_EMBEDDING_BASE_URL"
_EMBEDDING_API_KEY = "AGENT_CROSSBAR_EMBEDDING_API_KEY"
_EMBEDDING_MODEL = "AGENT_CROSSBAR_EMBEDDING_MODEL"
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_BATCH_SIZE = 64


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EmbeddingConfiguration:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
    ) -> EmbeddingConfiguration | None:
        base_url = environ.get(_EMBEDDING_BASE_URL, "").strip()
        api_key = environ.get(_EMBEDDING_API_KEY, "").strip()
        model = environ.get(_EMBEDDING_MODEL, "").strip()
        if not any((base_url, api_key, model)):
            return None
        if not all((base_url, api_key, model)):
            raise ValueError(
                "embedding base URL, API key, and model must be configured together"
            )
        return cls(base_url=base_url, api_key=api_key, model=model)


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("embedding base_url must be an explicit HTTP(S) endpoint")
        if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
            raise ValueError("remote embedding base_url must use HTTPS")
        if not api_key.strip():
            raise ValueError("embedding api_key must not be blank")
        if not model.strip():
            raise ValueError("embedding model must not be blank")

        self.model = model.strip()
        self._endpoint = f"{normalized}/embeddings"
        self._api_key = api_key
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > _MAX_BATCH_SIZE:
            raise EmbeddingError(
                "embedding_batch_too_large",
                f"embedding batches cannot exceed {_MAX_BATCH_SIZE} inputs",
            )

        client = self._client or httpx.AsyncClient()
        try:
            try:
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "input": texts},
                    timeout=httpx.Timeout(_REQUEST_TIMEOUT_SECONDS),
                )
            except httpx.HTTPError:
                raise EmbeddingError(
                    "embedding_transport_error",
                    "the embedding provider could not be reached",
                ) from None
        finally:
            if self._client is None:
                await client.aclose()

        if not response.is_success:
            raise EmbeddingError(
                "embedding_http_error",
                f"the embedding provider returned HTTP {response.status_code}",
            )
        try:
            return _decode_embeddings(response.json(), expected_count=len(texts))
        except (TypeError, ValueError, KeyError):
            raise EmbeddingError(
                "embedding_malformed_response",
                "the embedding provider returned a malformed response",
            ) from None


def _decode_embeddings(payload: object, *, expected_count: int) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise ValueError("embedding response must be an object")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected_count:
        raise ValueError("embedding response count does not match the request")

    indexed: dict[int, list[float]] = {}
    dimensions: int | None = None
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("embedding item must be an object")
        index = item.get("index")
        raw_vector = item.get("embedding")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index >= expected_count
            or index in indexed
        ):
            raise ValueError("embedding index is invalid")
        if not isinstance(raw_vector, list) or not raw_vector:
            raise ValueError("embedding vector must be a nonempty list")
        vector: list[float] = []
        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("embedding dimensions must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("embedding dimensions must be finite")
            vector.append(number)
        if dimensions is None:
            dimensions = len(vector)
        if dimensions != len(vector):
            raise ValueError("embedding dimensions must be consistent")
        indexed[index] = _normalize(vector)
    return [indexed[index] for index in range(expected_count)]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        raise ValueError("embedding vector cannot have a zero norm")
    return [value / norm for value in vector]
