from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_crossbar.domain.mcp import MCPServerCreate
from agent_crossbar.storage.database import Database


class MCPNotFoundError(Exception):
    """Raised when an MCP server or tool is not registered."""


@dataclass(frozen=True, slots=True)
class MCPServerRecord:
    server_id: str
    label: str
    transport: str
    command: str | None
    url: str | None
    args: tuple[str, ...]
    env_keys: tuple[str, ...]
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MCPToolRecord:
    server_id: str
    tool_name: str
    exposed_name: str
    description: str
    input_schema: dict[str, Any]
    discovered_at: datetime


class MCPStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, value: MCPServerCreate) -> MCPServerRecord:
        server_id = f"mcp_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO mcp_servers(
                    server_id, label, transport, command, url, args_json,
                    env_keys_json, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server_id,
                    value.label,
                    value.transport,
                    value.command,
                    value.url,
                    _json(value.args),
                    _json(value.env_keys),
                    int(value.enabled),
                    now,
                    now,
                ),
            )
        return self.get(server_id)

    def get(self, server_id: str) -> MCPServerRecord:
        row = self._database.connection.execute(
            """
            SELECT server_id, label, transport, command, url, args_json,
                   env_keys_json, enabled, created_at, updated_at
            FROM mcp_servers
            WHERE server_id = ?
            """,
            (server_id,),
        ).fetchone()
        if row is None:
            raise MCPNotFoundError(f"MCP server {server_id} does not exist")
        return _server_from_row(row)

    def list(self) -> list[MCPServerRecord]:
        rows = self._database.connection.execute(
            """
            SELECT server_id, label, transport, command, url, args_json,
                   env_keys_json, enabled, created_at, updated_at
            FROM mcp_servers
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [_server_from_row(row) for row in rows]

    def set_enabled(self, server_id: str, enabled: bool) -> MCPServerRecord:
        now = datetime.now(UTC).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE mcp_servers
                SET enabled = ?, updated_at = ?
                WHERE server_id = ?
                """,
                (int(enabled), now, server_id),
            )
        if cursor.rowcount != 1:
            raise MCPNotFoundError(f"MCP server {server_id} does not exist")
        return self.get(server_id)

    def delete(self, server_id: str) -> None:
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                "DELETE FROM mcp_servers WHERE server_id = ?",
                (server_id,),
            )
        if cursor.rowcount != 1:
            raise MCPNotFoundError(f"MCP server {server_id} does not exist")

    def list_tools(self, server_id: str | None = None) -> list[MCPToolRecord]:
        if server_id is None:
            rows = self._database.connection.execute(
                """
                SELECT server_id, tool_name, exposed_name, description,
                       input_schema_json, discovered_at
                FROM mcp_tools
                ORDER BY server_id, tool_name
                """
            ).fetchall()
        else:
            rows = self._database.connection.execute(
                """
                SELECT server_id, tool_name, exposed_name, description,
                       input_schema_json, discovered_at
                FROM mcp_tools
                WHERE server_id = ?
                ORDER BY tool_name
                """,
                (server_id,),
            ).fetchall()
        return [_tool_from_row(row) for row in rows]

    def get_tool(self, exposed_name: str) -> MCPToolRecord:
        row = self._database.connection.execute(
            """
            SELECT server_id, tool_name, exposed_name, description,
                   input_schema_json, discovered_at
            FROM mcp_tools
            WHERE exposed_name = ?
            """,
            (exposed_name,),
        ).fetchone()
        if row is None:
            raise MCPNotFoundError(f"MCP tool {exposed_name} is not registered")
        return _tool_from_row(row)

    def replace_tools(self, server_id: str, tools: list[MCPToolRecord]) -> None:
        now = datetime.now(UTC).isoformat()
        exposed_names = [tool.exposed_name for tool in tools]
        if len(exposed_names) != len(set(exposed_names)):
            raise ValueError("discovered MCP exposed tool names must be unique")
        with self._database.write_lock, self._database.connection:
            self.get(server_id)
            existing_conflicts = self._database.connection.execute(
                """
                SELECT exposed_name
                FROM mcp_tools
                WHERE exposed_name IN ({})
                  AND server_id <> ?
                """.format(",".join("?" for _ in exposed_names)),
                (*exposed_names, server_id),
            ).fetchall() if exposed_names else []
            if existing_conflicts:
                raise ValueError("discovered MCP exposed tool names collide with another server")

            self._database.connection.execute(
                "DELETE FROM mcp_tools WHERE server_id = ?",
                (server_id,),
            )
            self._database.connection.executemany(
                """
                INSERT INTO mcp_tools(
                    server_id, tool_name, exposed_name, description,
                    input_schema_json, discovered_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        tool.server_id,
                        tool.tool_name,
                        tool.exposed_name,
                        tool.description,
                        _json(tool.input_schema),
                        tool.discovered_at.isoformat(),
                    )
                    for tool in tools
                ],
            )
            self._database.connection.execute(
                "UPDATE mcp_servers SET updated_at = ? WHERE server_id = ?",
                (now, server_id),
            )


def _server_from_row(row: sqlite3.Row) -> MCPServerRecord:
    return MCPServerRecord(
        server_id=row["server_id"],
        label=row["label"],
        transport=row["transport"],
        command=row["command"],
        url=row["url"],
        args=tuple(json.loads(row["args_json"])),
        env_keys=tuple(json.loads(row["env_keys_json"])),
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _tool_from_row(row: sqlite3.Row) -> MCPToolRecord:
    return MCPToolRecord(
        server_id=row["server_id"],
        tool_name=row["tool_name"],
        exposed_name=row["exposed_name"],
        description=row["description"],
        input_schema=json.loads(row["input_schema_json"]),
        discovered_at=datetime.fromisoformat(row["discovered_at"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
