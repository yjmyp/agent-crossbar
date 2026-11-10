from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment

from agent_crossbar.runtime.tools import ToolDefinition, ToolExecutionError
from agent_crossbar.storage.mcp import MCPNotFoundError, MCPServerRecord, MCPStore, MCPToolRecord

_MAX_DISCOVERED_TOOLS = 500
_MAX_DISCOVERY_PAGES = 20
_MAX_TOOL_OUTPUT_CHARS = 100_000
_TOOL_NAME_PART = re.compile(r"[^a-z0-9_-]+")


class MCPClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MCPClientService:
    def __init__(self, store: MCPStore, *, timeout_seconds: float = 15.0) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds

    async def discover(self, server_id: str) -> list[MCPToolRecord]:
        server = self._store.get(server_id)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._connect(server) as client:
                    cursor: str | None = None
                    discovered: list[MCPToolRecord] = []
                    for _ in range(_MAX_DISCOVERY_PAGES):
                        result = await client.list_tools(cursor=cursor)
                        for tool in result.tools:
                            converted = _convert_tool(server, tool)
                            if converted is not None:
                                discovered.append(converted)
                                if len(discovered) > _MAX_DISCOVERED_TOOLS:
                                    raise MCPClientError(
                                        "mcp_tool_limit",
                                        "The MCP server exposes more than 500 usable tools.",
                                    )
                        cursor = result.next_cursor
                        if cursor is None:
                            break
                    else:
                        raise MCPClientError(
                            "mcp_pagination_limit",
                            "The MCP server returned too many tool pages.",
                        )
        except MCPNotFoundError:
            raise
        except MCPClientError:
            raise
        except TimeoutError as error:
            raise MCPClientError(
                "mcp_discovery_timeout",
                "The MCP server did not complete discovery before the timeout.",
            ) from error
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            raise MCPClientError(
                "mcp_discovery_failed",
                "The MCP server could not be reached or returned an invalid response.",
            ) from None

        try:
            self._store.replace_tools(server_id, discovered)
        except ValueError as error:
            raise MCPClientError(
                "mcp_tool_name_collision",
                "The MCP server exposed tool names that collide with another server.",
            ) from error
        return discovered

    def definitions(self) -> list[ToolDefinition]:
        definitions: list[ToolDefinition] = []
        servers = {server.server_id: server for server in self._store.list()}
        for record in self._store.list_tools():
            server = servers.get(record.server_id)
            if server is None or not server.enabled:
                continue
            definition = _definition(record)
            if definition is not None:
                definitions.append(definition)
        return definitions

    def has_tool(self, exposed_name: str) -> bool:
        try:
            tool = self._store.get_tool(exposed_name)
            return self._store.get(tool.server_id).enabled
        except MCPNotFoundError:
            return False

    async def invoke(self, exposed_name: str, arguments: dict[str, Any]) -> str:
        try:
            tool = self._store.get_tool(exposed_name)
            server = self._store.get(tool.server_id)
        except MCPNotFoundError as error:
            raise ToolExecutionError("mcp_tool_not_found", str(error)) from error
        if not server.enabled:
            raise ToolExecutionError(
                "mcp_server_disabled",
                f"MCP server {server.server_id!r} is disabled",
            )

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._connect(server) as client:
                    result = await client.call_tool(
                        tool.tool_name,
                        arguments=arguments,
                        read_timeout_seconds=self._timeout_seconds,
                    )
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise ToolExecutionError(
                "mcp_tool_timeout",
                "The MCP tool did not complete before the timeout.",
            ) from error
        except MCPClientError as error:
            raise ToolExecutionError(error.code, str(error)) from error
        except Exception as error:
            raise ToolExecutionError(
                "mcp_tool_failed",
                "The MCP tool call failed.",
            ) from error

        if result.is_error:
            raise ToolExecutionError(
                "mcp_tool_reported_error",
                "The MCP tool reported an error.",
            )

        payload = result.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        output = {
            "content": payload.get("content", []),
            "structured_content": payload.get("structuredContent"),
        }
        encoded = json.dumps(
            output,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(encoded) > _MAX_TOOL_OUTPUT_CHARS:
            raise ToolExecutionError(
                "mcp_tool_output_too_large",
                "The MCP tool output exceeded the configured limit.",
            )
        return encoded

    @asynccontextmanager
    async def _connect(self, server: MCPServerRecord) -> AsyncIterator[Client]:
        if server.transport == "stdio":
            environment = get_default_environment()
            for key in server.env_keys:
                value = os.environ.get(key)
                if value is None:
                    raise MCPClientError(
                        "mcp_environment_missing",
                        f"Required environment variable {key!r} is not available.",
                    )
                environment[key] = value
            parameters = StdioServerParameters(
                command=server.command or "",
                args=list(server.args),
                env=environment,
            )
            async with Client(
                parameters,
                raise_exceptions=True,
                read_timeout_seconds=self._timeout_seconds,
            ) as client:
                yield client
            return

        if not server.url:
            raise MCPClientError("mcp_configuration_invalid", "The MCP URL is missing.")
        async with Client(
            server.url,
            raise_exceptions=True,
            read_timeout_seconds=self._timeout_seconds,
        ) as client:
            yield client


def _convert_tool(server: MCPServerRecord, tool: object) -> MCPToolRecord | None:
    tool_name = getattr(tool, "name", None)
    description = getattr(tool, "description", None)
    input_schema = getattr(tool, "input_schema", None)
    if not isinstance(tool_name, str) or not tool_name.strip():
        return None
    if not isinstance(input_schema, dict):
        return None
    exposed_name = _exposed_name(server.server_id, tool_name)
    record = MCPToolRecord(
        server_id=server.server_id,
        tool_name=tool_name,
        exposed_name=exposed_name,
        description=(
            description.strip()[:500]
            if isinstance(description, str) and description.strip()
            else f"MCP tool {tool_name} from {server.label}"
        ),
        input_schema=input_schema,
        discovered_at=datetime.now(UTC),
    )
    return record if _definition(record) is not None else None


def _definition(record: MCPToolRecord) -> ToolDefinition | None:
    try:
        return ToolDefinition(
            name=record.exposed_name,
            description=record.description,
            input_schema=record.input_schema,
            risk="medium",
            timeout_seconds=30,
        )
    except ValueError:
        return None


def _exposed_name(server_id: str, tool_name: str) -> str:
    normalized = _TOOL_NAME_PART.sub("_", tool_name.strip().lower()).strip("._-")
    if not normalized or not normalized[0].isalpha():
        normalized = f"tool_{normalized}"
    prefix = f"mcp.{server_id}."
    available = 100 - len(prefix)
    if len(normalized) > available:
        suffix = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:8]
        normalized = f"{normalized[: available - 9].rstrip('._-')}_{suffix}"
    return f"{prefix}{normalized}"
