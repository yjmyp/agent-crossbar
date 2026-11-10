# Compare、Evaluation 与中文界面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Agent Crossbar 桌面应用中交付可真实使用的运行对比、持久化评测与回归门禁，并把所有产品界面文案改为中文。

**Architecture:** Compare 复用已持久化运行、AgentSpec 与规范化事件，在后端计算稳定摘要，前端只负责选择与呈现。Evaluation 使用 SQLite 新建版本化数据集、用例、评测批次和逐例结果；执行复用现有 `RunExecutor` 与不可变运行证据，批次结束后计算通过率、延迟和相对于基线的回归判定。

**Tech Stack:** React 19、TypeScript、Vitest、FastAPI、Pydantic、SQLite、pytest、Tauri。

**Spec:** `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`

**Status:** implementation and acceptance complete on 2026-11-03. The work was
intentionally left uncommitted in the shared workspace. Latest evidence is in
`docs/verification/agent-platform.md`; the milestone-specific record remains in
`docs/verification/compare-evaluation.md`.

## Global Constraints

- Windows 原生 Tauri 桌面应用是唯一主要交付形态。
- 所有产品界面展示文案使用中文；AgentSpec、MCP、API、ID、状态机原始值等技术标识可保留英文。
- 不修改 OfferAgent。
- 后端不把失败或不完整运行标记为成功。
- 新 API 必须经过 per-launch Bearer Token 鉴权。
- 所有持久化结构必须通过版本化 migration 创建。
- 页面必须包含加载、空态、错误、部分数据和破坏性操作确认状态。
- 只有完整门禁与真实桌面冒烟通过后才能声明完成。

---

### Task 1: 运行对比领域服务

**Files:**
- Create: `backend/agent_crossbar/api/compare.py`
- Modify: `backend/agent_crossbar/api/app.py`
- Test: `backend/tests/api/test_compare.py`

**Interfaces:**
- Consumes: `RunStore.get(run_id)`, `RunStore.list_events(run_id)`, `SpecStore.get(agent_id, version)`
- Produces: `GET /v1/compare?left_run_id=<id>&right_run_id=<id>`，返回两个运行摘要、相同点和差异点。

- [x] 写 API 测试，验证运行不存在、禁止自比较、事件统计与工具差异。
- [x] 运行测试并确认失败。
- [x] 实现纯函数 `build_run_comparison` 与路由。
- [x] 运行测试并确认通过。
- [x] 完成领域服务，并按工作区约束保持未提交。

### Task 2: 评测数据模型与 migration

**Files:**
- Create: `backend/agent_crossbar/domain/evaluation.py`
- Create: `backend/agent_crossbar/storage/evaluations.py`
- Modify: `backend/agent_crossbar/storage/migrations.py`
- Test: `backend/tests/storage/test_evaluations.py`

**Interfaces:**
- 数据集：名称、不可变版本、用例列表；用例包含输入、精确匹配或正则断言、标签。
- 批次：绑定 AgentSpec、数据集、基线批次与逐例运行。
- 结果状态：`pending`、`running`、`passed`、`failed`、`error`。
- `EvaluationStore.create_dataset`、`get_dataset`、`list_datasets`、`create_batch`、`get_batch`、`list_batches`、`update_case_result`、`finish_batch`。

- [x] 写 migration/reopen 与状态转换测试。
- [x] 运行测试并确认失败。
- [x] 实现 Pydantic 模型、JSON 校验与 SQLite store。
- [x] 运行测试并确认通过。
- [x] 完成持久化层，并按工作区约束保持未提交。

### Task 3: 批量评测执行与回归门禁

**Files:**
- Create: `backend/agent_crossbar/api/evaluation_service.py`
- Modify: `backend/agent_crossbar/api/app.py`
- Modify: `backend/agent_crossbar/storage/evaluations.py`
- Test: `backend/tests/api/test_evaluations.py`

**Interfaces:**
- 创建数据集、读取、删除由批次历史引用的数据集时拒绝删除。
- 创建批次后逐例启动真实运行，等待终止后按断言评分。
- 批次指标：通过率、错误率、平均延迟、相对基线通过率差与 `pass`/`regression` 门禁。

- [x] 写集成测试覆盖数据集 CRUD、批量执行、正则断言、失败原因和回归判定。
- [x] 运行测试并确认失败。
- [x] 实现 API 与执行状态机。
- [x] 运行测试并确认通过。
- [x] 完成评测执行闭环，并按工作区约束保持未提交。

### Task 4: 前端 Compare 工作区

**Files:**
- Create: `src/pages/ComparePage.tsx`
- Create: `src/pages/ComparePage.test.tsx`
- Modify: `src/lib/bridge.ts`
- Modify: `src/test/fakeBridge.ts`

- [x] 写组件测试覆盖双运行选择、摘要、差异和同运行拦截。
- [x] 实现页面与响应式并列布局。
- [x] 运行预期失败再实现，最后确认通过。
- [x] 完成 Compare 页面，并按工作区约束保持未提交。

### Task 5: 前端 Evaluation Lab

**Files:**
- Create: `src/pages/EvaluationPage.tsx`
- Create: `src/pages/EvaluationPage.test.tsx`
- Modify: `src/lib/bridge.ts`
- Modify: `src/test/fakeBridge.ts`

- [x] 写组件测试覆盖数据集创建、批次启动、结果表与回归门禁。
- [x] 实现页面、表单校验、状态轮询和失败用例展开。
- [x] 运行预期失败再实现，最后确认通过。
- [x] 完成 Evaluation Lab，并按工作区约束保持未提交。

### Task 6: 全界面中文化

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/**/*.tsx`
- Modify: `src/pages/*.tsx`
- Modify: `src/lib/bridge.ts`
- Modify: `src/lib/errors.ts`
- Modify: `src/**/*.test.tsx`

- [x] 把导航、标题、说明、按钮、空态、错误、状态与时间文案改为中文。
- [x] 保留技术标识和协议名，将可读状态另设中文展示。
- [x] 更新测试选择器，使用角色、标签和中文可见文案定位。
- [x] 运行前端测试、类型检查、lint 与生产构建。
- [x] 完成中文化，并按工作区约束保持未提交。

### Task 7: 完整验收与文档

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-02-agent-crossbar-design.md`
- Create: `docs/verification/compare-evaluation.md`

- [x] 运行 `npm.cmd run verify`。
- [x] 构建 sidecar 并运行 sidecar、Provider、桌面 Provider 三类冒烟。
- [x] 启动真实桌面应用，验证 Compare 与 Evaluation 的可交互状态。
- [x] 更新能力边界；后续平台里程碑已实现 MCP、词法知识检索、多 Agent、
  更多运行时适配器与本地签名/更新验证，生产凭据与 HTTPS 更新服务仍需外部提供。
- [x] 完成验收证据，并按工作区约束保持未提交。
