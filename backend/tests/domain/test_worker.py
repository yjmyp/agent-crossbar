import pytest
from agent_crossbar.domain.worker import WorkerCreate
from pydantic import ValidationError


def worker(**overrides: object) -> WorkerCreate:
    values: dict[str, object] = {
        "label": "华东执行节点",
        "base_url": "https://worker.example.test",
        "agent_id": "agent_research",
        "version": "1.0.0",
        "credential_ref": "east-research",
        "max_concurrency": 2,
        "timeout_seconds": 30,
    }
    values.update(overrides)
    return WorkerCreate(**values)


def test_worker_registration_accepts_https_and_normalizes_the_trailing_slash() -> None:
    record = worker(base_url="https://worker.example.test/base/")

    assert record.base_url == "https://worker.example.test/base"


def test_worker_registration_accepts_loopback_http_for_private_development() -> None:
    assert worker(base_url="http://127.0.0.1:9000").base_url == "http://127.0.0.1:9000"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://worker.example.test",
        "https://user:secret@worker.example.test",
        "https://worker.example.test?token=secret",
        "https://worker.example.test#fragment",
        "file:///tmp/worker",
    ],
)
def test_worker_registration_rejects_unsafe_remote_urls(base_url: str) -> None:
    with pytest.raises(ValidationError):
        worker(base_url=base_url)


def test_worker_registration_rejects_unstable_credential_references() -> None:
    with pytest.raises(ValidationError):
        worker(credential_ref="token value with spaces")
