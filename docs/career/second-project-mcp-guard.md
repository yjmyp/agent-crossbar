# 第二个旗舰项目：MCP Guard

日期：2026-11-14
状态：**已否决（2026-11-14 晚，检索后推翻）**

否决理由：这一格已经被占满。GitHub 上真实存在的同类项目（2026-11-14 检索）：

| 项目 | Stars | 说明 |
| --- | --- | --- |
| NVIDIA/SkillSpector | 25.9k | Agent skill 安全扫描，含 MCP |
| Tencent/AI-Infra-Guard | 7.5k | MCP scan + Agent scan 红队平台 |
| snyk/agent-scan | 3.2k | MCP server / agent skill 扫描 |
| IBM/mcp-context-forge | 4.8k | MCP/A2A 网关 + guardrails |
| microsoft/mcp-gateway | 919 | MCP 反向代理与生命周期管理 |
| cisco-ai-defense/mcp-scanner | 1.1k | MCP server 威胁扫描 |

个人项目在这条赛道上是“更弱的第七个扫描器”，面试官一句“和 Snyk 的比呢”就结束了。
下面的内容保留作为否决记录，不再作为选型。

## 先把前两版否掉，理由要能拿去面试讲

| 候选 | 采用摩擦 | 价值可见速度 | 差异化 | 可演示 | 结论 |
| --- | --- | --- | --- | --- | --- |
| TestWitness（改弱测试检测） | 高：需要成熟测试体系和 CI | 慢：要积累基线才看得出价值 | 中 | 弱：演示是“看一份 diff” | 否 |
| Agent Blackbox（会话取证/回滚） | 中高：回滚必须先于改动做快照，等于要包一层 | 中 | 中：Git 已覆盖大部分；审计价值与 Crossbar trace 重叠 | 中 | 否 |
| **MCP Guard** | **低：改一行 MCP 配置** | **快：装上立刻看到工具调用被记录/拦截** | **高：MCP 工具层几乎没有企业级防护** | **强：60 秒能演完拦截** | **是** |

Agent Blackbox 不是没价值，是“价值要等出事才体现”，而且回滚这件事 Git 已经做了
80%。面试官会问“这和 `git checkout` 有什么区别”，不好答。

TestWitness 的问题更直接：目标客户得先有一套像样的测试，才能谈“测试被改弱”。
对大多数团队，这不是今天的痛。

## 一句话

**Agent 能调用什么工具、传了什么参数、返回了什么，MCP Guard 都记账，并按策略拦截。**

## 为什么是现在

2026 年企业落 Agent 的真实路径是 MCP：文件系统、数据库、浏览器、内部 API 都包成
MCP server 接进来。风险也从“模型说错话”变成了“模型被诱导调了一个危险工具”：

- 工具描述里藏指令（tool poisoning / 间接提示注入）。
- `npx -y some-server@latest` 这种不锁版本的安装方式。
- 配置里明文放 token、数据库连接串。
- 一个 server 声明了 `read_file`，实际能读整个用户目录。
- 工具返回里带密钥，原样进了模型上下文，再被写进日志或代码。

这些都在 MCP 的 JSON-RPC 边界上，**不需要改 Agent、不需要换模型**，一个代理就能看见。

## 和 Crossbar 的关系（简历主线）

两个项目守的是同一条链上的两个关口：

```
Agent 生成代码  --[Crossbar]-->  进仓库/交付
Agent 调用工具  --[MCP Guard]--> 碰真实系统
```

一句话主线：**“我做了 Agent 供应链上的两个确定性闸门：交付前审代码，运行时审工具。”**

这比“我又做了一个 Agent 平台”强得多，因为它回答的是“你的东西到底挡了什么”。

## 用户是谁

- 正在给团队接 MCP server 的平台/安全工程师。
- 要把内部系统暴露成 MCP 工具，但不敢直接开的团队。
- 需要给审计/合规交“Agent 到底动了什么”的证据的人。

## 产品边界（写清楚，避免被拿去和 LangSmith 比）

做：
- 本机优先，无云端依赖。
- 静态配置审计 + 工具清单审计 + 运行时 JSON-RPC 代理与审计日志。
- SARIF 输出，能进 GitHub Code Scanning。
- 策略：允许/拒绝/脱敏/限速/审批。
- 可复现的恶意样本基准。

不做：
- 不做 Agent 可观测平台，不做 trace UI 全家桶。
- 不做 OS 级沙箱。**代理只能约束 JSON-RPC 边界，管不了 server 进程自己干什么**，
  这句话必须写进 README，否则就是虚假宣传。
- 不做模型网关。

## 架构

```
                 ┌──────────────┐
  Agent/client → │  mcp-guard   │ → MCP server (stdio)
                 │   proxy      │
                 └──────┬───────┘
                        │ JSON-RPC 帧
              ┌─────────┴──────────┐
              │ policy engine      │  allow / deny / redact / require-approval
              │ redactor           │  secrets, tokens, paths
              │ audit store        │  SQLite: 每次调用一条不可篡改记录
              └─────────┬──────────┘
                        │
                 SARIF / HTML / JSON
```

三个子命令：

```bash
mcpguard scan                 # 扫配置 + 工具描述，不启动任何 server
mcpguard inspect -- <cmd>     # 启动 server，只调 tools/list，记录 schema 与能力
mcpguard proxy -- <cmd>       # 运行时拦截与记账
```

## 3 分钟演示脚本

1. `mcpguard scan` 扫一份真实配置：报出 `npx -y @x/server@latest`、明文 token、
   工作区外的文件根目录。（30 秒）
2. `mcpguard inspect` 连一个故意投毒的自建 server：报出工具描述里的隐藏指令和
   不可见 Unicode。（40 秒）
3. `mcpguard proxy` 跑同一个 server：Agent 请求 `read_file("/etc/passwd")` 被策略拒绝，
   请求 `write_file` 触发审批，正常读取被记录。（60 秒）
4. 打开审计日志与 SARIF，展示一条完整证据链。（30 秒）

## MVP（4 周，按周验收）

| 周 | 交付 | 验收 |
| --- | --- | --- |
| 1 | 配置发现 + 静态规则 + SARIF | 对 3 种客户端配置格式都能扫；`--fail-on high` 退出码正确 |
| 2 | `inspect`：spawn server、`tools/list`、描述分析 | 自建 5 个良性 + 5 个恶意 server，恶意全中，良性零误报 |
| 3 | `proxy`：JSON-RPC 透传、策略、脱敏、SQLite 审计 | 透传不破坏正常会话；拒绝/脱敏各有测试；崩溃可恢复 |
| 4 | 基准 + CI + 文档 + 3 分钟视频 | 公开召回率/误报率；GitHub Action 示例；`pipx install` 可用 |

## 必须公开的数字

- 静态规则在自建样本集上的精确率 / 召回率（样本与规则分离，规则不能对着样本写）。
- 代理引入的额外延迟（P50 / P95，逐条消息）。
- 大配置（例如 20 个 server、400 个工具）的扫描耗时。
- 误报清单：哪些是已知不修的，为什么不修。

没有这四组数字，就还是“看起来很酷”，不是“能验收”。

## 风险与红线

- **风险一**：MCP 生态变化快，规范可能改。缓解：只依赖 `initialize` / `tools/list` /
  `tools/call` 这三个最稳定的方法，其余透传。
- **风险二**：被说“你这不就是个中间人”。缓解：把策略、审计、SARIF、基准做扎实，
  中间人是形态，证据链才是价值。
- **红线**：不声称能阻止恶意 server 的一切行为；不声称“企业级”；不编造用户数和
  检出率。
