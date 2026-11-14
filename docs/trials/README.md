# Agent Crossbar 用户试用包

目标：让 3 个没有参与开发的人，只靠 README 和一条命令跑通，并记录他们卡在哪里。

## 邀请话术（直接复制）

> 我在做一个本地 Agent 交付安全闸门，想请你帮我做一次 15 分钟盲测。
> 你不需要懂我的项目，也不用给我面子。只按 README 操作，卡住就停，
> 把报错原文和你的第一反应告诉我。可以选择匿名，我不会公开你的姓名。

## 试用协议

1. 只发仓库链接：https://github.com/yjmyp/agent-crossbar
2. 不口头提示，不替对方操作，不先解释架构。
3. 让对方共享屏幕或录屏；记录每一步耗时。
4. 卡住时只问：“你现在期待发生什么？实际发生了什么？”
5. 不争论，不解释“其实可以这样”；先记录，再修。
6. 试用结束后填写 `.github/ISSUE_TEMPLATE/user-trial.yml` 或直接回复反馈表。

## 对方要执行的两条命令

```powershell
git clone https://github.com/yjmyp/agent-crossbar
cd agent-crossbar
uv run --with build python -m build --wheel -o build/wheels
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/trial.ps1
```

脚本会自己建 venv、装 wheel、跑不安全样本、跑 demo，并在
`%TEMP%\crossbar-trial-<时间戳>\report.md` 写一份带耗时和报错的报告。
对方只需要把 `report.md` 发回来。

实测：本机 Windows 11 + Python 3.10 全新 venv，63 秒 PASS。

## 反馈表

| 字段 | 内容 |
| --- | --- |
| 系统 / 版本 | 例如 Windows 11 23H2 |
| 是否有 Python/Node/Rust 经验 | 有 / 无 |
| 第一次成功耗时 | 分钟 |
| 卡在第几步 | 原文 |
| 报错原文 | 不要改写 |
| 最难理解的词 | 例如 sidecar、SARIF、豁免 |
| 是否愿意再使用 | 愿意 / 不愿意 / 看情况 |
| 最该修的一件事 | 一句话 |

## 结果记录

把真实结果写回
[`docs/verification/user-trials.md`](../verification/user-trials.md)。
没有真人结果就继续写 `0 / 3`，不要用“朋友说不错”代替。

