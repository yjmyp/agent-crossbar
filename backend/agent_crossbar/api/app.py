from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_crossbar import __version__
from agent_crossbar.api.auth import has_valid_bearer_token
from agent_crossbar.api.run_service import RunExecutor
from agent_crossbar.domain.events import RuntimeEvent
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.native import EchoProvider, NativeRuntime
from agent_crossbar.runtime.tools import build_default_tool_registry
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.runs import (
    TERMINAL_RUN_STATUSES,
    RunNotFoundError,
    RunRecord,
    RunStore,
)
from agent_crossbar.storage.specs import (
    AgentSpecRecord,
    DuplicateSpecError,
    SpecNotFoundError,
    SpecStore,
)


@dataclass(frozen=True, slots=True)
class AppSettings:
    database_path: Path
    launch_token: str
    allowed_origins: tuple[str, ...] = (
        "http://localhost:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    )


class CreateRunRequest(BaseModel):
    spec_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=80)
    input: str = Field(min_length=1, max_length=100_000)


class RunResource(BaseModel):
    run_id: str
    agent_id: str
    spec_version: str
    input: str
    status: str
    output: str | None
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def create_app(settings: AppSettings) -> FastAPI:
    if not settings.launch_token:
        raise ValueError("launch_token must not be blank")

    database = Database(settings.database_path)
    spec_store = SpecStore(database)
    run_store = RunStore(database)
    run_executor = RunExecutor(
        run_store,
        runtime_factory=lambda: NativeRuntime(
            provider=EchoProvider(),
            tool_registry=build_default_tool_registry(),
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await run_executor.shutdown()
        database.close()

    app = FastAPI(
        title="Agent Crossbar Local API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.spec_store = spec_store
    app.state.run_store = run_store
    app.state.run_executor = run_executor
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
        if request.method == "OPTIONS":
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        if not has_valid_bearer_token(
            request.headers.get("Authorization"),
            settings.launch_token,
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": "A valid per-launch bearer token is required.",
                    }
                },
                headers={"X-Request-ID": request_id, "WWW-Authenticate": "Bearer"},
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(SpecNotFoundError)
    async def handle_spec_not_found(_: Request, __: SpecNotFoundError) -> JSONResponse:
        return _error_response(404, "spec_not_found", "The requested agent version was not found.")

    @app.exception_handler(RunNotFoundError)
    async def handle_run_not_found(_: Request, __: RunNotFoundError) -> JSONResponse:
        return _error_response(404, "run_not_found", "The requested run was not found.")

    @app.exception_handler(DuplicateSpecError)
    async def handle_duplicate_spec(_: Request, __: DuplicateSpecError) -> JSONResponse:
        return _error_response(
            409,
            "duplicate_spec",
            "That agent version already exists. Create a new version instead.",
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "database": "ready"}

    @app.post("/v1/specs", status_code=201)
    async def create_spec(spec: AgentSpec) -> dict[str, object]:
        return _spec_resource(spec_store.create(spec))

    @app.get("/v1/specs")
    async def list_specs() -> list[dict[str, object]]:
        return [_spec_resource(record) for record in spec_store.list()]

    @app.post("/v1/runs", status_code=202)
    async def create_run(payload: CreateRunRequest) -> dict[str, object]:
        spec_record = spec_store.get(payload.spec_id, payload.version)
        run = run_store.create(
            agent_id=spec_record.agent_id,
            spec_version=spec_record.spec.version,
            input_text=payload.input,
        )
        run_executor.submit(run, spec_record.spec)
        return _run_resource(run).model_dump(mode="json")

    @app.get("/v1/runs")
    async def list_runs() -> list[dict[str, object]]:
        return [_run_resource(record).model_dump(mode="json") for record in run_store.list()]

    @app.get("/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        return _run_resource(run_store.get(run_id)).model_dump(mode="json")

    @app.post("/v1/runs/{run_id}/cancel", status_code=202)
    async def cancel_run(run_id: str) -> dict[str, object]:
        run = run_store.get(run_id)
        if run.status not in TERMINAL_RUN_STATUSES:
            await run_executor.cancel(run_id)
        return _run_resource(run_store.get(run_id)).model_dump(mode="json")

    @app.get("/v1/runs/{run_id}/events")
    async def stream_run_events(request: Request, run_id: str) -> StreamingResponse:
        run_store.get(run_id)
        after_sequence = _parse_after_sequence(request)

        async def event_stream() -> AsyncIterator[str]:
            cursor = after_sequence
            while True:
                events = run_store.list_events(run_id, after_sequence=cursor)
                for event in events:
                    cursor = event.sequence
                    yield _format_sse(event)
                run = run_store.get(run_id)
                if run.status in TERMINAL_RUN_STATUSES and not events:
                    break
                if await request.is_disconnected():
                    break
                await asyncio.sleep(0.05)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def _spec_resource(record: AgentSpecRecord) -> dict[str, object]:
    return {
        "agent_id": record.agent_id,
        "digest": record.digest,
        "created_at": record.created_at.isoformat(),
        "spec": record.spec.model_dump(mode="json"),
    }


def _run_resource(record: RunRecord) -> RunResource:
    return RunResource(
        run_id=record.run_id,
        agent_id=record.agent_id,
        spec_version=record.spec_version,
        input=record.input_text,
        status=record.status.value,
        output=record.output,
        error=record.error,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _parse_after_sequence(request: Request) -> int:
    raw_value = request.headers.get("Last-Event-ID") or request.query_params.get("after", "0")
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 0


def _format_sse(event: RuntimeEvent) -> str:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.sequence}\nevent: runtime_event\ndata: {data}\n\n"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
