from __future__ import annotations

import ast
import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_crossbar.runtime.messages import ToolCall

ToolExecutor = Callable[[dict[str, Any]], Awaitable[str]]


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ToolDefinition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]
    risk: Literal["low", "medium", "high"] = "low"
    timeout_seconds: float = Field(default=5.0, gt=0, le=120)

    @model_validator(mode="after")
    def validate_input_schema(self) -> ToolDefinition:
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input_schema must describe an object")
        try:
            Draft202012Validator.check_schema(self.input_schema)
        except SchemaError as error:
            raise ValueError(f"invalid tool input_schema: {error.message}") from error
        return self


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    name: str
    content: str


class ToolRegistry:
    def __init__(
        self,
        *,
        definitions: Sequence[ToolDefinition],
        executors: Mapping[str, ToolExecutor],
    ) -> None:
        definitions_by_name: dict[str, ToolDefinition] = {}
        for definition in definitions:
            if definition.name in definitions_by_name:
                raise ValueError(f"duplicate tool definition: {definition.name}")
            definitions_by_name[definition.name] = definition

        definition_names = set(definitions_by_name)
        executor_names = set(executors)
        missing = definition_names - executor_names
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"missing executor for tool: {names}")
        extra = executor_names - definition_names
        if extra:
            names = ", ".join(sorted(extra))
            raise ValueError(f"executor has no matching tool definition: {names}")

        self._definitions = definitions_by_name
        self._executors = dict(executors)

    def available(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def describe(self, names: tuple[str, ...]) -> list[ToolDefinition]:
        definitions: list[ToolDefinition] = []
        for name in names:
            definition = self._definitions.get(name)
            if definition is None:
                raise ToolExecutionError(
                    "tool_not_registered",
                    f"tool {name!r} is not registered",
                )
            definitions.append(definition)
        return definitions

    async def execute(
        self,
        call: ToolCall,
        *,
        allowed_names: tuple[str, ...],
    ) -> ToolResult:
        if call.name not in allowed_names:
            raise ToolExecutionError(
                "tool_not_allowed",
                f"tool {call.name!r} is not allowed by the agent spec",
            )

        definition = self._definitions.get(call.name)
        if definition is None:
            raise ToolExecutionError(
                "tool_not_registered",
                f"tool {call.name!r} is not registered",
            )

        validator = Draft202012Validator(definition.input_schema)
        validation_errors = sorted(
            validator.iter_errors(call.arguments),
            key=lambda error: tuple(str(path) for path in error.absolute_path),
        )
        if validation_errors:
            raise ToolExecutionError(
                "tool_invalid_arguments",
                f"invalid arguments for tool {call.name!r}",
            )

        executor = self._executors[call.name]
        try:
            output = await asyncio.wait_for(
                executor(dict(call.arguments)),
                timeout=definition.timeout_seconds,
            )
        except ToolExecutionError:
            raise
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise ToolExecutionError(
                "tool_timeout",
                f"tool {call.name!r} timed out",
            ) from error
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise ToolExecutionError(
                "tool_execution_failed",
                f"tool {call.name!r} failed",
            ) from error

        if not isinstance(output, str):
            raise ToolExecutionError(
                "tool_invalid_output",
                f"tool {call.name!r} returned a non-string result",
            )
        return ToolResult(call_id=call.id, name=call.name, content=output)


_MAX_EXPRESSION_LENGTH = 500
_MAX_EXPRESSION_DEPTH = 40
_MAX_EXPONENT = 100
_MAX_ABSOLUTE_VALUE = 1e100
_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float | int, float | int], float | int]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
}


def _invalid_calculator_expression() -> ToolExecutionError:
    return ToolExecutionError(
        "tool_invalid_arguments",
        "calculator expression is invalid or exceeds its safety limits",
    )


def _checked_number(value: object) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid_calculator_expression()
    if isinstance(value, float) and not math.isfinite(value):
        raise _invalid_calculator_expression()
    if abs(value) > _MAX_ABSOLUTE_VALUE:
        raise _invalid_calculator_expression()
    return value


def _evaluate_expression(node: ast.AST, *, depth: int = 0) -> float | int:
    if depth > _MAX_EXPRESSION_DEPTH:
        raise _invalid_calculator_expression()

    if isinstance(node, ast.Constant):
        return _checked_number(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate_expression(node.operand, depth=depth + 1)
        return _checked_number(operand if isinstance(node.op, ast.UAdd) else -operand)

    if isinstance(node, ast.BinOp):
        left = _evaluate_expression(node.left, depth=depth + 1)
        right = _evaluate_expression(node.right, depth=depth + 1)

        if isinstance(node.op, ast.Pow):
            if not isinstance(right, int) or abs(right) > _MAX_EXPONENT:
                raise _invalid_calculator_expression()
            try:
                value = left**right
            except ArithmeticError as error:
                raise _invalid_calculator_expression() from error
        else:
            operator = _BINARY_OPERATORS.get(type(node.op))
            if operator is None:
                raise _invalid_calculator_expression()
            try:
                value = operator(left, right)
            except (ArithmeticError, OverflowError) as error:
                raise _invalid_calculator_expression() from error

        return _checked_number(value)

    raise _invalid_calculator_expression()


async def _calculator(arguments: dict[str, Any]) -> str:
    expression = arguments["expression"]
    if not isinstance(expression, str) or not expression.strip():
        raise _invalid_calculator_expression()
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise _invalid_calculator_expression()

    try:
        parsed = ast.parse(expression, mode="eval")
        value = _evaluate_expression(parsed.body)
    except (SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise _invalid_calculator_expression() from error

    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)


async def _text_stats(arguments: dict[str, Any]) -> str:
    text = arguments["text"]
    result = {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()),
    }
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def default_tool_definitions() -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(
            name="calculator",
            description="Evaluate a bounded arithmetic expression without executable code.",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": _MAX_EXPRESSION_LENGTH,
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="text_stats",
            description="Count characters, words, and lines in a text value.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "maxLength": 100_000,
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        ),
    )


def default_tool_executors() -> dict[str, ToolExecutor]:
    return {
        "calculator": _calculator,
        "text_stats": _text_stats,
    }


def build_default_tool_registry() -> ToolRegistry:
    definitions = default_tool_definitions()
    return ToolRegistry(
        definitions=definitions,
        executors=default_tool_executors(),
    )
