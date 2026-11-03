import os
from pathlib import Path

import pytest
from agent_crossbar.sidecar import parse_args, process_is_running


def test_sidecar_requires_a_launch_token() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--database", "crossbar.db"])


def test_sidecar_accepts_an_ephemeral_loopback_port(tmp_path: Path) -> None:
    arguments = parse_args(
        [
            "--database",
            str(tmp_path / "crossbar.db"),
            "--token",
            "a" * 32,
            "--port",
            "0",
        ]
    )

    assert arguments.port == 0
    assert arguments.database == tmp_path / "crossbar.db"


def test_sidecar_accepts_the_desktop_owner_process(tmp_path: Path) -> None:
    arguments = parse_args(
        [
            "--database",
            str(tmp_path / "crossbar.db"),
            "--token",
            "a" * 32,
            "--parent-pid",
            "1234",
        ]
    )

    assert arguments.parent_pid == 1234


def test_sidecar_recognizes_its_current_process() -> None:
    assert process_is_running(os.getpid())
