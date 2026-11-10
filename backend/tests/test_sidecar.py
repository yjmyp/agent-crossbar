import os
from pathlib import Path

import agent_crossbar.sidecar as sidecar
import pytest

parse_args = sidecar.parse_args
process_is_running = sidecar.process_is_running


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


def test_sidecar_loads_the_worker_inbound_token_from_environment(
    tmp_path: Path,
) -> None:
    options = parse_args(
        [
            "--database",
            str(tmp_path / "crossbar.db"),
            "--token",
            "a" * 32,
        ]
    )

    settings = sidecar.create_app_settings(
        options,
        {"AGENT_CROSSBAR_WORKER_INBOUND_TOKEN": "w" * 40},
    )

    assert settings.launch_token == "a" * 32
    assert settings.worker_inbound_token == "w" * 40


def test_sidecar_rejects_a_short_worker_inbound_token(tmp_path: Path) -> None:
    options = parse_args(
        [
            "--database",
            str(tmp_path / "crossbar.db"),
            "--token",
            "a" * 32,
        ]
    )

    with pytest.raises(ValueError, match="at least 32 characters"):
        sidecar.create_app_settings(
            options,
            {"AGENT_CROSSBAR_WORKER_INBOUND_TOKEN": "too-short"},
        )
