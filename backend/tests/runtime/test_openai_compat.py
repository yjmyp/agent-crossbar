from __future__ import annotations

import json

import httpx
import pytest
from agent_crossbar.runtime.base import ProviderRequest
from agent_crossbar.runtime.messages import ConversationMessage, ToolCall
from agent_crossbar.runtime.openai_compat import OpenAICompatibleError, OpenAICompatibleProvider
from agent_crossbar.runtime.tools import build_default_tool_registry


def calculator_definition():
    return build_default_tool_registry().describe(("calculator",))[0]


def tool_request() -> ProviderRequest:
    return ProviderRequest(
        messages=(
            ConversationMessage(role="system", content="Use tools when needed."),
            ConversationMessage(role="user", content="What is 2 + 2?"),
        ),
        tools=(calculator_definition(),),
        model_profile="openai.default",
        turn=1,
    )


@pytest.mark.asyncio
async def test_provider_translates_tool_calls_and_preserves_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"

        body = json.loads(request.content)
        assert body["model"] == "model-a"
        assert body["messages"] == [
            {"role": "system", "content": "Use tools when needed."},
            {"role": "user", "content": "What is 2 + 2?"},
        ]
        assert body["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": calculator_definition().description,
                    "parameters": calculator_definition().input_schema,
                },
            }
        ]

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": '{"expression":"2+2"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1/",
        api_key="test-secret",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await provider.complete(tool_request())

    assert response.text == ""
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "calculator"
    assert response.tool_calls[0].arguments == {"expression": "2+2"}
    assert response.finish_reason == "tool_calls"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 3


@pytest.mark.asyncio
async def test_provider_translates_assistant_tool_calls_and_tool_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["messages"] == [
            {"role": "system", "content": "Use tools when needed."},
            {"role": "user", "content": "What is 2 + 2?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression":"2+2"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "4"},
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "The answer is 4."},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    request = ProviderRequest(
        messages=(
            ConversationMessage(role="system", content="Use tools when needed."),
            ConversationMessage(role="user", content="What is 2 + 2?"),
            ConversationMessage(
                role="assistant",
                content="",
                tool_calls=(
                    ToolCall(
                        id="call_1",
                        name="calculator",
                        arguments={"expression": "2+2"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            ConversationMessage(role="tool", content="4", tool_call_id="call_1"),
        ),
        tools=(calculator_definition(),),
        model_profile="openai.default",
        turn=2,
    )
    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-secret",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await provider.complete(request)

    assert response.text == "The answer is 4."
    assert response.tool_calls == ()
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["{broken", "[]", '"text"'])
async def test_provider_rejects_malformed_tool_arguments_without_echoing_them(
    arguments: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calculator",
                                        "arguments": arguments,
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="must-not-leak",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OpenAICompatibleError) as error:
        await provider.complete(tool_request())

    assert error.value.code == "malformed_tool_call"
    assert arguments not in str(error.value)
    assert "must-not-leak" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_http_failure_never_leaks_credentials_or_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text="upstream-secret and must-not-leak",
            headers={"X-Upstream-Debug": "must-not-leak"},
        )

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="must-not-leak",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OpenAICompatibleError) as error:
        await provider.complete(tool_request())

    assert error.value.code == "provider_http_error"
    assert "500" in str(error.value)
    assert "upstream-secret" not in str(error.value)
    assert "must-not-leak" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_network_failure_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("must-not-leak", request=request)

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="must-not-leak",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OpenAICompatibleError) as error:
        await provider.complete(tool_request())

    assert error.value.code == "provider_transport_error"
    assert "must-not-leak" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_rejects_malformed_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-secret",
        model="model-a",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OpenAICompatibleError) as error:
        await provider.complete(tool_request())

    assert error.value.code == "malformed_response"


@pytest.mark.parametrize(
    "base_url",
    ("", "file:///tmp/model", "ftp://model.example/v1", "https://"),
)
def test_provider_requires_an_explicit_http_endpoint(base_url: str) -> None:
    with pytest.raises(ValueError, match="base_url"):
        OpenAICompatibleProvider(
            base_url=base_url,
            api_key="test-secret",
            model="model-a",
        )
