from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_crossbar import __version__
from agent_crossbar.api.auth import has_valid_bearer_token
from agent_crossbar.api.compare import (
    RunComparison,
    RunsNotComparableError,
    SameRunError,
    build_run_comparison,
)
from agent_crossbar.api.evaluation_service import (
    EvaluationExecutor,
    InvalidEvaluationRequest,
    batch_resource,
    dataset_resource,
)
from agent_crossbar.api.run_service import RunExecutor
from agent_crossbar.domain.evaluation import EvaluationDataset
from agent_crossbar.domain.events import RuntimeEvent
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.runtime.catalog import (
    OpenAIConnectionConfig,
    ProviderCatalog,
    ProviderConfigurationError,
    ProviderProfile,
)
from agent_crossbar.runtime.native import NativeRuntime
from agent_crossbar.runtime.tools import build_default_tool_registry
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.evaluations import (
    DatasetInUseError,
    DatasetNotFoundError,
    DuplicateDatasetError,
    EvaluationBatchNotFoundError,
    EvaluationStore,
)
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


class CreateEvaluationBatchRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=80)
    baseline_batch_id: str | None = Field(default=None, min_length=1, max_length=100)


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


def create_app(
    settings: AppSettings,
    *,
    provider_catalog: ProviderCatalog | None = None,
) -> FastAPI:
    if not settings.launch_token:
        raise ValueError("launch_token must not be blank")

    catalog = provider_catalog or ProviderCatalog.from_environment(os.environ)
    tool_registry = build_default_tool_registry()
    database = Database(settings.database_path)
    spec_store = SpecStore(database)
    run_store = RunStore(database)
    evaluation_store = EvaluationStore(database)
    run_executor = RunExecutor(
        run_store,
        runtime_factory=lambda spec: NativeRuntime(
            provider=catalog.provider_for(spec.model_profile),
            tool_registry=tool_registry,
        ),
    )
    evaluation_executor = EvaluationExecutor(
        evaluation_store=evaluation_store,
        run_store=run_store,
        run_executor=run_executor,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await evaluation_executor.shutdown()
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
    app.state.evaluation_store = evaluation_store
    app.state.run_executor = run_executor
    app.state.evaluation_executor = evaluation_executor
    app.state.provider_catalog = catalog
    app.state.tool_registry = tool_registry
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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

    @app.exception_handler(SameRunError)
    async def handle_same_run(_: Request, __: SameRunError) -> JSONResponse:
        return _error_response(
            400,
            "same_run",
            "Choose two different runs before comparing evidence.",
        )

    @app.exception_handler(RunsNotComparableError)
    async def handle_runs_not_comparable(
        _: Request,
        __: RunsNotComparableError,
    ) -> JSONResponse:
        return _error_response(
            409,
            "runs_not_terminal",
            "Wait for both runs to reach a terminal state before comparing them.",
        )

    @app.exception_handler(DatasetNotFoundError)
    async def handle_dataset_not_found(
        _: Request,
        __: DatasetNotFoundError,
    ) -> JSONResponse:
        return _error_response(404, "dataset_not_found", "The evaluation dataset was not found.")

    @app.exception_handler(EvaluationBatchNotFoundError)
    async def handle_evaluation_batch_not_found(
        _: Request,
        __: EvaluationBatchNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            404,
            "evaluation_batch_not_found",
            "The evaluation batch was not found.",
        )

    @app.exception_handler(DuplicateDatasetError)
    async def handle_duplicate_dataset(
        _: Request,
        __: DuplicateDatasetError,
    ) -> JSONResponse:
        return _error_response(
            409,
            "duplicate_dataset",
            "That dataset name and version already exist.",
        )

    @app.exception_handler(DatasetInUseError)
    async def handle_dataset_in_use(_: Request, __: DatasetInUseError) -> JSONResponse:
        return _error_response(
            409,
            "dataset_in_use",
            "This dataset is referenced by an evaluation batch and cannot be deleted.",
        )

    @app.exception_handler(InvalidEvaluationRequest)
    async def handle_invalid_evaluation_request(
        _: Request,
        error: InvalidEvaluationRequest,
    ) -> JSONResponse:
        return _error_response(422, "invalid_evaluation_request", str(error))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _: Request,
        __: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            422,
            "validation_error",
            "The request did not match the required schema.",
        )

    @app.exception_handler(ProviderConfigurationError)
    async def handle_provider_configuration(
        _: Request,
        error: ProviderConfigurationError,
    ) -> JSONResponse:
        return _error_response(422, error.code, str(error))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "database": "ready"}

    @app.post("/v1/specs", status_code=201)
    async def create_spec(spec: AgentSpec) -> dict[str, object]:
        return _spec_resource(spec_store.create(spec))

    @app.get("/v1/specs")
    async def list_specs() -> list[dict[str, object]]:
        return [_spec_resource(record) for record in spec_store.list()]

    @app.get("/v1/providers")
    async def list_providers() -> list[ProviderProfile]:
        return catalog.list_public()

    @app.put("/v1/providers/openai.default/configuration")
    async def configure_openai_provider(payload: OpenAIConnectionConfig) -> ProviderProfile:
        return catalog.configure_openai(payload)

    @app.delete("/v1/providers/openai.default/configuration")
    async def remove_openai_provider() -> ProviderProfile:
        return catalog.remove_openai()

    @app.post("/v1/providers/openai.default/test")
    async def test_openai_provider() -> dict[str, object]:
        await catalog.test_openai_connection()
        return {"ok": True, "message": "Connection succeeded."}

    @app.get("/v1/tools")
    async def list_tools() -> list[dict[str, object]]:
        return [definition.model_dump(mode="json") for definition in tool_registry.available()]

    @app.post("/v1/evaluation/datasets", status_code=201)
    async def create_evaluation_dataset(dataset: EvaluationDataset) -> dict[str, object]:
        return dataset_resource(evaluation_store.create_dataset(dataset)).model_dump(mode="json")

    @app.get("/v1/evaluation/datasets")
    async def list_evaluation_datasets() -> list[dict[str, object]]:
        return [
            dataset_resource(record).model_dump(mode="json")
            for record in evaluation_store.list_datasets()
        ]

    @app.get("/v1/evaluation/datasets/{dataset_id}")
    async def get_evaluation_dataset(dataset_id: str) -> dict[str, object]:
        return dataset_resource(evaluation_store.get_dataset(dataset_id)).model_dump(mode="json")

    @app.delete("/v1/evaluation/datasets/{dataset_id}", status_code=204)
    async def delete_evaluation_dataset(dataset_id: str) -> None:
        evaluation_store.delete_dataset(dataset_id)

    @app.post("/v1/evaluation/batches", status_code=202)
    async def create_evaluation_batch(
        payload: CreateEvaluationBatchRequest,
    ) -> dict[str, object]:
        dataset = evaluation_store.get_dataset(payload.dataset_id)
        spec_record = spec_store.get(payload.agent_id, payload.version)
        catalog.provider_for(spec_record.spec.model_profile)
        if payload.baseline_batch_id is not None:
            baseline = evaluation_store.get_batch(payload.baseline_batch_id)
            if baseline.dataset_id != dataset.dataset_id:
                raise InvalidEvaluationRequest(
                    "The baseline batch must use the same evaluation dataset."
                )
        batch = evaluation_store.create_batch(
            dataset_id=dataset.dataset_id,
            agent_id=spec_record.agent_id,
            spec_version=spec_record.spec.version,
            baseline_batch_id=payload.baseline_batch_id,
        )
        evaluation_executor.submit(batch, spec_record.spec)
        return batch_resource(batch).model_dump(mode="json")

    @app.get("/v1/evaluation/batches")
    async def list_evaluation_batches() -> list[dict[str, object]]:
        return [
            batch_resource(record).model_dump(mode="json")
            for record in evaluation_store.list_batches()
        ]

    @app.get("/v1/evaluation/batches/{batch_id}")
    async def get_evaluation_batch(batch_id: str) -> dict[str, object]:
        return batch_resource(evaluation_store.get_batch(batch_id)).model_dump(mode="json")

    @app.post("/v1/runs", status_code=202)
    async def create_run(payload: CreateRunRequest) -> dict[str, object]:
        spec_record = spec_store.get(payload.spec_id, payload.version)
        catalog.provider_for(spec_record.spec.model_profile)
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

    @app.get("/v1/compare")
    async def compare_runs(left_run_id: str, right_run_id: str) -> RunComparison:
        return build_run_comparison(
            left_run_id=left_run_id,
            right_run_id=right_run_id,
            run_store=run_store,
            spec_store=spec_store,
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
