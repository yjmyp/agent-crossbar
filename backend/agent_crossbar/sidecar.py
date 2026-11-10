from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path

import uvicorn

from agent_crossbar.api.app import AppSettings, create_app


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent Crossbar local control service")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--token", required=True, type=_launch_token)
    parser.add_argument("--port", type=_port, default=0)
    parser.add_argument("--parent-pid", type=_positive_pid)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> None:
    options = parse_args(arguments)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    options.database.parent.mkdir(parents=True, exist_ok=True)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", options.port))
    listener.listen(128)
    listener.set_inheritable(True)
    port = int(listener.getsockname()[1])

    app = create_app(create_app_settings(options, os.environ))
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,
            access_log=False,
        )
    )
    print(
        json.dumps({"event": "ready", "host": "127.0.0.1", "port": port}),
        flush=True,
    )
    if options.parent_pid is not None:
        threading.Thread(
            target=_stop_when_parent_exits,
            args=(options.parent_pid, server),
            name="desktop-owner-watchdog",
            daemon=True,
        ).start()
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()


def _launch_token(value: str) -> str:
    if len(value) < 32:
        raise argparse.ArgumentTypeError("launch token must contain at least 32 characters")
    return value


def create_app_settings(
    options: argparse.Namespace,
    environment: Mapping[str, str],
) -> AppSettings:
    worker_inbound_token = environment.get("AGENT_CROSSBAR_WORKER_INBOUND_TOKEN")
    if worker_inbound_token is not None:
        worker_inbound_token = worker_inbound_token.strip()
        if len(worker_inbound_token) < 32:
            raise ValueError(
                "AGENT_CROSSBAR_WORKER_INBOUND_TOKEN must contain at least 32 characters"
            )
    return AppSettings(
        database_path=options.database,
        launch_token=options.token,
        worker_inbound_token=worker_inbound_token,
    )


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if port < 0 or port > 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def _positive_pid(value: str) -> int:
    try:
        pid = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("parent PID must be an integer") from error
    if pid <= 0:
        raise argparse.ArgumentTypeError("parent PID must be greater than zero")
    return pid


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _stop_when_parent_exits(parent_pid: int, server: uvicorn.Server) -> None:
    while process_is_running(parent_pid):
        time.sleep(1)
    server.should_exit = True


if __name__ == "__main__":
    main()
