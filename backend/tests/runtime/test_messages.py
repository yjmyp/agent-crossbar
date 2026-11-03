import pytest
from agent_crossbar.runtime.messages import ConversationMessage, ModelResponse, ToolCall
from pydantic import ValidationError


def test_model_response_rejects_duplicate_tool_call_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ModelResponse(
            tool_calls=(
                ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
                ToolCall(id="call_1", name="calculator", arguments={"expression": "3+3"}),
            )
        )


def test_assistant_message_preserves_tool_calls() -> None:
    response = ModelResponse(
        text="I will calculate that.",
        tool_calls=(
            ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"}),
        ),
        finish_reason="tool_calls",
    )

    message = response.assistant_message()

    assert message.role == "assistant"
    assert message.content == "I will calculate that."
    assert message.tool_calls[0].id == "call_1"
    assert message.finish_reason == "tool_calls"


def test_tool_message_requires_a_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool_call_id"):
        ConversationMessage(role="tool", content="4")


def test_user_message_rejects_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool_call_id"):
        ConversationMessage(role="user", content="hello", tool_call_id="call_1")


def test_tool_call_requires_a_nonblank_id() -> None:
    with pytest.raises(ValidationError, match="id"):
        ToolCall(id=" ", name="calculator", arguments={"expression": "2+2"})


def test_only_assistant_messages_can_carry_tool_calls() -> None:
    call = ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"})

    with pytest.raises(ValidationError, match="assistant"):
        ConversationMessage(role="user", content="hello", tool_calls=(call,))


def test_one_message_rejects_duplicate_tool_call_ids() -> None:
    first = ToolCall(id="call_1", name="calculator", arguments={"expression": "2+2"})
    second = ToolCall(id="call_1", name="text_stats", arguments={"text": "hello"})

    with pytest.raises(ValidationError, match="unique"):
        ConversationMessage(role="assistant", tool_calls=(first, second))
