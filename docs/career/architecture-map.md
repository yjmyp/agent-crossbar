# 架构地图：从一次点击到一条结论

这份文件只有一个目的：**你自己能讲清楚每个目录是干什么的，以及数据怎么流动。**

## 一句话分层

```
React 桌面 UI (src/)
        │  HTTP + Bearer token, 127.0.0.1 随机端口
        ▼
FastAPI 控制面 (backend/agent_crossbar/api/)
        │  只做编排：校验、调服务、返回
        ▼
领域与存储 (domain/ + storage/)
        │  SQLite WAL，一张表对应一类事实
        ▼
运行时 (runtime/)                         安全引擎 (security/engine/)
  ├─ native / langgraph / adapters           ├─ 31 条确定性规则
  ├─ mcp_client（工具调用）                  ├─ 证据 → 策略条款映射
  └─ worker_runtime（私有 Worker）           └─ Markdown / SARIF 输出
```

左侧和右侧在 `security/service.py` 汇合：代码证据 + 同一条 run 的行为预算 + 豁免，
一起得出 `block / fix / ship`。

## 每个目录的职责（背下来）

| 路径 | 职责 | 面试时一句话 |
| --- | --- | --- |
| `src/lib/bridge.ts` | 前端唯一出口：拼 URL、加 token、解错误 | “UI 不直接 fetch，所有请求走一个桥” |
| `src/pages/*` | 每个页面只负责展示与交互 | “页面无业务逻辑，状态来自后端” |
| `backend/agent_crossbar/sidecar.py` | 启动 sidecar：绑 127.0.0.1、随机端口、打印 ready、父进程死了就退出 | “桌面进程和 Python 进程分离，攻击面只有回环” |
| `api/app.py` | FastAPI 装配、鉴权中间件、依赖注入 | “控制面只做编排” |
| `api/run_service.py` | 创建 run、驱动适配器、把事件落库并推送 | “一次 run 的生命周期在这里” |
| `api/evaluation_service.py` | 为每个 case 真跑一次 run，按断言判定 | “评测不是比对字符串，是重跑” |
| `api/compare.py` | 两条 run 的差异 | “同一份 spec 不同版本，差在哪” |
| `domain/*` | 纯数据模型与不变量（spec、event、evaluation、mcp、worker） | “领域层不碰 IO” |
| `storage/database.py` | 连接、WAL、事务 | “单机单操作员，SQLite 足够” |
| `storage/migrations.py` | 全部建表语句 | “看这一张表就懂数据模型” |
| `storage/runs.py` | run 与事件的读写；事件序号单调 | “trace 可重放的前提” |
| `runtime/base.py` / `native.py` | 运行时接口与自带实现 | “换框架不改上层” |
| `runtime/adapters.py` | LangGraph 等适配 | “适配器模式，不是 if-else 堆” |
| `runtime/mcp_client.py` | 连接 MCP server、列工具、调工具 | “工具调用的入口” |
| `runtime/worker_runtime.py` | 注册表、健康检查、轮转、失败转移 | “是工作台，不是集群调度器” |
| `security/engine/rules.py` | 31 条规则 | “确定性、可解释、可回归” |
| `security/engine/diff.py` | 只扫改动行（`--base` / `--staged`） | “能进 CI，不扫全仓库” |
| `security/engine/redaction.py` | 命中值脱敏后再进报告 | “证据不二次泄露” |
| `security/engine/report.py` | terminal / markdown / sarif | “一个结论，三种出口” |
| `security/service.py` | 代码证据 + 行为预算 + 豁免 → 结论 | “三件事合成一个可执行结论” |
| `security/policy.py` | 策略与豁免校验（owner、理由、到期） | “永久忽略等于没有闸门” |

## 一次“跑一次并评审”的完整路径

1. UI 点“运行” → `bridge.ts` → `POST /api/runs`，带 Bearer token。
2. `run_service` 读 `agent_specs` 里不可变的 spec（SHA-256）。
3. 选 `runtime` 适配器，循环执行：模型轮次 → 工具调用 → 事件。
4. 每个事件写 `run_events`（单调序号），同时 SSE 推给 UI。
5. 终态写 `runs`（状态、token、时长、工具统计）。
6. 点“安全评审” → `security/service.py`：
   - 扫代码 → 命中 → 映射策略条款；
   - 若带 `run_id`，读事件算行为预算；
   - 过滤已过期/无 owner 的豁免；
   - 出 `block / fix / ship`。
7. 报告写 `security_reviews`，可导出 Markdown / SARIF；阻断时 CLI 退出码 1。

## 数据库只有 16 张表，按四类记

- **Agent**：`agents`、`agent_specs`
- **运行**：`runs`、`run_events`
- **评测**：`evaluation_datasets`、`evaluation_batches`、`evaluation_case_results`
- **扩展**：`mcp_servers`、`mcp_tools`、`knowledge_*`（4 张）、`workers`
- **安全**：`security_reviews`、`security_waivers`

面试官问“数据怎么存”，答这四类就够，不要背字段。

## 三个最容易讲错的地方

1. **别说“平台”**。它是单操作员的本地工作台；Worker 是注册表 + 健康检查 +
   轮转 + 失败转移，不是调度器。说“平台”会被拿去和 LangSmith 比。
2. **别把 RAG 的数字安到 Crossbar 上**。Crossbar 的 RAG 是 24 文档 / 72 查询，
   hybrid R@5 0.9722、MRR 0.9190。240 条 / R@5 95% 属于另一个仓库。
3. **别说“企业级安全”**。说“确定性闸门 + 可复现基准 + 明确的未覆盖清单”。
   71.4% 召回和 16.7% -> 22.7% -> 62.5% -> 100.0% 的误报下降曲线都要主动说。

## 如果只能记三句

- 控制面只编排，领域层不碰 IO，存储层只管事实。
- 安全结论 = 代码证据 + 行为预算 + 豁免，缺一项都不能算通过。
- 所有数字都能用仓库里的命令重新跑出来，跑不出来的不写进简历。
