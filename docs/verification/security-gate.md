# 交付安全闸门：实现与证据

日期：2026-11-14

## 它解决什么问题

Agent 生成代码之后，团队通常只有两种选择：整段信任，或人工逐行读。
Agent Crossbar 增加第三种：一个本地、可解释、可豁免、可进 CI 的交付闸门。

一次评审输出三样东西：

1. **代码结论**：31 条确定性规则命中的问题、脱敏证据、中文修复建议、条款依据。
2. **行为结论**：关联 run 的模型轮次、工具调用、Token、时长、禁用工具是否超预算。
3. **责任边界**：哪些风险被谁、以什么理由、豁免到什么时候。

结论只有 `block`、`fix`、`ship` 三种。没有“综合评分”这类不可执行的输出。

## 运行方式

CLI（可进 CI）：

```bash
python -m agent_crossbar.security.cli \
  --root backend/agent_crossbar \
  --format sarif \
  --output work/security.sarif
```

`--fail-on blocked` 是默认值：结论为阻断时退出码为 1。只生成报告不阻断时用
`--fail-on never`。`pipx install .` 后命令名为 `crossbar-security`。

端到端演示：

```bash
python scripts/demo.py
```

演示会真实创建 AgentSpec、执行一次 run、把 run 与安全评审关联，再输出
Markdown 与 SARIF。实测输出：

```text
[demo] run status: completed
[demo] verdict: block - 阻断交付：存在未豁免的高风险问题或行为预算超限。
[demo] findings: 1 total, 1 blocking
  - critical CS-PY-003 deploy.py:6 以 shell=True 调用子进程
[demo] behaviour: 运行正常结束=pass, Token 预算=pass, 时长预算=pass,
        工具调用预算=pass, 安全扫描不外发源码=pass
```

## API

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/v1/security/reviews` | 扫描目录，可带 `run_id` 做行为预算核验 |
| GET | `/v1/security/reviews` | 最近评审 |
| GET | `/v1/security/reviews/{id}` | 完整结论、问题、证据、条款、外发记录 |
| GET | `/v1/security/reviews/{id}/markdown` | PR / 工单可直接粘贴的报告 |
| GET | `/v1/security/policy` | 当前策略条款与预算 |
| GET | `/v1/security/waivers` | 豁免列表（含 active 计算） |
| POST | `/v1/security/waivers` | 登记豁免：规则、文件范围、owner、理由、到期时间 |
| DELETE | `/v1/security/waivers/{id}` | 撤销豁免 |

评审与豁免持久化在 SQLite（schema v7）：

- `security_reviews`：结论、策略名、run 关联、完整 JSON 报告。
- `security_waivers`：规则、文件模式、owner、理由、到期时间、撤销时间。

## 判定规则

- 任一 `critical` / `high` 问题未豁免 → `block`。
- 行为预算任一失败 → `block`。
- 只有中低危问题 → `fix`。
- 全部豁免或没有命中 → `ship`，并明确记录豁免数量。
- 豁免过期或已撤销 → 不生效。

## 外发边界

默认扫描器不调用任何外部模型。报告里写的是：

> 本次扫描全程本地执行；源码、片段与证据未离开本机。

只有显式开启外部模型复核时，才会把**脱敏片段**发给模型，并在 `egress` 中记录
文件名、数量与 provider。当前 UI 和默认 CLI 不开启这条路径。

## 独立基准

见 [`security-benchmark.md`](security-benchmark.md)。固定公开仓库与 commit，
标签人工阅读源码写入，扫描器不参与出题。

- 限定应用代码：精确率 83.3%，召回率 71.4%。
- 整仓库不过滤：精确率 16.7%，召回率 71.4%。
- 明确不覆盖：XSS、XXE、XPath 注入、NoSQL 注入、认证、访问控制。

这组数字说明它适合做“交付前的确定性拦截”，不适合宣称“完整安全审计”。

## 测试与 CI

- Python：211 passed。
- 前端：71 passed（含安全评审页的结论、筛选、扫描参数、豁免重扫）。
- 新机器演示：`python scripts/demo.py` 通过。
- SARIF：对 `backend/agent_crossbar` 生成成功，退出码 0。
- CI：`.github/workflows/verify.yml`（Python + Node + Rust），
  `.github/workflows/security.yml`（SARIF 上传到 Code Scanning）。
- 打包：wheel 已构建，`policy.yaml` 已包含，`tests/` 未进入 wheel；
  console script 为 `crossbar-security`。

本机 Rust 复跑未通过，原因是环境里的 MSVC `cl.exe` 报
`D8050 无法执行 c1.dll`，不是本次代码改动；本次没有声称 Rust 本地通过。
此前记录为 25 + 3 个 Rust 测试通过。

## 还没做到的

- **3 名外部用户独立跑通**：没有完成。README 明确写“未完成”，不编造姓名或反馈。
- **真实企业策略接入**：`policy.yaml` 是示例公司规范，不是任何真实公司的制度。
- **完整 SAST**：规则覆盖有限，跨文件数据流、框架特定 sink、依赖漏洞不在范围内。
- **性能**：本地单操作员工具，没有高并发或大仓库压测数据。

## 面试时怎么说

不要说“我做了个通用安全平台”。应该说：

> 我把 Agent 生成代码的交付问题收敛成一个本地闸门：确定性扫描负责代码，
> 行为预算负责运行，豁免负责组织流程，最后只输出 block/fix/ship。
> 我用两个公开漏洞项目做了独立基准，限定口径精确率 83.3%、召回率 71.4%，
> 整仓库精确率只有 16.7%，这个数字我也公开，因为它说明规则还需要降噪。

接着能讲清楚：为什么扫描器自己必须先证明不外发；为什么豁免必须有 owner 和
到期时间；为什么结论要能关联到同一条 run 的 trace。
