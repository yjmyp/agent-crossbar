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
