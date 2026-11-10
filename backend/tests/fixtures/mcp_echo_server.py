from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

server = MCPServer("agent-crossbar-test")


@server.tool(description="Echo a short value for the Agent Crossbar integration test.")
def echo(value: str) -> str:
    return f"echo:{value}"


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
