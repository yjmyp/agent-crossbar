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
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
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
from agent_crossbar.domain.knowledge import KnowledgeDocumentCreate
from agent_crossbar.domain.mcp import MCPServerCreate, MCPServerUpdate
from agent_crossbar.domain.spec import AgentSpec, CollaborationPolicy
from agent_crossbar.domain.worker import WorkerCreate, WorkerUpdate
from agent_crossbar.runtime.adapters import RuntimeAdapterRegistry
from agent_crossbar.runtime.catalog import (
    OpenAIConnectionConfig,
    ProviderCatalog,
    ProviderConfigurationError,
    ProviderProfile,
)
from agent_crossbar.runtime.delegation import DelegationCoordinator
from agent_crossbar.runtime.embeddings import (
    EmbeddingConfiguration,
    OpenAICompatibleEmbeddingClient,
)
from agent_crossbar.runtime.mcp_client import MCPClientError, MCPClientService
from agent_crossbar.runtime.tool_catalog import RuntimeToolCatalog
from agent_crossbar.runtime.tools import ToolExecutionError
from agent_crossbar.runtime.worker_runtime import (
    WORKER_PROTOCOL_VERSION,
    WorkerCredentialVault,
    WorkerProtocolError,
    WorkerRuntime,
)
from agent_crossbar.security import SecurityReviewService
from agent_crossbar.security.errors import (
    SecurityReviewError,
    SecurityReviewNotFoundError,
    SecurityWaiverNotFoundError,
)
from agent_crossbar.security.service import render_review_markdown
from agent_crossbar.storage.database import Database
from agent_crossbar.storage.evaluations import (
    DatasetInUseError,
    DatasetNotFoundError,
    DuplicateDatasetError,
    EvaluationBatchNotFoundError,
    EvaluationStore,
)
from agent_crossbar.storage.knowledge import (
    EmbeddingClient,
    KnowledgeDocumentRecord,
    KnowledgeNotFoundError,
    KnowledgeStore,
)
from agent_crossbar.storage.mcp import (
    MCPNotFoundError,
    MCPServerRecord,
    MCPStore,
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
    agent_id_for_name,
)
from agent_crossbar.storage.workers import (
    WorkerNotFoundError,
    WorkerRecord,
    WorkerStore,
)


@dataclass(frozen=True, slots=True)
class AppSettings:
    database_path: Path
    launch_token: str
    worker_inbound_token: str | None = None
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


class EmbeddingConnectionRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2_048)
    api_key: str = Field(min_length=1, max_length=4_096)
    model: str = Field(min_length=1, max_length=200)


class CreateEvaluationBatchRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=80)
    baseline_batch_id: str | None = Field(default=None, min_length=1, max_length=100)


class WorkerCredentialRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4_096)


class CreateSecurityReviewRequest(BaseModel):
    root: str = Field(min_length=1, max_length=4096)
    base: str | None = Field(default=None, max_length=200)
    staged: bool = False
    run_id: str | None = Field(default=None, min_length=1, max_length=100)
    policy_path: str | None = Field(default=None, max_length=4096)


class CreateSecurityWaiverRequest(BaseModel):
    rule_id: str = Field(min_length=1, max_length=80)
    file_pattern: str = Field(default="**", min_length=1, max_length=400)
    owner: str = Field(min_length=2, max_length=120)
    reason: str = Field(min_length=8, max_length=2000)
    expires_at: datetime


class InboundWorkerRunRequest(BaseModel):
    protocol_version: int
    agent_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=80)
    input: str = Field(min_length=1, max_length=100_000)
    parent_run_id: str | None = Field(default=None, min_length=1, max_length=100)
    root_run_id: str | None = Field(default=None, min_length=1, max_length=100)


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
    parent_run_id: str | None
    root_run_id: str | None
    delegation_depth: int


class RunTreeNode(BaseModel):
    run: RunResource
    children: list[RunTreeNode] = Field(default_factory=list)


class SpecValidationError(Exception):
    """Raised when a spec references unavailable capabilities or agents."""


def create_app(
    settings: AppSettings,
    *,
    provider_catalog: ProviderCatalog | None = None,
    embedding_client: EmbeddingClient | None = None,
    worker_credentials: WorkerCredentialVault | None = None,
) -> FastAPI:
    if not settings.launch_token:
        raise ValueError("launch_token must not be blank")

    catalog = provider_catalog or ProviderCatalog.from_environment(os.environ)
    embedder = embedding_client
    if embedder is None:
        embedding_configuration = EmbeddingConfiguration.from_environment(os.environ)
        if embedding_configuration is not None:
            embedder = OpenAICompatibleEmbeddingClient(
                base_url=embedding_configuration.base_url,
                api_key=embedding_configuration.api_key,
                model=embedding_configuration.model,
            )
    database = Database(settings.database_path)
    spec_store = SpecStore(database)
    run_store = RunStore(database)
    evaluation_store = EvaluationStore(database)
    mcp_store = MCPStore(database)
    mcp_service = MCPClientService(mcp_store)
    knowledge_store = KnowledgeStore(database, embedder=embedder)
    tool_catalog = RuntimeToolCatalog(knowledge_store, mcp_service)
    worker_store = WorkerStore(database)
    security_service = SecurityReviewService(database)
    credentials = worker_credentials or WorkerCredentialVault()
    worker_runtime = WorkerRuntime(credentials)
    delegation = DelegationCoordinator(
        run_store,
        spec_store,
        worker_store=worker_store,
        worker_runtime=worker_runtime,
    )
    run_executor = RunExecutor(
        run_store,
        runtime_factory=lambda spec: RuntimeAdapterRegistry(
            provider=catalog.provider_for(spec.model_profile),
            tool_registry=tool_catalog.registry(),
            delegation=delegation,
        ).create(spec),
    )
    delegation.bind(run_executor)
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
    app.state.mcp_store = mcp_store
    app.state.mcp_service = mcp_service
    app.state.knowledge_store = knowledge_store
    app.state.tool_catalog = tool_catalog
    app.state.worker_store = worker_store
    app.state.security_service = security_service
    app.state.worker_credentials = credentials
    app.state.worker_runtime = worker_runtime
    app.state.delegation = delegation
    app.state.run_executor = run_executor
    app.state.evaluation_executor = evaluation_executor
    app.state.provider_catalog = catalog
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
        is_worker_route = request.url.path.startswith("/worker/")
        expected_token = (
            settings.worker_inbound_token
            if is_worker_route
            else settings.launch_token
        )
        if not has_valid_bearer_token(
            request.headers.get("Authorization"),
            expected_token or "",
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": (
                            "A valid Worker inbound token is required."
                            if is_worker_route
                            else "A valid per-launch bearer token is required."
                        ),
                    }
                },
                headers={"X-Request-ID": request_id, "WWW-Authenticate": "Bearer"},
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(SecurityReviewError)
    async def handle_security_review_error(
        _: Request,
        error: SecurityReviewError,
    ) -> JSONResponse:
        return _error_response(422, "security_review_failed", str(error))

    @app.exception_handler(SecurityReviewNotFoundError)
    async def handle_security_review_not_found(
        _: Request,
        __: SecurityReviewNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            404, "security_review_not_found", "The security review was not found."
        )

    @app.exception_handler(SecurityWaiverNotFoundError)
    async def handle_security_waiver_not_found(
        _: Request,
        __: SecurityWaiverNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            404, "security_waiver_not_found", "The security waiver was not found."
        )

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

    @app.exception_handler(SpecValidationError)
    async def handle_spec_validation(
        _: Request,
        error: SpecValidationError,
    ) -> JSONResponse:
        return _error_response(422, "invalid_agent_spec", str(error))

    @app.exception_handler(ToolExecutionError)
    async def handle_tool_catalog_error(
        _: Request,
        error: ToolExecutionError,
    ) -> JSONResponse:
        return _error_response(422, error.code, str(error))

    @app.exception_handler(MCPNotFoundError)
    async def handle_mcp_not_found(_: Request, __: MCPNotFoundError) -> JSONResponse:
        return _error_response(404, "mcp_not_found", "The MCP resource was not found.")

    @app.exception_handler(MCPClientError)
    async def handle_mcp_client_error(_: Request, error: MCPClientError) -> JSONResponse:
        return _error_response(422, error.code, str(error))

    @app.exception_handler(KnowledgeNotFoundError)
    async def handle_knowledge_not_found(
        _: Request,
        __: KnowledgeNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            404,
            "knowledge_not_found",
            "The knowledge document was not found.",
        )

    @app.exception_handler(WorkerNotFoundError)
    async def handle_worker_not_found(
        _: Request,
        __: WorkerNotFoundError,
    ) -> JSONResponse:
        return _error_response(404, "worker_not_found", "The Worker was not found.")

    @app.exception_handler(WorkerProtocolError)
    async def handle_worker_protocol_error(
        _: Request,
        error: WorkerProtocolError,
    ) -> JSONResponse:
        return _error_response(502, error.code, error.message)

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

    @app.get("/worker/v1/health")
    async def worker_health() -> dict[str, object]:
        return {
            "status": "ok",
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "version": __version__,
        }

    @app.post("/worker/v1/runs", status_code=202, response_model=None)
    async def start_inbound_worker_run(
        payload: InboundWorkerRunRequest,
    ) -> dict[str, object] | JSONResponse:
        if payload.protocol_version != WORKER_PROTOCOL_VERSION:
            return _error_response(
                422,
                "worker_protocol_mismatch",
                "The Worker protocol version is not supported.",
            )
        spec_record = spec_store.get(payload.agent_id, payload.version)
        catalog.provider_for(spec_record.spec.model_profile)
        tool_catalog.validate_names(tuple(tool.name for tool in spec_record.spec.tools))
        _validate_spec_members(spec_record.spec, spec_store)
        run = run_store.create(
            agent_id=spec_record.agent_id,
            spec_version=spec_record.spec.version,
            input_text=payload.input,
        )
        run_executor.submit(
            run,
            spec_record.spec,
            initial_event_payload={
                "external_parent_run_id": payload.parent_run_id,
                "external_root_run_id": payload.root_run_id,
                "control_plane_boundary": True,
            },
        )
        return {
            "remote_run_id": run.run_id,
            "status": "queued",
            "protocol_version": WORKER_PROTOCOL_VERSION,
        }

    @app.get("/worker/v1/runs/{run_id}/events")
    async def stream_inbound_worker_run_events(
        request: Request,
        run_id: str,
    ) -> StreamingResponse:
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

    @app.post("/worker/v1/runs/{run_id}/cancel", status_code=202)
    async def cancel_inbound_worker_run(run_id: str) -> dict[str, object]:
        run = run_store.get(run_id)
        if run.status not in TERMINAL_RUN_STATUSES:
            await run_executor.cancel(run_id)
        return _run_resource(run_store.get(run_id)).model_dump(mode="json")

    @app.post("/v1/specs", status_code=201)
    async def create_spec(spec: AgentSpec) -> dict[str, object]:
        tool_catalog.validate_names(tuple(tool.name for tool in spec.tools))
        _validate_spec_collaboration(spec, spec_store)
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
        return [
            definition.model_dump(mode="json") for definition in tool_catalog.available()
        ]

    @app.post("/v1/workers", status_code=201)
    async def create_worker(payload: WorkerCreate) -> dict[str, object]:
        return _worker_resource(worker_store.create(payload), credentials)

    @app.get("/v1/workers")
    async def list_workers() -> list[dict[str, object]]:
        return [
            _worker_resource(record, credentials)
            for record in worker_store.list()
        ]

    @app.get("/v1/workers/{worker_id}")
    async def get_worker(worker_id: str) -> dict[str, object]:
        return _worker_resource(worker_store.get(worker_id), credentials)

    @app.put("/v1/workers/{worker_id}")
    async def update_worker(
        worker_id: str,
        payload: WorkerUpdate,
    ) -> dict[str, object]:
        return _worker_resource(
            worker_store.set_enabled(worker_id, payload.enabled),
            credentials,
        )

    @app.put("/v1/workers/{worker_id}/credential", status_code=204)
    async def set_worker_credential(
        worker_id: str,
        payload: WorkerCredentialRequest,
    ) -> None:
        worker = worker_store.get(worker_id)
        credentials.set(worker.credential_ref, payload.token)

    @app.delete("/v1/workers/{worker_id}", status_code=204)
    async def delete_worker(worker_id: str) -> None:
        worker = worker_store.get(worker_id)
        worker_store.delete(worker_id)
        credentials.delete(worker.credential_ref)

    @app.post("/v1/workers/{worker_id}/health")
    async def check_worker_health(worker_id: str) -> dict[str, object]:
        worker = worker_store.get(worker_id)
        payload = await worker_runtime.health(worker)
        return {
            "worker_id": worker.worker_id,
            "status": payload["status"],
            "protocol_version": payload["protocol_version"],
            "version": payload.get("version"),
            "checked_at": datetime.now().astimezone().isoformat(),
        }

    @app.post("/v1/mcp/servers", status_code=201)
    async def create_mcp_server(payload: MCPServerCreate) -> dict[str, object]:
        return _mcp_server_resource(mcp_store.create(payload), mcp_store)

    @app.get("/v1/mcp/servers")
    async def list_mcp_servers() -> list[dict[str, object]]:
        return [_mcp_server_resource(server, mcp_store) for server in mcp_store.list()]

    @app.put("/v1/mcp/servers/{server_id}")
    async def update_mcp_server(
        server_id: str,
        payload: MCPServerUpdate,
    ) -> dict[str, object]:
        return _mcp_server_resource(
            mcp_store.set_enabled(server_id, payload.enabled),
            mcp_store,
        )

    @app.post("/v1/mcp/servers/{server_id}/discover")
    async def discover_mcp_server(server_id: str) -> dict[str, object]:
        await mcp_service.discover(server_id)
        return _mcp_server_resource(mcp_store.get(server_id), mcp_store)

    @app.delete("/v1/mcp/servers/{server_id}", status_code=204)
    async def delete_mcp_server(server_id: str) -> None:
        mcp_store.delete(server_id)

    @app.post("/v1/knowledge/documents", status_code=201)
    async def create_knowledge_document(
        payload: KnowledgeDocumentCreate,
    ) -> dict[str, object]:
        return _knowledge_document_resource(await knowledge_store.ingest(payload))

    @app.get("/v1/knowledge/documents")
    async def list_knowledge_documents() -> list[dict[str, object]]:
        return [
            _knowledge_document_resource(document)
            for document in knowledge_store.list()
        ]

    @app.delete("/v1/knowledge/documents/{document_id}", status_code=204)
    async def delete_knowledge_document(document_id: str) -> None:
        knowledge_store.delete(document_id)

    @app.get("/v1/knowledge/search")
    async def search_knowledge(
        q: str,
        limit: int = 6,
        mode: str = "auto",
    ) -> dict[str, object]:
        if not q.strip() or len(q) > 500:
            raise SpecValidationError("knowledge query must contain 1 to 500 characters")
        if limit < 1 or limit > 20:
            raise SpecValidationError("knowledge search limit must be between 1 and 20")
        if mode not in {"auto", "lexical", "vector", "hybrid"}:
            raise SpecValidationError(
                "knowledge search mode must be auto, lexical, vector, or hybrid"
            )
        result = await knowledge_store.search_with_mode(q, limit=limit, mode=mode)
        return {"query": q, **result.as_dict()}

    @app.get("/v1/knowledge/index")
    async def get_knowledge_index_status() -> dict[str, object]:
        return (await knowledge_store.index_status()).as_dict()

    @app.post("/v1/knowledge/index/rebuild")
    async def rebuild_knowledge_index() -> dict[str, object]:
        return (await knowledge_store.rebuild_index()).as_dict()

    @app.put("/v1/knowledge/embedding/configuration")
    async def configure_embedding(
        payload: EmbeddingConnectionRequest,
    ) -> dict[str, object]:
        knowledge_store.set_embedder(
            OpenAICompatibleEmbeddingClient(
                base_url=payload.base_url,
                api_key=payload.api_key,
                model=payload.model,
            )
        )
        return (await knowledge_store.index_status()).as_dict()

    @app.delete("/v1/knowledge/embedding/configuration")
    async def remove_embedding() -> dict[str, object]:
        knowledge_store.set_embedder(None)
        return (await knowledge_store.index_status()).as_dict()

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
        tool_catalog.validate_names(tuple(tool.name for tool in spec_record.spec.tools))
        _validate_spec_members(spec_record.spec, spec_store)
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

    @app.get("/v1/runs/{run_id}/tree")
    async def get_run_tree(run_id: str) -> RunTreeNode:
        records = run_store.list_subtree(run_id)
        run = records[0]
        children_by_parent: dict[str, list[RunRecord]] = {}
        for descendant in records[1:]:
            if descendant.parent_run_id is not None:
                children_by_parent.setdefault(descendant.parent_run_id, []).append(descendant)

        def build(record: RunRecord) -> RunTreeNode:
            return RunTreeNode(
                run=_run_resource(record),
                children=[
                    build(child)
                    for child in children_by_parent.get(record.run_id, [])
                ],
            )

        return build(run)

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

    @app.post("/v1/security/reviews", status_code=201)
    async def create_security_review(
        payload: CreateSecurityReviewRequest,
    ) -> dict[str, object]:
        review = security_service.create_review(
            root=payload.root,
            base=payload.base,
            staged=payload.staged,
            run_id=payload.run_id,
            policy_path=payload.policy_path,
        )
        return review.payload

    @app.get("/v1/security/reviews")
    async def list_security_reviews(limit: int = 50) -> list[dict[str, object]]:
        return [record.payload for record in security_service.list_reviews(limit=limit)]

    @app.get("/v1/security/reviews/{review_id}")
    async def get_security_review(review_id: str) -> dict[str, object]:
        return security_service.get_review(review_id).payload

    @app.get("/v1/security/reviews/{review_id}/markdown")
    async def get_security_review_markdown(review_id: str) -> PlainTextResponse:
        payload = security_service.get_review(review_id).payload
        return PlainTextResponse(
            render_review_markdown(payload),
            media_type="text/markdown; charset=utf-8",
        )

    @app.get("/v1/security/waivers")
    async def list_security_waivers() -> list[dict[str, object]]:
        return security_service.list_waivers()

    @app.post("/v1/security/waivers", status_code=201)
    async def create_security_waiver(
        payload: CreateSecurityWaiverRequest,
    ) -> dict[str, object]:
        return security_service.create_waiver(
            rule_id=payload.rule_id,
            file_pattern=payload.file_pattern,
            owner=payload.owner,
            reason=payload.reason,
            expires_at=payload.expires_at,
        )

    @app.delete("/v1/security/waivers/{waiver_id}")
    async def revoke_security_waiver(waiver_id: str) -> dict[str, object]:
        return security_service.revoke_waiver(waiver_id)

    @app.get("/v1/security/policy")
    async def get_security_policy() -> dict[str, object]:
        policy = security_service.policy
        return {
            "name": policy.name,
            "clauses": [
                {
                    "id": clause.clause_id,
                    "title": clause.title,
                    "text": clause.text,
                    "severity": clause.severity,
                }
                for clause in policy.clauses
            ],
            "budgets": policy.budgets,
        }

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
        parent_run_id=record.parent_run_id,
        root_run_id=record.root_run_id,
        delegation_depth=record.delegation_depth,
    )


def _worker_resource(
    record: WorkerRecord,
    credentials: WorkerCredentialVault,
) -> dict[str, object]:
    return {
        "worker_id": record.worker_id,
        "label": record.label,
        "base_url": record.base_url,
        "agent_id": record.agent_id,
        "version": record.spec_version,
        "credential_ref": record.credential_ref,
        "credential_configured": record.credential_ref in credentials,
        "max_concurrency": record.max_concurrency,
        "timeout_seconds": record.timeout_seconds,
        "enabled": record.enabled,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _mcp_server_resource(record: MCPServerRecord, store: MCPStore) -> dict[str, object]:
    return {
        "server_id": record.server_id,
        "label": record.label,
        "transport": record.transport,
        "command": record.command,
        "url": record.url,
        "args": list(record.args),
        "env_keys": list(record.env_keys),
        "enabled": record.enabled,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "tools": [
            {
                "server_id": tool.server_id,
                "tool_name": tool.tool_name,
                "exposed_name": tool.exposed_name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "discovered_at": tool.discovered_at.isoformat(),
            }
            for tool in store.list_tools(record.server_id)
        ],
    }


def _knowledge_document_resource(record: KnowledgeDocumentRecord) -> dict[str, object]:
    return {
        "document_id": record.document_id,
        "title": record.title,
        "source_name": record.source_name,
        "content_digest": record.content_digest,
        "chunk_count": record.chunk_count,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _validate_spec_collaboration(spec: AgentSpec, spec_store: SpecStore) -> None:
    policy = spec.collaboration
    if policy.mode == "single":
        return
    prospective_agent_id = agent_id_for_name(spec.name)
    for member in policy.members:
        if (
            member.agent_id == prospective_agent_id
            and member.version == spec.version
        ):
            raise SpecValidationError(
                "an agent version cannot delegate directly to itself"
            )
        try:
            spec_store.get(member.agent_id, member.version)
        except SpecNotFoundError as error:
            raise SpecValidationError(
                f"collaboration member {member.agent_id}@{member.version} does not exist"
            ) from error


def _validate_spec_members(spec: AgentSpec, spec_store: SpecStore) -> None:
    _validate_policy_members(spec.collaboration, spec_store)


def _validate_policy_members(
    policy: CollaborationPolicy,
    spec_store: SpecStore,
) -> None:
    if policy.mode == "single":
        return
    seen: set[tuple[str, str]] = set()
    for member in policy.members:
        key = (member.agent_id, member.version)
        if key in seen:
            raise SpecValidationError(
                f"collaboration member {member.agent_id}@{member.version} is duplicated"
            )
        seen.add(key)
        try:
            spec_store.get(member.agent_id, member.version)
        except SpecNotFoundError as error:
            raise SpecValidationError(
                f"collaboration member {member.agent_id}@{member.version} does not exist"
            ) from error


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
