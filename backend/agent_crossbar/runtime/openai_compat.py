from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from agent_crossbar.domain.events import TokenUsage
from agent_crossbar.runtime.base import ProviderRequest
from agent_crossbar.runtime.messages import ConversationMessage, ModelResponse, ToolCall


class OpenAICompatibleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized_base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an explicit HTTP(S) endpoint")
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not model.strip():
            raise ValueError("model must not be blank")

        self._endpoint = f"{normalized_base_url}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client

    async def complete(self, request: ProviderRequest) -> ModelResponse:
        payload = {
            "model": self._model,
            "messages": [self._encode_message(message) for message in request.messages],
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
            ]

        client = self._client or httpx.AsyncClient()
        try:
            try:
                response = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.HTTPError:
                raise OpenAICompatibleError(
                    "provider_transport_error",
                    "the model provider could not be reached",
                ) from None
        finally:
            if self._client is None:
                await client.aclose()

        if not response.is_success:
            raise OpenAICompatibleError(
                "provider_http_error",
                f"the model provider returned HTTP {response.status_code}",
            )

        try:
            return self._decode_response(response.json())
        except (ValueError, TypeError, KeyError, ValidationError):
            raise OpenAICompatibleError(
                "malformed_response",
                "the model provider returned a malformed response",
            ) from None

    @staticmethod
    def _encode_message(message: ConversationMessage) -> dict[str, Any]:
        encoded: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_calls:
            encoded["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            encoded["tool_call_id"] = message.tool_call_id
        return encoded

    @staticmethod
    def _decode_response(payload: object) -> ModelResponse:
        if not isinstance(payload, dict):
            raise ValueError("response must be an object")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("response must contain a choice")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("choice must be an object")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("choice must contain a message")

        content = message.get("content")
        if content is None:
            text = ""
        elif isinstance(content, str):
            text = content
        else:
            raise ValueError("message content must be text")

        raw_tool_calls = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise ValueError("tool_calls must be a list")
        tool_calls = tuple(
            OpenAICompatibleProvider._decode_tool_call(raw_call)
            for raw_call in raw_tool_calls
        )

        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason is None:
            finish_reason = "stop"
        if not isinstance(finish_reason, str) or not finish_reason.strip():
            raise ValueError("finish_reason must be nonempty text")

        usage_payload = payload.get("usage", {})
        if not isinstance(usage_payload, dict):
            raise ValueError("usage must be an object")
        prompt_tokens = usage_payload.get("prompt_tokens", 0)
        completion_tokens = usage_payload.get("completion_tokens", 0)
        if (
            isinstance(prompt_tokens, bool)
            or not isinstance(prompt_tokens, int)
            or prompt_tokens < 0
            or isinstance(completion_tokens, bool)
            or not isinstance(completion_tokens, int)
            or completion_tokens < 0
        ):
            raise ValueError("token usage must be nonnegative integers")

        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            ),
            finish_reason=finish_reason,
        )

    @staticmethod
    def _decode_tool_call(payload: object) -> ToolCall:
        if not isinstance(payload, dict):
            raise ValueError("tool call must be an object")
        if payload.get("type") != "function":
            raise ValueError("tool call type must be function")

        call_id = payload.get("id")
        function = payload.get("function")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("tool call id must be nonempty text")
        if not isinstance(function, dict):
            raise ValueError("tool call function must be an object")

        name = function.get("name")
        raw_arguments = function.get("arguments")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool call name must be nonempty text")
        if not isinstance(raw_arguments, str):
            raise OpenAICompatibleError(
                "malformed_tool_call",
                "the model provider returned malformed tool arguments",
            )

        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, ValueError):
            raise OpenAICompatibleError(
                "malformed_tool_call",
                "the model provider returned malformed tool arguments",
            ) from None
        if not isinstance(arguments, dict):
            raise OpenAICompatibleError(
                "malformed_tool_call",
                "the model provider returned malformed tool arguments",
            )
        return ToolCall(id=call_id, name=name, arguments=arguments)
