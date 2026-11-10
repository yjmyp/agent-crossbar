from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local OpenAI-compatible endpoint used only by smoke tests."
    )
    parser.add_argument("--port", type=int, default=0)
    return parser.parse_args()


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentCrossbarMock/1.0"

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._write_json(404, {"error": {"message": "not found"}})
            return

        expected_key = os.environ.get("AGENT_CROSSBAR_TEST_PROVIDER_KEY", "")
        if not expected_key or self.headers.get("Authorization") != f"Bearer {expected_key}":
            self._write_json(401, {"error": {"message": "unauthorized"}})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (ValueError, TypeError):
            self._write_json(400, {"error": {"message": "invalid JSON"}})
            return

        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            self._write_json(400, {"error": {"message": "messages are required"}})
            return

        messages = payload["messages"]
        tools = payload.get("tools")
        if os.environ.get("AGENT_CROSSBAR_TEST_KNOWLEDGE") == "1" and isinstance(
            tools, list
        ):
            knowledge_tool = next(
                (
                    tool
                    for tool in tools
                    if isinstance(tool, dict)
                    and isinstance(tool.get("function"), dict)
                    and tool["function"].get("name") == "knowledge_search"
                ),
                None,
            )
            if knowledge_tool is not None:
                tool_results = [
                    message
                    for message in messages
                    if isinstance(message, dict) and message.get("role") == "tool"
                ]
                if not tool_results:
                    self._write_json(
                        200,
                        {
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "content": None,
                                        "tool_calls": [
                                            {
                                                "id": "call_knowledge_search",
                                                "type": "function",
                                                "function": {
                                                    "name": "knowledge_search",
                                                    "arguments": (
                                                        '{"query":"发布会话","limit":3}'
                                                    ),
                                                },
                                            }
                                        ],
                                    },
                                    "finish_reason": "tool_calls",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                            },
                        },
                    )
                    return

                tool_content = str(tool_results[-1].get("content", ""))
                self._write_json(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": f"知识库回答：{tool_content}",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 15,
                            "completion_tokens": 8,
                        },
                    },
                )
                return

        if os.environ.get("AGENT_CROSSBAR_TEST_MCP_TOOL") == "1" and isinstance(tools, list):
            mcp_tool = next(
                (
                    tool
                    for tool in tools
                    if isinstance(tool, dict)
                    and isinstance(tool.get("function"), dict)
                    and str(tool["function"].get("name", "")).startswith("mcp.")
                ),
                None,
            )
            if mcp_tool is not None:
                tool_name = mcp_tool["function"]["name"]
                tool_results = [
                    message
                    for message in messages
                    if isinstance(message, dict) and message.get("role") == "tool"
                ]
                if not tool_results:
                    self._write_json(
                        200,
                        {
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "content": None,
                                        "tool_calls": [
                                            {
                                                "id": "call_mcp_echo",
                                                "type": "function",
                                                "function": {
                                                    "name": tool_name,
                                                    "arguments": '{"value":"你好"}',
                                                },
                                            }
                                        ],
                                    },
                                    "finish_reason": "tool_calls",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 8,
                                "completion_tokens": 4,
                            },
                        },
                    )
                    return

                tool_content = str(tool_results[-1].get("content", ""))
                self._write_json(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": f"MCP result: {tool_content}",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 12,
                            "completion_tokens": 6,
                        },
                    },
                )
                return

        self._write_json(
            200,
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        # Avoid writing request headers or bodies into verification artifacts.
        return

    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    options = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", options.port), Handler)
    port = int(server.server_address[1])
    print(json.dumps({"event": "ready", "host": "127.0.0.1", "port": port}), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
