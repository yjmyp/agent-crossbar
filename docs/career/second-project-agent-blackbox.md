# 第二个旗舰项目：Agent Blackbox

日期：2026-11-14
状态：**已否决**。回滚价值与 `git checkout` 高度重叠，取证价值与 Crossbar 的
trace 重叠，且“先包一层才能快照”拉高了采用门槛。最终选型见
[`second-project-mcp-guard.md`](second-project-mcp-guard.md)。

## 先否决 TestWitness

TestWitness 的问题不是技术，而是采用门槛：

- 团队必须先有像样的测试体系，否则工具没有输入。
- 需要改 CI、维护基线、处理误报。
- 对很多公司来说，“测试被改弱”还不是当前最痛的问题。

它更像一个高级 QA 工具，不像一个装完就能用的企业产品。

## 一句话

**不用改 Agent，也能知道它到底做了什么。**

Agent Blackbox 是一个本地优先的 Agent 运行取证与回滚工具。它读取 Codex、
Claude Code 等编码 Agent 已经写在磁盘上的会话记录，结合 Git diff，重建一次
运行的完整时间线：模型轮次、工具调用、命令、文件改动、Token/成本、敏感信息、
最终产物，并支持一键回滚。

它不要求 Agent 接 SDK，不要求换模型，不要求改 CI。装完，选仓库，导入会话。

## 为什么这个更容易用上

企业已经在用 Codex、Claude Code、Cursor，但通常回答不了：

- 这次改动到底是哪个 Agent、哪次会话、哪个模型做的？
- 它执行了哪些命令？读了哪些文件？有没有把密钥发出去？
- 花了多少 Token/成本？失败重试了几次？
- 出问题能不能回到运行前？
- 同一份证据能不能给安全、审计、主管看？

Git 只记录最终 diff，不记录工具调用和模型轮次。LangSmith/Langfuse 这类工具
需要 SDK 埋点，管不到员工本地跑的编码 Agent。Agent Blackbox 填的就是这个空位：

> 外部 Agent 的本地飞行记录仪。

## 目标用户

- 已经给研发配了 Codex / Claude Code / Cursor 的 20–500 人团队。
- 需要回答“Agent 到底改了什么、有没有泄露、花了多少钱”的技术负责人。
- 需要事故复盘、合规审计、成本归因的平台/安全团队。

买家不需要先建设 Agent 平台，也不需要改现有研发流程。

## 使用方式

```text
1. 安装 Agent Blackbox（Windows 桌面应用或 CLI）
2. 选择仓库目录
3. 自动发现 ~/.codex/sessions、~/.claude/projects 等本地会话
4. 看到按时间排序的运行列表
5. 点开一次运行：时间线、工具调用、文件 diff、Token/成本、风险
6. 需要时导出 Markdown，或一键回滚
```

CLI 版本：

```bash
blackbox import --repo . --source codex
blackbox list --repo .
blackbox show run_123 --format markdown
blackbox rollback run_123 --dry-run
```

## MVP 范围

### 必须做

- Codex 会话适配器（JSONL/本地存储）。
- Claude Code 会话适配器（JSONL）。
- Git diff 关联：哪次运行改了哪些文件、哪些行。
- 统一事件模型：`run_started / model_turn / tool_call / file_change / command / run_finished`。
- 时间线 UI：按时间、按文件、按工具三种视图。
- Token/成本汇总；模型名、轮次、工具次数。
- 本地确定性敏感信息扫描（复用 Crossbar 规则）。
- Markdown/JSON 导出；证据带 hash。
- 回滚：生成反向 patch，先 dry-run，再应用。

### 明确不做

- 不做托管可观测平台，不替代 LangSmith/Langfuse。
- 不做模型路由、提示词管理、评测平台。
- 不承诺还原 Agent 的隐藏推理；只记录可观察事件。
- 不默认上传任何源码或日志。

## 技术架构

```text
Desktop UI (React/Tauri) 或 CLI
  └─ importer
       ├─ Codex adapter
       ├─ Claude Code adapter
       └─ generic JSONL adapter
            └─ normalizer -> SQLite event store
                 ├─ git correlator (diff, blame, worktree)
                 ├─ secret/risk scanner (deterministic)
                 ├─ cost calculator (provider usage, local table)
                 └─ evidence exporter (Markdown/JSON/SARIF)
                      └─ rollback planner (reverse patch, dry-run)
```

关键设计：

- **零埋点**：读已有会话，不要求 Agent 改代码。
- **本地优先**：默认不联网；上传必须是显式操作。
- **证据可复核**：每条结论绑定会话文件 hash、仓库 commit、工具版本。
- **事件归一化**：不同 Agent 的日志映射到同一套事件 schema。
- **回滚安全**：默认 dry-run；有未提交改动时拒绝直接回滚。

## 首个演示

1. 用 Codex 在一个演示仓库里改一个文件、跑一次测试。
2. 打开 Agent Blackbox，自动发现这次会话。
3. 时间线显示：模型轮次 → 读文件 → 改文件 → 执行命令 → 结束。
4. 文件视图显示 diff；成本视图显示 Token。
5. 安全视图标出一个硬编码密钥。
6. 点击“回滚”，生成反向 patch，dry-run 展示将撤销的改动。

这个演示不需要用户先有测试体系，也不需要改 CI，价值一眼可见。

## 与 Crossbar 的关系

| 项目 | 管什么 | 使用方式 |
| --- | --- | --- |
| Agent Crossbar | 你自己构建/运行的 Agent：spec、trace、评测、安全闸门 | 工作台 |
| Agent Blackbox | 别人已经用的 Agent：Codex、Claude Code、Cursor 的本地取证 | 记录仪 |

Crossbar 是“运行和交付”，Blackbox 是“审计和回滚”。两者共享事件模型、
SQLite、React/Tauri、安全规则，但不是同一个产品的两个页面。

## 里程碑

### M1：Codex 取证（1–2 周）

- Codex 会话导入
- 统一事件模型 + SQLite
- 时间线 UI（先只读）
- Git diff 关联
- Markdown/JSON 导出

### M2：风险与成本（1 周）

- 敏感信息扫描
- Token/成本汇总
- 证据 hash
- 失败/重试标记

### M3：回滚与 Claude Code（1–2 周）

- 反向 patch + dry-run
- Claude Code 适配器
- 未提交改动保护
- 回滚审计日志

### M4：真实试用（1 周）

- 3 个外部用户独立导入自己的会话
- 记录卡点、导入失败格式、最常用视图
- 公开支持矩阵和已知不兼容

## 竞争边界

- LangSmith/Langfuse：需要 SDK 埋点，偏托管评测/观测；Blackbox 零埋点、本地、跨 Agent。
- GitHub Copilot 审计日志：只管 Copilot，且偏企业管理员；Blackbox 管本地多个 Agent。
- Git：只有最终 diff，没有工具调用、模型轮次、成本和风险。
- 终端历史：只有命令，没有文件关联和回滚证据。

## 风险

- **日志格式变化**：适配器必须版本化，导入失败要明确报错，不能猜。
- **隐私**：默认本地；导出前提示包含哪些内容。
- **回滚危险**：默认 dry-run；有未提交改动时拒绝。
- **范围膨胀**：先支持 Codex，再 Claude Code；不要一开始做所有 Agent。

## 结论

Agent Blackbox 比 TestWitness 更容易被企业用上：

- 不需要测试体系，不需要 CI 改造。
- 装完就能看到价值：时间线、成本、风险、回滚。
- 技术深度足够：多源日志归一化、Git 关联、证据链、回滚安全。
- 和 Crossbar 形成“运行 + 取证”的组合，而不是两个相似的门禁。

