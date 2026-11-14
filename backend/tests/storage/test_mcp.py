from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from agent_crossbar.domain.mcp import MCPServerCreate
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.mcp import MCPStore, MCPToolRecord


def _tool(server_id: str, name: str) -> MCPToolRecord:
    return MCPToolRecord(
        server_id=server_id,
        tool_name=name,
        exposed_name=f"mcp.{server_id}.{name}",
        description=f"Tool {name}.",
        input_schema={"type": "object", "properties": {}},
        discovered_at=datetime.now(timezone.utc),
    )


def test_replacement_is_atomic_and_scoped_to_one_server(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = MCPStore(database)
    first = store.create(MCPServerCreate(label="First", command="first"))
    second = store.create(MCPServerCreate(label="Second", command="second"))
    store.replace_tools(first.server_id, [_tool(first.server_id, "old")])

    store.replace_tools(first.server_id, [_tool(first.server_id, "new")])

    assert [tool.tool_name for tool in store.list_tools(first.server_id)] == ["new"]
    assert store.list_tools(second.server_id) == []
    database.close()


def test_deleting_server_cascades_to_discovered_tools(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = MCPStore(database)
    server = store.create(MCPServerCreate(label="Disposable", command="server"))
    store.replace_tools(server.server_id, [_tool(server.server_id, "echo")])

    store.delete(server.server_id)

    assert store.list_tools() == []
    database.close()


def test_cross_server_exposed_name_collision_aborts_replacement(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = MCPStore(database)
    first = store.create(MCPServerCreate(label="First", command="first"))
    second = store.create(MCPServerCreate(label="Second", command="second"))
    colliding = MCPToolRecord(
        server_id=second.server_id,
        tool_name="echo",
        exposed_name=f"mcp.{first.server_id}.echo",
        description="Collision.",
        input_schema={"type": "object"},
        discovered_at=datetime.now(timezone.utc),
    )
    store.replace_tools(first.server_id, [_tool(first.server_id, "echo")])

    with pytest.raises(ValueError, match="collide"):
        store.replace_tools(second.server_id, [colliding])

    assert [tool.server_id for tool in store.list_tools()] == [first.server_id]
    database.close()
