# 第二个旗舰项目：TestWitness

日期：2026-11-14

## 一句话

**Agent 让 CI 变绿，TestWitness 证明它不是靠改测试。**

TestWitness 是一个本地优先、可解释、可进 CI 的“测试完整性闸门”：它检查
Agent 生成的改动有没有删除测试、放宽断言、跳过用例、扩大 mock、批量更新快照，
或者让新增代码没有被测试覆盖。

它不训练模型，不调用外部 LLM，不替代测试框架。它只回答一个问题：

> 这次改动看起来通过了，但测试本身有没有被削弱？

## 为什么不选 MCP Gateway

我先查了公开仓库，MCP 网关/代理已经是拥挤赛道：

- IBM `mcp-context-forge`：约 4.8k stars，注册、代理、guardrails。
- Microsoft `mcp-gateway`：约 919 stars，Kubernetes 反向代理。
- `solongate/agent-security`：约 685 stars，本地 Agent 工具调用策略与审计。
- `speakeasy-api/gram`、`TheLunarCompany/lunar`：企业 MCP 治理。

如果现在做一个“通用 MCP 网关”，会直接和这些项目比注册中心、协议兼容、
Kubernetes、企业 IdP。作为个人项目，赢面很低。

TestWitness 的竞争密度明显更低，而且痛点更具体：

- 覆盖率高，不等于测试有效。
- Agent 很容易通过删断言、加 `skip`、放宽 mock 来让 CI 变绿。
- 代码评审通常看得懂业务代码，却很少有人逐行审查测试改动。
- 现有工具分别做覆盖率、变异测试、AI 代码评审，但很少把“测试是否被削弱”
  做成一个可阻断、可豁免、可追溯的交付结论。

## 目标用户

- 正在把 Codex / Claude Code / Cursor 接进研发流程的 20–500 人团队。
- 有 CI、有测试、有代码评审，但没有“测试完整性”门禁的团队。
- 金融、企业软件、基础设施等不能接受“测试被改绿”的组织。

买家不是“AI 爱好者”，而是技术负责人、QA 负责人、平台工程团队。

## 工作流

```bash
# 本地：对比当前分支与 main
testwitness scan --base origin/main

# CI：输出 SARIF，并在 PR 上阻断
testwitness scan --base origin/main --format sarif -o testwitness.sarif

# 深度模式：只对改动行做变异测试
testwitness scan --base origin/main --mutation changed-lines
```

输出只有三种结论：

- `intact`：测试没有被削弱，可以继续评审。
- `weakened`：发现测试弱化，需要说明或补测试。
- `blocked`：删除/跳过关键测试，或新增代码零覆盖，直接阻断。

每条问题必须带：文件、行号、改动前后对比、规则、策略条款、修复建议。

## 检测能力（MVP）

### 1. 测试删除与跳过

- 删除测试函数、测试文件、断言。
- 新增 `skip`、`xfail`、`only`、`.todo`、`describe.skip`。
- 把测试改成空函数，或只保留 `expect(true).toBe(true)`。

### 2. 断言强度下降

Python：

- `assert x == expected` → `assert x is not None`
- `pytest.raises(...)` 被删除
- `assert_called_once_with(...)` → `assert_called_once()`

TypeScript：

- `toBe(value)` → `toBeDefined()`
- `toHaveBeenCalledWith(...)` → `toHaveBeenCalled()`
- `toEqual(...)` → `toBeTruthy()`

### 3. Mock 与快照扩大

- `mock.ANY`、`vi.fn()` 无返回值、宽泛的 `**kwargs` mock。
- 一次性更新大量快照，且没有对应源码变更说明。
- 把真实依赖替换成永远成功的 fake。

### 4. 改动行覆盖

- 新增/修改的源码行是否被测试执行。
- 覆盖率是否从“覆盖关键分支”退化为“只执行到函数入口”。

### 5. 变异测试（深度模式）

只对 PR 改动行生成变异体，运行相关测试，计算 mutation score。
如果代码改了、测试也改了，但 mutation score 明显下降，标记为 `weakened`。

## 技术架构

```text
CLI / GitHub Action
  └─ diff loader (git merge-base)
       ├─ test AST analyzer (Python / TypeScript)
       ├─ assertion strength model
       ├─ mock / snapshot analyzer
       ├─ coverage delta runner
       └─ mutation runner (changed lines only)
            └─ policy engine + waiver + SARIF + SQLite audit
```

关键设计：

- **diff-only**：默认只分析改动文件，不扫全仓库。
- **确定性**：规则引擎不调用 LLM；需要解释时只发送脱敏片段。
- **可复现**：每个结论绑定 base commit、head commit、命令和工具版本。
- **可豁免**：owner + 理由 + 到期时间；过期重新阻断。
- **可组合**：可以单独用，也可以和 Crossbar 的安全评审并列进 CI。

## 与 Crossbar 的关系

| 项目 | 管什么 | 交付结论 |
| --- | --- | --- |
| Agent Crossbar | 代码有没有密钥/注入/危险命令，运行有没有超预算 | `block / fix / ship` |
| TestWitness | 测试有没有被 Agent 改弱，新增代码有没有被验证 | `intact / weakened / blocked` |

两者共享同一套产品哲学：本地、确定性、证据、豁免、SARIF、可复现。
简历上可以写成一条主线：

> 为 Agent 生成代码建立两道交付闸门：Crossbar 管安全与行为预算，TestWitness 管测试完整性。

## MVP 里程碑

### M1：Python 可用（1–2 周）

- `testwitness scan --base origin/main`
- Python AST：删除测试、删除断言、新增 skip、断言强度下降
- pytest coverage JSON：改动行覆盖
- Markdown + SARIF 输出
- 20 个手工构造的 agent patch 回归样本

### M2：CI 与证据（1 周）

- GitHub Action
- PR 注释与 Check Run
- SQLite 审计 + owner/到期时间豁免
- `testwitness verify` 复现历史结论

### M3：TypeScript 与变异（2 周）

- Vitest/Jest AST 分析
- Stryker 或自研 changed-lines mutation runner
- 先支持 Python，再支持 TS；不要一上来做多语言

### M4：独立基准（1 周）

- 100 个 agent patch：50 个真实弱化、50 个合法重构
- 标签人工写，扫描器不参与
- 公开 precision / recall / false positive 文件
- 公开不覆盖：语义正确性、业务需求、 flaky test 根因

## 首个演示（必须能打）

1. Agent 修改 `service.py`，同时删除 `test_service.py` 里的断言。
2. `pytest` 仍然全绿。
3. `testwitness scan` 输出 `blocked`，指出删除的断言和未覆盖的改动行。
4. 加回断言后，结论变为 `intact`。
5. 导出 SARIF，在 GitHub Code Scanning 里看到同一条问题。

这个演示比“再做一个聊天 UI”更有说服力，因为它直接证明：
**CI 绿不等于测试可信。**

## 差异化

- 不是覆盖率工具：覆盖率高但断言弱，照样阻断。
- 不是变异测试工具：默认 diff-only，秒级；变异是可选深度模式。
- 不是 AI 代码评审：不靠模型猜，规则和证据可复现。
- 不是测试生成器：先证明测试没被削弱，再谈补测试。
- 不是通用 Agent 平台：一个命令、一个结论、一个 PR 门禁。

## 风险与停止条件

- **误报**：合法重构会移动/合并测试。必须用 100 个真实 patch 标定，
  误报率高于 10% 就缩小规则范围。
- **语言覆盖**：不要同时支持 6 种语言。Python 做不透，就不要做 TS。
- **变异测试太慢**：只对改动行跑，超过 5 分钟就降级为可选。
- **市场教育成本**：先用“Agent 删测试让 CI 变绿”的真实案例做演示，
  不要讲抽象治理。

## 结论

TestWitness 比 MCP Gateway 更适合作为第二个旗舰项目：

- 痛点具体，演示一眼能懂。
- 技术有深度，但不依赖训练模型。
- 企业有明确使用场景，个人可以独立做出可用版本。
- 和 Crossbar 组成“安全 + 测试完整性”的 Agent 交付双闸门，而不是两个孤立项目。

