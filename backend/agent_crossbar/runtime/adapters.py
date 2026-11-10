from __future__ import annotations

import json
from collections.abc import AsyncIterator

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.base import ModelProvider, RuntimeRequest
from agent_crossbar.runtime.delegation import DelegationCoordinator
from agent_crossbar.runtime.langgraph_runtime import LangGraphRuntime
from agent_crossbar.runtime.native import NativeRuntime
from agent_crossbar.runtime.tools import ToolRegistry


class StructuredRuntime:
    """Validate the native runtime's final answer against the declared JSON schema."""

    def __init__(self, native: NativeRuntime, schema: dict[str, object]) -> None:
        self._native = native
        self._schema = schema

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        async for event in self._native.execute(request):
            if event.type != RuntimeEventType.RUN_COMPLETED:
                yield event
                continue

            output = event.payload.get("output")
            error = _structured_output_error(output, self._schema)
            if error is None:
                yield event
            else:
                yield event.model_copy(
                    update={
                        "type": RuntimeEventType.RUN_FAILED,
                        "payload": {"error": error},
                    }
                )
            return


class RuntimeAdapterRegistry:
    """Construct the explicitly supported runtime adapters for one application."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        tool_registry: ToolRegistry,
        delegation: DelegationCoordinator | None = None,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._delegation = delegation

    def create(self, spec: AgentSpec) -> NativeRuntime | StructuredRuntime | LangGraphRuntime:
        if spec.runtime == "langgraph":
            return LangGraphRuntime(
                provider=self._provider,
                tool_registry=self._tool_registry,
                delegation=self._delegation,
            )
        native = NativeRuntime(
            provider=self._provider,
            tool_registry=self._tool_registry,
            delegation=self._delegation,
            review=spec.runtime == "review",
        )
        if spec.runtime == "structured":
            return StructuredRuntime(native, spec.output_schema)
        return native


def _structured_output_error(
    output: object,
    schema: dict[str, object],
) -> dict[str, str] | None:
    if not isinstance(output, str):
        return {
            "code": "structured_output_invalid",
            "message": "The structured runtime requires a JSON object response.",
        }
    try:
        value = json.loads(output)
    except (TypeError, ValueError):
        return {
            "code": "structured_output_invalid",
            "message": "The structured runtime returned invalid JSON.",
        }
    if not isinstance(value, dict):
        return {
            "code": "structured_output_invalid",
            "message": "The structured runtime must return a JSON object.",
        }
    try:
        validator = Draft202012Validator(schema)
        validator.check_schema(schema)
    except SchemaError:
        return {
            "code": "structured_output_invalid",
            "message": "The declared output schema is invalid.",
        }
    if next(validator.iter_errors(value), None) is not None:
        return {
            "code": "structured_output_invalid",
            "message": "The structured runtime output does not match the declared schema.",
        }
    return None
