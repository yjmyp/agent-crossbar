# 简历 B：AI 应用开发 / 安全与交付

> 同一份项目，换成“安全交付”叙事。适合投 Agent 平台、DevTools、代码安全、
> AI 工程效率方向。数字与 A 版一致，不能同时投递互相矛盾的两版。

## 余剑

求职方向：AI 应用开发 / Agent 安全与交付  
南京邮电大学 · 网络工程（本科）· 2027 届（2023.09–2027.06）  
电话：17578999648 · 邮箱：yj2994762833@gmail.com · 南京  
GitHub：https://github.com/yjmyp

## 个人概述

关注 Agent 生成代码后的“最后一公里”：代码有没有密钥/注入/危险命令，运行有没有超预算，
出了问题能不能追到同一条 trace，风险能不能被责任人限时豁免。独立实现 Agent Crossbar
的交付安全闸门，并用公开漏洞项目做独立基准，公开精确率、召回率和明确不覆盖的范围。

## 专业技能

- 安全扫描：Python AST、轻量污点分析、正则规则、脱敏、SARIF、策略条款映射
- Agent 工程：工具循环、事件轨迹、MCP、LangGraph、多 Agent 委派、行为预算
- 后端与数据：Python、FastAPI、Pydantic、SQLite/WAL、REST、SSE
- 前端与交付：React/TypeScript、Tauri、GitHub Actions、wheel/console script
- 工程习惯：结论可复现、边界写清楚、不把回归样本当检出率

## 项目经历

### Agent Crossbar｜Agent 交付安全闸门与本地工作台

独立开发｜2026.10 – 至今｜https://github.com/yjmyp

- **问题定义**：Coding Agent 能快速生成代码，但团队缺少一个能回答“这次改动能不能交付”的
  本地闸门。项目把代码扫描、运行行为、组织豁免合成一个 `block/fix/ship` 结论。
- **确定性扫描**：31 条规则覆盖硬编码密钥、私钥/.env、`eval/exec`、`shell=True`、
  不安全 pickle/YAML、SQL/路径注入、关闭 TLS、弱哈希、危险 CORS 等；输出中文标题、
  修复建议、CWE、脱敏证据和策略条款（SEC-01…SEC-14）。
- **外发边界**：默认不调用任何外部模型，报告明确写“源码、片段与证据未离开本机”；
  外部模型复核是显式开关，只发脱敏片段，并记录文件列表与 provider。
- **行为预算**：评审可关联真实 run，读取事件计算模型轮次、工具调用、Token、时长、
  禁用工具，与同一份策略预算逐项对照；超限直接阻断。
- **责任豁免**：豁免必须有规则、文件范围、owner、理由、到期时间；过期或撤销不生效，
  报告记录 `waived_by` 与 `waived_until`，避免“永久忽略”。
- **独立基准**：固定 DSVW（commit 9ca3c9a）与 OWASP NodeGoat（commit c5cb68a），
  人工标注 7 个漏洞行；召回率 71.4%，整仓库精确率 16.7% -> 规则修复后 22.7% ->
  默认忽略后 62.5% -> 带 owner/到期时间的规则白名单后 100.0%，曲线完整公开。
  明确不覆盖 XSS、XXE、XPath、NoSQL、认证与访问控制，不宣称完整 SAST。
- **交付链路**：Markdown 报告可直接贴 PR；SARIF 上传 GitHub Code Scanning；
  `crossbar-security` 可 `pipx install`，CI 中阻断时退出码为 1。

### 支撑能力：可审计的 Agent 运行时

- Tauri + 回环 FastAPI sidecar + SQLite WAL；AgentSpec 不可变并带 SHA-256。
- 事件单调序号、SSE 重连、工具异常回填、超时/取消、多 Agent 委派与 Worker 失败转移。
- 11 类评测断言，既能测最终输出，也能测工具顺序、调用次数和错误轨迹。

## 工程验证

- Python 211 项、前端 71 项自动化测试通过；`npm run verify` 覆盖类型、lint、测试、构建。
- `make demo` / `python scripts/demo.py` 十分钟跑通 spec → run → 评审 → SARIF。
- GitHub Actions：`verify.yml`（Python/Node/Rust）+ `security.yml`（SARIF 上传）。
- wheel 包含 `policy.yaml`，不包含测试目录；console script 实测可执行。

## 教育背景

南京邮电大学｜网络工程（本科）｜2023.09–2027.06  
主修：数据结构与算法、计算机网络、操作系统、数据库原理。
