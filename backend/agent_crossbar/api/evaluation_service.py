from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from agent_crossbar.api.run_service import RunExecutor
from agent_crossbar.domain.evaluation import EvaluationCase, EvaluationStatus
from agent_crossbar.domain.spec import AgentSpec
from agent_crossbar.storage.evaluations import (
    EvaluationBatchRecord,
    EvaluationDatasetRecord,
    EvaluationStore,
)
from agent_crossbar.storage.runs import TERMINAL_RUN_STATUSES, RunRecord, RunStore


class InvalidEvaluationRequest(Exception):
    """Raised when an evaluation request cannot be executed as specified."""


class EvaluationDatasetResource(BaseModel):
    dataset_id: str
    digest: str
    created_at: datetime
    dataset: dict[str, Any]


class EvaluationCaseResultResource(BaseModel):
    case_id: str
    case_name: str
    status: str
    run_id: str | None
    latency_ms: int | None
    output: str | None
    failure_reason: str | None


class EvaluationBatchResource(BaseModel):
    batch_id: str
    dataset_id: str
    agent_id: str
    spec_version: str
    baseline_batch_id: str | None
    status: str
    gate_status: str
    metrics: dict[str, Any]
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    results: list[EvaluationCaseResultResource]


class EvaluationExecutor:
    def __init__(
        self,
        *,
        evaluation_store: EvaluationStore,
        run_store: RunStore,
        run_executor: RunExecutor,
    ) -> None:
        self._evaluation_store = evaluation_store
        self._run_store = run_store
        self._run_executor = run_executor
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(self, batch: EvaluationBatchRecord, spec: AgentSpec) -> None:
        task = asyncio.create_task(
            self._execute(batch, spec),
            name=f"agent-evaluation-{batch.batch_id}",
        )
        self._tasks[batch.batch_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(batch.batch_id, None))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(
        self,
        batch: EvaluationBatchRecord,
        spec: AgentSpec,
    ) -> None:
        try:
            self._evaluation_store.mark_batch_running(batch.batch_id)
            dataset = self._evaluation_store.get_dataset(batch.dataset_id)
            for case in dataset.dataset.cases:
                await self._execute_case(batch, spec, case)

            completed = self._evaluation_store.get_batch(batch.batch_id)
            metrics = _metrics(completed)
            gate_status = self._gate_status(completed, metrics)
            self._evaluation_store.finish_batch(
                batch.batch_id,
                status=EvaluationStatus.COMPLETED,
                gate_status=gate_status,
                metrics=metrics,
            )
        except asyncio.CancelledError:
            self._mark_unfinished_cases(batch.batch_id, "评测任务已取消。")
            with suppress(Exception):
                self._evaluation_store.finish_batch(
                    batch.batch_id,
                    status=EvaluationStatus.CANCELLED,
                    gate_status="not_evaluated",
                    metrics=_metrics(self._evaluation_store.get_batch(batch.batch_id)),
                    error={"code": "evaluation_cancelled", "message": "评测任务已取消。"},
                )
            raise
        except Exception:
            self._mark_unfinished_cases(batch.batch_id, "评测执行器意外终止。")
            with suppress(Exception):
                self._evaluation_store.finish_batch(
                    batch.batch_id,
                    status=EvaluationStatus.FAILED,
                    gate_status="not_evaluated",
                    metrics=_metrics(self._evaluation_store.get_batch(batch.batch_id)),
                    error={
                        "code": "evaluation_executor_error",
                        "message": "评测执行器意外终止。",
                    },
                )

    async def _execute_case(
        self,
        batch: EvaluationBatchRecord,
        spec: AgentSpec,
        case: EvaluationCase,
    ) -> None:
        run = self._run_store.create(
            agent_id=batch.agent_id,
            spec_version=batch.spec_version,
            input_text=case.input,
        )
        self._evaluation_store.update_case_result(
            batch.batch_id,
            case.case_id,
            status=EvaluationStatus.RUNNING,
            run_id=run.run_id,
        )
        started = asyncio.get_running_loop().time()
        self._run_executor.submit(run, spec)
        terminal = await self._wait_for_terminal(
            run.run_id,
            timeout_seconds=spec.execution.timeout_seconds + 10,
        )
        latency_ms = _duration_ms(terminal, started)
        if terminal.status != "completed" or terminal.output is None:
            self._evaluation_store.update_case_result(
                batch.batch_id,
                case.case_id,
                status=EvaluationStatus.ERROR,
                run_id=terminal.run_id,
                latency_ms=latency_ms,
                output=terminal.output,
                failure_reason=_run_failure_reason(terminal),
            )
            return

        passed, failure_reason = _assert_output(case, terminal.output)
        self._evaluation_store.update_case_result(
            batch.batch_id,
            case.case_id,
            status=EvaluationStatus.PASSED if passed else EvaluationStatus.FAILED,
            run_id=terminal.run_id,
            latency_ms=latency_ms,
            output=terminal.output,
            failure_reason=failure_reason,
        )

    async def _wait_for_terminal(
        self,
        run_id: str,
        *,
        timeout_seconds: int,
    ) -> RunRecord:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            run = self._run_store.get(run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            await asyncio.sleep(0.03)
        raise TimeoutError(f"evaluation run {run_id} did not reach a terminal state")

    def _mark_unfinished_cases(self, batch_id: str, reason: str) -> None:
        with suppress(Exception):
            batch = self._evaluation_store.get_batch(batch_id)
            for result in batch.results:
                if result.status in {
                    EvaluationStatus.PENDING,
                    EvaluationStatus.RUNNING,
                }:
                    self._evaluation_store.update_case_result(
                        batch_id,
                        result.case_id,
                        status=EvaluationStatus.ERROR,
                        run_id=result.run_id,
                        failure_reason=reason,
                    )

    def _gate_status(
        self,
        batch: EvaluationBatchRecord,
        metrics: dict[str, Any],
    ) -> str:
        if batch.baseline_batch_id is None:
            return "not_evaluated"
        baseline = self._evaluation_store.get_batch(batch.baseline_batch_id)
        baseline_rate = baseline.metrics.get("pass_rate")
        if not isinstance(baseline_rate, int | float):
            return "not_evaluated"
        current_rate = metrics["pass_rate"]
        metrics["baseline_pass_rate"] = float(baseline_rate)
        metrics["pass_rate_delta"] = round(float(current_rate) - float(baseline_rate), 6)
        return "regression" if float(current_rate) < float(baseline_rate) else "pass"


def dataset_resource(record: EvaluationDatasetRecord) -> EvaluationDatasetResource:
    return EvaluationDatasetResource(
        dataset_id=record.dataset_id,
        digest=record.digest,
        created_at=record.created_at,
        dataset=record.dataset.model_dump(mode="json"),
    )


def batch_resource(record: EvaluationBatchRecord) -> EvaluationBatchResource:
    return EvaluationBatchResource(
        batch_id=record.batch_id,
        dataset_id=record.dataset_id,
        agent_id=record.agent_id,
        spec_version=record.spec_version,
        baseline_batch_id=record.baseline_batch_id,
        status=record.status.value,
        gate_status=record.gate_status,
        metrics=record.metrics,
        error=record.error,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        results=[
            EvaluationCaseResultResource(
                case_id=result.case_id,
                case_name=result.case_name,
                status=result.status.value,
                run_id=result.run_id,
                latency_ms=result.latency_ms,
                output=result.output,
                failure_reason=result.failure_reason,
            )
            for result in record.results
        ],
    )


def _assert_output(case: EvaluationCase, output: str) -> tuple[bool, str | None]:
    if case.assertion_type == "exact":
        if output.strip() == case.expected.strip():
            return True, None
        return False, f"期望输出“{case.expected}”，实际输出“{output}”。"

    if re.search(case.expected, output, flags=re.MULTILINE):
        return True, None
    return False, f"输出未匹配正则表达式“{case.expected}”，实际输出“{output}”。"


def _metrics(batch: EvaluationBatchRecord) -> dict[str, Any]:
    results = batch.results
    passed = sum(result.status == EvaluationStatus.PASSED for result in results)
    failed = sum(result.status == EvaluationStatus.FAILED for result in results)
    errors = sum(result.status == EvaluationStatus.ERROR for result in results)
    latencies = [
        result.latency_ms for result in results if result.latency_ms is not None
    ]
    total = len(results)
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "error_cases": errors,
        "pass_rate": round(passed / total, 6) if total else 0,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
    }


def _duration_ms(run: RunRecord, fallback_started: float) -> int:
    if run.started_at is not None and run.finished_at is not None:
        return max(0, round((run.finished_at - run.started_at).total_seconds() * 1_000))
    return max(0, round((asyncio.get_running_loop().time() - fallback_started) * 1_000))


def _run_failure_reason(run: RunRecord) -> str:
    if run.error is not None:
        message = run.error.get("message")
        if isinstance(message, str) and message:
            return f"运行失败：{message}"
    return f"运行未成功完成，状态为 {run.status.value}。"
