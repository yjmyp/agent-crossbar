from __future__ import annotations

import asyncio
import ctypes
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
from agent_crossbar.storage.workers import WorkerRecord

WORKER_PROTOCOL_VERSION = 1
_CREDENTIAL_TARGET_PREFIX = "AgentCrossbar/Worker/"


class WorkerProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkerCredentialVault:
    def __init__(
        self,
        values: Mapping[str, str] | None = None,
        *,
        persistent: bool = False,
    ) -> None:
        if persistent and os.name != "nt":
            raise RuntimeError("persistent Worker credentials require Windows Credential Manager")
        self._persistent = persistent
        self._values: dict[str, str] = {}
        for reference, token in (values or {}).items():
            self.set(reference, token)

    def set(self, reference: str, token: str) -> None:
        if not reference:
            raise ValueError("credential reference must not be blank")
        if not token or token != token.strip():
            raise ValueError("worker token must be non-blank and have no outer whitespace")
        if self._persistent:
            _windows_credential_write(reference, token)
            return
        self._values[reference] = token

    def get(self, reference: str) -> str | None:
        if self._persistent:
            return _windows_credential_read(reference)
        return self._values.get(reference)

    def delete(self, reference: str) -> None:
        if self._persistent:
            _windows_credential_delete(reference)
            return
        self._values.pop(reference, None)

    def __contains__(self, reference: object) -> bool:
        if self._persistent and isinstance(reference, str):
            return self.get(reference) is not None
        return reference in self._values


class _FileTime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def _credential_target(reference: str) -> str:
    return f"{_CREDENTIAL_TARGET_PREFIX}{reference}"


def _windows_advapi32() -> Any:
    if os.name != "nt":
        raise RuntimeError("Windows Credential Manager is unavailable")
    return ctypes.WinDLL("advapi32", use_last_error=True)


def _windows_credential_write(reference: str, token: str) -> None:
    blob = token.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    credential = _Credential(
        Flags=0,
        Type=1,
        TargetName=_credential_target(reference),
        Comment="Agent Crossbar private Worker token",
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        Persist=2,
        UserName="AgentCrossbar",
    )
    if not _windows_advapi32().CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, "Windows Credential Manager could not store the Worker token")


def _windows_credential_read(reference: str) -> str | None:
    advapi32 = _windows_advapi32()
    credential_pointer = ctypes.POINTER(_Credential)()
    if not advapi32.CredReadW(
        _credential_target(reference),
        1,
        0,
        ctypes.byref(credential_pointer),
    ):
        error = ctypes.get_last_error()
        if error == 1168:
            return None
        raise OSError(error, "Windows Credential Manager could not read the Worker token")
    try:
        credential = credential_pointer.contents
        blob = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        return blob.decode("utf-16-le")
    finally:
        advapi32.CredFree(credential_pointer)


def _windows_credential_delete(reference: str) -> None:
    advapi32 = _windows_advapi32()
    if not advapi32.CredDeleteW(_credential_target(reference), 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise OSError(error, "Windows Credential Manager could not delete the Worker token")


@dataclass(frozen=True, slots=True)
class RemoteRunResult:
    remote_run_id: str
    status: str
    output: str
    error: dict[str, Any] | None


class WorkerRuntime:
    def __init__(
        self,
        credentials: WorkerCredentialVault,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._transport = transport
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    async def health(self, worker: WorkerRecord) -> dict[str, Any]:
        token = self._token(worker)
        async with self._client(worker.timeout_seconds) as client:
            try:
                response = await client.get(
                    self._url(worker, "/worker/v1/health"),
                    headers=self._headers(token),
                )
            except httpx.TimeoutException as error:
                raise WorkerProtocolError(
                    "timeout",
                    "The Worker health check timed out.",
                ) from error
            except httpx.RequestError as error:
                raise WorkerProtocolError(
                    "disconnect",
                    "The Worker could not be reached.",
                ) from error
        if response.status_code in {401, 403}:
            raise WorkerProtocolError(
                "unauthorized",
                "The Worker rejected its configured credential.",
            )
        if response.status_code != 200:
            raise WorkerProtocolError(
                f"http_{response.status_code}",
                "The Worker health check failed.",
            )
        payload = _json_object(response)
        if payload.get("protocol_version") != WORKER_PROTOCOL_VERSION:
            raise WorkerProtocolError(
                "protocol_mismatch",
                "The Worker protocol version is not supported.",
            )
        if payload.get("status") != "ok":
            raise WorkerProtocolError(
                "unhealthy",
                "The Worker reported an unhealthy status.",
            )
        return payload

    async def execute(
        self,
        worker: WorkerRecord,
        *,
        input_text: str,
        parent_run_id: str,
        root_run_id: str,
        cancel_event: asyncio.Event,
        on_event: Callable[[dict[str, Any]], None],
    ) -> RemoteRunResult:
        token = self._token(worker)
        semaphore = self._semaphore(worker)
        try:
            async with semaphore, asyncio.timeout(worker.timeout_seconds):
                if cancel_event.is_set():
                    raise asyncio.CancelledError
                async with self._client(worker.timeout_seconds) as client:
                    remote_run_id = await self._start(
                        client,
                        worker,
                        token,
                        input_text=input_text,
                        parent_run_id=parent_run_id,
                        root_run_id=root_run_id,
                    )
                    try:
                        return await self._collect(
                            client,
                            worker,
                            token,
                            remote_run_id=remote_run_id,
                            cancel_event=cancel_event,
                            on_event=on_event,
                        )
                    except asyncio.CancelledError:
                        await self._cancel_remote(client, worker, token, remote_run_id)
                        raise
        except TimeoutError as error:
            raise WorkerProtocolError(
                "timeout",
                "The Worker run exceeded its configured timeout.",
            ) from error
        except httpx.TimeoutException as error:
            raise WorkerProtocolError(
                "timeout",
                "The Worker run timed out.",
            ) from error
        except httpx.RequestError as error:
            raise WorkerProtocolError(
                "disconnect",
                "The Worker disconnected before the run completed.",
            ) from error

    def _token(self, worker: WorkerRecord) -> str:
        token = self._credentials.get(worker.credential_ref)
        if token is None:
            raise WorkerProtocolError(
                "credential_missing",
                "No credential is configured for this Worker.",
            )
        return token

    def _semaphore(self, worker: WorkerRecord) -> asyncio.Semaphore:
        semaphore = self._semaphores.get(worker.worker_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(worker.max_concurrency)
            self._semaphores[worker.worker_id] = semaphore
        return semaphore

    def _client(self, timeout_seconds: int) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(float(timeout_seconds)),
            follow_redirects=False,
        )

    async def _start(
        self,
        client: httpx.AsyncClient,
        worker: WorkerRecord,
        token: str,
        *,
        input_text: str,
        parent_run_id: str,
        root_run_id: str,
    ) -> str:
        response = await client.post(
            self._url(worker, "/worker/v1/runs"),
            headers={**self._headers(token), "Content-Type": "application/json"},
            json={
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "agent_id": worker.agent_id,
                "version": worker.spec_version,
                "input": input_text,
                "parent_run_id": parent_run_id,
                "root_run_id": root_run_id,
            },
        )
        if response.status_code in {401, 403}:
            raise WorkerProtocolError(
                "unauthorized",
                "The Worker rejected its configured credential.",
            )
        if response.status_code != 202:
            raise WorkerProtocolError(
                f"http_{response.status_code}",
                "The Worker rejected the run request.",
            )
        payload = _json_object(response)
        remote_run_id = payload.get("remote_run_id")
        if not isinstance(remote_run_id, str) or not remote_run_id:
            raise WorkerProtocolError(
                "protocol_error",
                "The Worker returned an invalid run identifier.",
            )
        return remote_run_id

    async def _collect(
        self,
        client: httpx.AsyncClient,
        worker: WorkerRecord,
        token: str,
        *,
        remote_run_id: str,
        cancel_event: asyncio.Event,
        on_event: Callable[[dict[str, Any]], None],
    ) -> RemoteRunResult:
        url = self._url(worker, f"/worker/v1/runs/{remote_run_id}/events")
        collect = asyncio.create_task(
            self._read_event_stream(
                client,
                url,
                token,
                remote_run_id=remote_run_id,
                cancel_event=cancel_event,
                on_event=on_event,
            )
        )
        cancelled = asyncio.create_task(cancel_event.wait())
        done, _ = await asyncio.wait(
            {collect, cancelled},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancelled in done and collect not in done:
            collect.cancel()
            await asyncio.gather(collect, return_exceptions=True)
            raise asyncio.CancelledError
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        return await collect

    async def _read_event_stream(
        self,
        client: httpx.AsyncClient,
        url: str,
        token: str,
        *,
        remote_run_id: str,
        cancel_event: asyncio.Event,
        on_event: Callable[[dict[str, Any]], None],
    ) -> RemoteRunResult:
        async with client.stream(
            "GET",
            url,
            headers={**self._headers(token), "Accept": "text/event-stream"},
        ) as response:
            if response.status_code in {401, 403}:
                raise WorkerProtocolError(
                    "unauthorized",
                    "The Worker rejected its configured credential.",
                )
            if response.status_code != 200:
                raise WorkerProtocolError(
                    f"http_{response.status_code}",
                    "The Worker event stream could not be opened.",
                )
            async for line in response.aiter_lines():
                if cancel_event.is_set():
                    raise asyncio.CancelledError
                if not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if not raw:
                    continue
                try:
                    event = RuntimeEvent.model_validate(json.loads(raw))
                except (ValueError, TypeError) as error:
                    raise WorkerProtocolError(
                        "protocol_error",
                        "The Worker emitted an invalid runtime event.",
                    ) from error
                on_event(event.model_dump(mode="json"))
                terminal = _terminal(event)
                if terminal is not None:
                    return terminal
        raise WorkerProtocolError(
            "disconnect",
            "The Worker event stream ended before a terminal event.",
        )

    async def _cancel_remote(
        self,
        client: httpx.AsyncClient,
        worker: WorkerRecord,
        token: str,
        remote_run_id: str,
    ) -> None:
        try:
            await client.post(
                self._url(worker, f"/worker/v1/runs/{remote_run_id}/cancel"),
                headers=self._headers(token),
            )
        except httpx.RequestError:
            return

    @staticmethod
    def _url(worker: WorkerRecord, path: str) -> str:
        return f"{worker.base_url}{path}"

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


def _terminal(event: RuntimeEvent) -> RemoteRunResult | None:
    if event.type == RuntimeEventType.RUN_COMPLETED:
        return RemoteRunResult(
            remote_run_id=event.run_id,
            status="completed",
            output=str(event.payload.get("output", "")),
            error=None,
        )
    if event.type == RuntimeEventType.RUN_FAILED:
        raw_error = event.payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else {
            "code": "remote_run_failed",
            "message": "The Worker reported a failed run.",
        }
        return RemoteRunResult(
            remote_run_id=event.run_id,
            status="failed",
            output="",
            error=error,
        )
    if event.type == RuntimeEventType.RUN_CANCELLED:
        return RemoteRunResult(
            remote_run_id=event.run_id,
            status="cancelled",
            output="",
            error={
                "code": "worker_cancelled",
                "message": "The Worker cancelled the run.",
            },
        )
    return None


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise WorkerProtocolError(
            "protocol_error",
            "The Worker returned invalid JSON.",
        ) from error
    if not isinstance(payload, dict):
        raise WorkerProtocolError(
            "protocol_error",
            "The Worker returned an invalid response.",
        )
    return payload
