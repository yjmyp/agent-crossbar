# 简历 A：Agent 工程 / 运行时与评测

> 用法：只保留真实做过的内容。数字来自仓库内命令，面试时能现场复现。
> 不要把这版和 `ai-learning/rag2` 的 240 条 / R@5 95% 混写。

## 余剑

求职方向：AI 应用开发 / Agent 工程  
南京邮电大学 · 网络工程（本科）· 2027 届（2023.09–2027.06）  
电话：17578999648 · 邮箱：yj2994762833@gmail.com · 南京  
GitHub：https://github.com/yjmyp

## 个人概述

独立完成本地优先的 Agent 工程工作台 Agent Crossbar：从不可变 AgentSpec、运行时适配、
事件轨迹、批量评测，到交付前的安全闸门与豁免流程。关注“每个结论都能被一条命令复现”，
不把原型包装成平台。熟悉 Python/FastAPI、React/TypeScript、Tauri、SQLite、MCP、
LangGraph、RAG 与 CI。

## 专业技能

- 语言与后端：Python、FastAPI、Pydantic、SQLite/WAL、REST、SSE、Git
- Agent 运行时：工具循环、超时/取消、事件规范化、MCP、多 Agent 委派、LangGraph StateGraph
- 评测与检索：11 类断言（含轨迹）、批量回归、FTS5 BM25、Embedding、RRF、引用与降级
- 交付工程：React/TypeScript、Tauri、Windows Credential Manager、GitHub Actions、SARIF
- 安全：确定性规则扫描、AST/轻量污点分析、脱敏证据、策略条款、owner + 到期时间豁免

## 项目经历

### Agent Crossbar｜本地 Agent 工程工作台与交付闸门

独立开发｜2026.10 – 至今｜https://github.com/yjmyp

- **架构**：Tauri 壳 + 仅回环的 FastAPI sidecar（随机 bearer token）+ SQLite WAL +
  React。一次 run 的路径是 `AgentSpec(SHA-256) → run_service → runtime adapter →
  规范化事件 + 序号 → 落库 → SSE → 终态 → 评测/安全评审可引用`。
- **运行时**：实现有界工具循环、工具异常回填、超时/取消、失败转移；提供 native、
  真实 LangGraph StateGraph、结构化输出与复核适配器。真实模型 E2E：DeepSeek 两轮模型、
  1 次 `knowledge_search`、1114 tokens、3062ms，API Key 不落库。
- **轨迹与评测**：事件带单调序号并持久化；评测支持 exact、regex、contains、
  not_contains、json_path、tool_called、tool_not_called、tool_sequence、
  max_tool_calls、max_steps、no_error 共 11 类断言，能对轨迹而不是只对最终字符串回归。
- **安全闸门**：31 条确定性规则覆盖密钥、命令执行、动态执行、SQL/路径注入、TLS/弱哈希/
  危险配置；中文修复建议 + 条款引用 + 脱敏证据 + `block/fix/ship` 结论；扫描全程本地，
  报告明确记录是否发生外发。
- **豁免与行为预算**：豁免必须有 owner、理由、到期时间，过期/撤销不生效；评审可关联
  同一条 run，核验 Token、时长、工具调用与禁用工具预算，代码结论和行为结论同页呈现。
- **证据与工程**：独立基准固定 DSVW 与 OWASP NodeGoat 的 commit，限定应用代码精确率
  83.3%、召回率 71.4%（整仓库精确率 16.7% 也公开）；Python 211 + 前端 71 项自动化测试；
  GitHub Actions 跑 Python/Node/Rust 并上传 SARIF；`make demo` 十分钟跑通。
- **大仓库性能**：Django 5.1.4 3994 文件 34.4 s、VS Code 1.95.0 6362 文件 51.3 s
  （热缓存单进程）；修复 O(n²) 源码切片热点，单文件 1.8 s → 0.06 s。

### 支撑能力：Agent Crossbar 内的混合检索

- FTS5 BM25 + Embedding + RRF 融合，中文/英文查询、精确子串兜底、来源引用与词法降级。
- 自带 24 文档 / 72 查询合成语料：hybrid R@5 0.9722、MRR 0.9190、P95 77.7ms；
  同时公开 hybrid 语义 R@1 低于 vector 的真实退化。

## 工程验证

- `python scripts/demo.py`：spec → run → 安全评审 → Markdown/SARIF 全链路通过。
- `python scripts/security-benchmark.py --prepare`：固定 commit 重建独立基准。
- `npm run verify`：TypeScript、ESLint、Vitest、Vite build、Ruff、Pytest、Rust 检查。
- wheel 构建成功，`policy.yaml` 随包分发，console script 为 `crossbar-security`。

## 教育背景

南京邮电大学｜网络工程（本科）｜2023.09–2027.06  
主修：数据结构与算法、计算机网络、操作系统、数据库原理。
