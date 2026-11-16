# 用户试用记录

状态：**真人 0 / 3**。本文件不包含任何虚构用户、姓名或反馈。

## 现在能自动做到什么

| 项目 | 状态 |
| --- | --- |
| 三个干净 OS runner 独立跑通 | 已完成 |
| 一条命令完成“安装 → 不安全样本 → demo → 生成报告” | 已完成：`scripts/trial.ps1` |
| 本机 Python 3.10 全新 venv 试跑 | 已通过；2026-11-16 复跑 149 秒，报告 `local-trial-20261116.md` |
| 邀请话术与协议 | 已完成：`docs/trials/README.md` |
| GitHub issue 反馈表单 | 已完成：`.github/ISSUE_TEMPLATE/user-trial.yml` |
| 3 个真人 | **0 / 3，未开始** |

自动试跑不能替代真人。它能证明“机器能装上”，不能证明“人看得懂”。

2026-11-16 的复跑还修了两处试跑路径问题：pip 默认 15 秒超时在慢网络下会失败，
已改为 60 秒 + 5 次重试并支持 `-PipIndexUrl`；CLI 验证从 `python -m` 改为真实
`crossbar-security.exe`，确保 console script 本身可用。

## 这一轮自动试跑发现的真实问题

1. **Python 3.10 直接 `ImportError`**：产品代码用了 `datetime.UTC`（3.11+），
   而 `pyproject.toml` 声明支持 3.10。已修为 `timezone.utc`。
2. **试跑脚本本身吞掉了报错**：PowerShell 把原生 stderr 包装成 `ErrorRecord`，
   原实现只留下第一行 `Traceback`，看不到真正原因。已改为逐条取
   `Exception.Message`，现在报告里能看到完整 traceback 最后一行。

这两条都不是单元测试能发现的，只有“按用户路径装一遍”才会暴露。

## 怎么在 3 天内凑齐 3 个人（可执行）

不要群发“帮我看看项目”。给对方一个 10 分钟的任务和一条命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/trial.ps1 -WheelPath <wheel 路径>
```

| 渠道 | 具体做法 | 预期 |
| --- | --- | --- |
| 同学 / 前同事 | 找 2 个写过 Python 但没碰过这个项目的人，约 15 分钟屏幕共享 | 最容易成，优先 |
| 技术社区 | V2EX「分享创造」、即刻、掘金发帖：招 3 位测试者，送咖啡券，要求录屏 | 1–2 天有响应 |
| GitHub | 在 README 加 “Looking for 3 trial users” 并开 Discussion | 慢，但长期有 |

对方只需要：Windows + Python 3.10+ + 一条命令。不需要 Node、Rust、uv。

## 试用协议

1. 只给仓库链接、README 和一台干净机器。
2. 不口头提示，不替对方操作；观察并计时。
3. 记录：卡在第几步、报错原文、花了多久、是否需要管理员权限。
4. 只修真实卡点，不为每个人加一个定制开关。
5. 把修复前后的耗时和原话写回本文件。

## 记录表

| 用户 | 背景 | 是否跑通 | 首次成功耗时 | 卡点原文 | 修复 |
| --- | --- | --- | --- | --- | --- |
| 待招募 | — | 未开始 | — | — | — |
| 待招募 | — | 未开始 | — | — | — |
| 待招募 | — | 未开始 | — | — | — |

## 当前已知门槛（未修）

- 桌面 UI 仍需 Tauri 开发环境；CLI 安全闸门不需要。
- MSI 未签名，SmartScreen 会拦；这是证书问题，不是代码问题。
- `make demo` 在 Windows 上需要 GNU make；README 已给 PowerShell 替代命令。
