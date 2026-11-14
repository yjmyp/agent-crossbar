from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from agent_crossbar.domain.mcp import MCPServerCreate
from agent_crossbar.runtime.mcp_client import MCPClientService
from agent_crossbar.runtime.tools import ToolExecutionError
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.mcp import MCPStore, MCPToolRecord

_SERVER_PATH = Path(__file__).parents[1] / "fixtures" / "mcp_echo_server.py"


@pytest.mark.asyncio
async def test_stdio_server_discovery_and_invocation(tmp_path: Path) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = MCPStore(database)
    server = store.create(
        MCPServerCreate(
            label="Echo test server",
            transport="stdio",
            command=sys.executable,
            args=(str(_SERVER_PATH),),
        )
    )
    service = MCPClientService(store, timeout_seconds=5)

    discovered = await service.discover(server.server_id)
    stored = store.list_tools(server.server_id)
    result = await service.invoke(stored[0].exposed_name, {"value": "你好"})

    assert [tool.tool_name for tool in discovered] == ["echo"]
    assert stored[0].exposed_name.startswith(f"mcp.{server.server_id}.")
    assert "echo:你好" in result
    database.close()


@pytest.mark.asyncio
async def test_environment_configuration_error_keeps_stable_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(tmp_path / "crossbar.db")
    store = MCPStore(database)
    server = store.create(
        MCPServerCreate(
            label="Missing environment",
            transport="stdio",
            command=sys.executable,
            args=(str(_SERVER_PATH),),
            env_keys=("AGENT_CROSSBAR_TEST_MISSING",),
        )
    )
    store.replace_tools(
        server.server_id,
        [
            MCPToolRecord(
                server_id=server.server_id,
                tool_name="echo",
                exposed_name=f"mcp.{server.server_id}.echo",
                description="Echo a value.",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                discovered_at=datetime.now(timezone.utc),
            )
        ],
    )
    monkeypatch.delenv("AGENT_CROSSBAR_TEST_MISSING", raising=False)
    service = MCPClientService(store, timeout_seconds=5)

    with pytest.raises(ToolExecutionError) as error:
        await service.invoke(f"mcp.{server.server_id}.echo", {"value": "hello"})

    assert error.value.code == "mcp_environment_missing"
    assert "AGENT_CROSSBAR_TEST_MISSING" in str(error.value)
    database.close()
