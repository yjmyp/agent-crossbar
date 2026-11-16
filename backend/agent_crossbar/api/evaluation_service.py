from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from agent_crossbar.api.run_service import RunExecutor
from agent_crossbar.domain.diagnostics import build_diagnostics
from agent_crossbar.domain.evaluation import EvaluationCase, EvaluationStatus
from agent_crossbar.domain.events import RuntimeEvent, RuntimeEventType
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
            metrics = _metrics(completed, run_store=self._run_store)
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
                    metrics=_metrics(
                        self._evaluation_store.get_batch(batch.batch_id),
                        run_store=self._run_store,
                    ),
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
                    metrics=_metrics(
                        self._evaluation_store.get_batch(batch.batch_id),
                        run_store=self._run_store,
                    ),
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

        events = self._run_store.list_events(terminal.run_id)
        passed, failure_reason = _assert_case(case, terminal.output, events)
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
        regressions: list[dict[str, Any]] = []
        if float(current_rate) < float(baseline_rate):
            regressions.append(
                {
                    "metric": "pass_rate",
                    "baseline": float(baseline_rate),
                    "current": float(current_rate),
                    "limit": "must not decrease",
                }
            )

        budgets = (
            ("total_tokens", 1.2, 100.0, "max +20% or +100 tokens"),
            ("total_model_turns", 1.15, 1.0, "max +15% or +1 turn"),
            ("average_latency_ms", 1.25, 250.0, "max +25% or +250 ms"),
        )
        for metric, ratio, absolute_allowance, label in budgets:
            baseline_value = baseline.metrics.get(metric)
            current_value = metrics.get(metric)
            if not isinstance(baseline_value, int | float) or not isinstance(
                current_value, int | float
            ):
                continue
            allowed = max(float(baseline_value) * ratio, float(baseline_value) + absolute_allowance)
            metrics[f"baseline_{metric}"] = baseline_value
            metrics[f"{metric}_delta"] = round(
                float(current_value) - float(baseline_value),
                6,
            )
            metrics[f"{metric}_budget"] = round(allowed, 6)
            if float(current_value) > allowed:
                regressions.append(
                    {
                        "metric": metric,
                        "baseline": baseline_value,
                        "current": current_value,
                        "allowed": round(allowed, 6),
                        "limit": label,
                    }
                )

        metrics["gate_regressions"] = regressions
        metrics["gate_policy"] = {
            "pass_rate": "must not decrease",
            "total_tokens": "max +20% or +100 tokens",
            "total_model_turns": "max +15% or +1 turn",
            "average_latency_ms": "max +25% or +250 ms",
        }
        return "regression" if regressions else "pass"


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


def _assert_case(
    case: EvaluationCase,
    output: str,
    events: list[RuntimeEvent],
) -> tuple[bool, str | None]:
    if case.assertion_type == "exact":
        if output.strip() == case.expected.strip():
            return True, None
        return False, f"期望输出“{case.expected}”，实际输出“{output}”。"

    if case.assertion_type == "regex":
        if re.search(case.expected, output, flags=re.MULTILINE):
            return True, None
        return False, f"输出未匹配正则表达式“{case.expected}”，实际输出“{output}”。"

    if case.assertion_type == "contains":
        if case.expected in output:
            return True, None
        return False, f"输出不包含“{case.expected}”，实际输出“{output}”。"

    if case.assertion_type == "not_contains":
        if case.expected not in output:
            return True, None
        return False, f"输出不应包含“{case.expected}”，实际输出“{output}”。"

    tool_names = _tool_names(events)
    if case.assertion_type == "tool_called":
        if case.expected.strip() in tool_names:
            return True, None
        return False, f"期望调用工具“{case.expected}”，实际调用 {tool_names}。"

    if case.assertion_type == "tool_not_called":
        if case.expected.strip() not in tool_names:
            return True, None
        return False, f"不应调用工具“{case.expected}”，实际调用 {tool_names}。"

    if case.assertion_type == "tool_sequence":
        expected = _parse_tool_sequence(case.expected)
        if tuple(tool_names) == expected:
            return True, None
        return False, f"期望工具序列 {list(expected)}，实际序列 {tool_names}。"

    if case.assertion_type == "max_tool_calls":
        limit = int(case.expected)
        if len(tool_names) <= limit:
            return True, None
        return False, f"工具调用 {len(tool_names)} 次，超过上限 {limit}。"

    if case.assertion_type == "max_steps":
        limit = int(case.expected)
        steps = _step_count(events)
        if steps <= limit:
            return True, None
        return False, f"执行 {steps} 步，超过上限 {limit}。"

    diagnostics = None
    trajectory_limits = {
        "max_loops": ("loops", "循环"),
        "max_oscillations": ("oscillations", "震荡"),
        "max_duplicate_calls": ("duplicate_calls", "重复工具调用"),
    }
    if case.assertion_type in trajectory_limits:
        diagnostics = build_diagnostics("evaluation", events)
        attribute, label = trajectory_limits[case.assertion_type]
        actual = int(getattr(diagnostics, attribute))
        limit = int(case.expected)
        if actual <= limit:
            return True, None
        return False, f"{label} {actual} 次，超过上限 {limit}。"

    if case.assertion_type == "no_denials":
        diagnostics = diagnostics or build_diagnostics("evaluation", events)
        if diagnostics.denials == 0:
            return True, None
        return False, f"运行中出现 {diagnostics.denials} 次审批拒绝。"

    if case.assertion_type == "max_tokens":
        total_tokens = sum(
            event.usage.total_tokens
            for event in events
            if event.usage is not None
        )
        limit = int(case.expected)
        if total_tokens <= limit:
            return True, None
        return False, f"Token 用量 {total_tokens}，超过上限 {limit}。"

    if case.assertion_type == "max_duration_ms":
        duration_ms = (
            max(0, round((events[-1].timestamp - events[0].timestamp).total_seconds() * 1_000))
            if events
            else 0
        )
        limit = int(case.expected)
        if duration_ms <= limit:
            return True, None
        return False, f"轨迹耗时 {duration_ms} ms，超过上限 {limit} ms。"

    if case.assertion_type == "no_error":
        failures = [
            event
            for event in events
            if event.type in {RuntimeEventType.TOOL_FAILED, RuntimeEventType.RUN_FAILED}
        ]
        if not failures and output.strip():
            return True, None
        if failures:
            return False, f"运行中出现 {len(failures)} 个失败事件。"
        return False, "运行没有产生有效输出。"

    if case.assertion_type == "json_path":
        try:
            document = json.loads(output)
        except ValueError:
            return False, f"输出不是合法 JSON：“{output}”。"
        payload = json.loads(case.expected)
        path = str(payload["path"])
        found, value = _read_json_path(document, path)
        if "exists" in payload:
            if found is payload["exists"]:
                return True, None
            return False, f"JSON 路径“{path}”存在性为 {found}，期望 {payload['exists']}。"
        if not found:
            return False, f"JSON 路径“{path}”不存在。"
        if "equals" in payload:
            if value == payload["equals"]:
                return True, None
            return False, f"JSON 路径“{path}”为 {value!r}，期望 {payload['equals']!r}。"
        if isinstance(value, str) and payload["contains"] in value:
            return True, None
        return False, f"JSON 路径“{path}”的值不包含“{payload['contains']}”。"

    return False, f"不支持的断言类型“{case.assertion_type}”。"


def _parse_tool_sequence(value: str) -> tuple[str, ...]:
    normalized = value.replace("->", ",").replace("→", ",")
    return tuple(
        item.strip()
        for item in re.split(r"[,\s]+", normalized)
        if item.strip()
    )


def _tool_names(events: list[RuntimeEvent]) -> list[str]:
    names: list[str] = []
    for event in events:
        if event.type is not RuntimeEventType.TOOL_STARTED:
            continue
        name = event.payload.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _step_count(events: list[RuntimeEvent]) -> int:
    steps = {event.step_id for event in events if event.step_id is not None}
    return len(steps)


def _read_json_path(document: Any, path: str) -> tuple[bool, Any]:
    current = document
    normalized = path.strip()
    if normalized.startswith("$"):
        normalized = normalized[1:]
    for raw_part in normalized.split("."):
        part = raw_part.strip()
        if not part:
            continue
        index: int | None = None
        key = part
        if part.endswith("]"):
            opening = part.rfind("[")
            if opening > 0:
                key = part[:opening]
                try:
                    index = int(part[opening + 1 : -1])
                except ValueError:
                    return False, None
        if key:
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current[key]
        if index is not None:
            if not isinstance(current, list) or index >= len(current) or index < -len(current):
                return False, None
            current = current[index]
    return True, current


def _metrics(
    batch: EvaluationBatchRecord,
    *,
    run_store: RunStore | None = None,
) -> dict[str, Any]:
    results = batch.results
    passed = sum(result.status == EvaluationStatus.PASSED for result in results)
    failed = sum(result.status == EvaluationStatus.FAILED for result in results)
    errors = sum(result.status == EvaluationStatus.ERROR for result in results)
    latencies = [
        result.latency_ms for result in results if result.latency_ms is not None
    ]
    total = len(results)
    tool_calls = 0
    model_turns = 0
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    steps = 0
    if run_store is not None:
        for result in results:
            if result.run_id is None:
                continue
            try:
                events = run_store.list_events(result.run_id)
            except Exception:
                continue
            tool_calls += sum(
                event.type is RuntimeEventType.TOOL_STARTED for event in events
            )
            model_turns += sum(
                event.type is RuntimeEventType.MODEL_COMPLETED for event in events
            )
            steps += _step_count(events)
            for event in events:
                if event.usage is not None:
                    input_tokens += event.usage.input_tokens
                    output_tokens += event.usage.output_tokens
                if event.cost_usd is not None:
                    cost_usd += float(event.cost_usd)
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "error_cases": errors,
        "pass_rate": round(passed / total, 6) if total else 0,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "total_tool_calls": tool_calls,
        "average_tool_calls": round(tool_calls / total, 4) if total else 0,
        "total_model_turns": model_turns,
        "average_model_turns": round(model_turns / total, 4) if total else 0,
        "total_steps": steps,
        "average_steps": round(steps / total, 4) if total else 0,
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_cost_usd": round(cost_usd, 6),
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
