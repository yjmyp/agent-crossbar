# 3 分钟真人演示录制包

目标：让本人出镜 + 屏幕录制 + 麦克风 narration 一次完成，不需要 OBS 配置。

## 先检查设备

```powershell
.\scripts\record-demo.ps1 -ListDevices
```

本机当前检测到：

- 摄像头：`Integrated Camera`
- 麦克风：`麦克风阵列 (Realtek(R) Audio)`

## 录制

```powershell
.\scripts\record-demo.ps1 -Seconds 180
```

默认输出：`outputs/agent-crossbar-human-demo.mp4`

录制内容：

- 全屏桌面
- 右下角摄像头画中画
- 麦克风音轨

## 录制前 5 分钟

1. 关掉微信、邮箱、浏览器标签和任何含公司数据的窗口。
2. 打开 `docs/career/teleprompter.html`，放在手机或第二块屏幕。
3. 打开一个干净终端，`cd` 到仓库，先跑一次 `python scripts/demo.py` 确认。
4. 桌面分辨率调到 1920×1080，字号调大。
5. 先录 15 秒测试，回放确认声音和画中画位置。

## 3 分钟节奏

| 时间 | 画面 | 说什么 |
| --- | --- | --- |
| 0:00–0:15 | 本人 + 标题 | 这是 Agent Crossbar，解决 Agent 代码交付前没有结论的问题 |
| 0:15–0:40 | 终端 | 跑 demo，看到 block、命中 shell=True、行为预算通过 |
| 0:40–1:10 | 报告 | 中文标题、脱敏证据、条款、SARIF |
| 1:10–1:40 | 基准 | 83.3% / 71.4%，整仓库 16.7% 也公开 |
| 1:40–2:10 | 性能 | Django 34.4s、VS Code 51.3s，修掉 O(n²) |
| 2:10–2:40 | 边界 | 不是平台、不是完整 SAST、3 个用户仍未完成 |
| 2:40–3:00 | 本人 | 每个结论都能被一条命令复现 |

## 诚实边界

这段视频需要你本人出镜和说话。我无法代替你成为真人，也不会用 AI 头像伪装。
录完把文件放在 `outputs/`，不要提交到仓库。

