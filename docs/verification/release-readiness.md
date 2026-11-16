# 发布就绪状态（2026-11-16）

这份文件只记录事实，不把未完成写成完成。

| 项目 | 状态 | 证据或阻塞 |
| --- | --- | --- |
| 3 分钟演示视频 | 程序化版已完成；真人版待录 | `outputs/agent-crossbar-demo-3min.mp4`，179.3 秒；录制脚本已自检通过（`-Validate`、`-SelfTest`），需本人出镜 |
| 大仓库性能 | 已完成 | `docs/verification/security-performance.md`；Django 5.1.4 3994 文件 34.4 s，VS Code 1.95.0 6362 文件 51.3 s（3 次中位数，热缓存） |
| 干净 Python 环境安装 | 已完成 | `docs/verification/packaging-clean-env.md`；wheel 安装、policy.yaml、CLI、SARIF 均通过 |
| 干净 Windows 环境回归 | wheel 与 pipx 在 GitHub 干净 Windows runner 通过；MSI 静默安装挂起（有超时日志）；真机 VM 未做 | `docs/verification/clean-windows-vm.md`、`docs/verification/ci-release-smoke.md` |
| `pipx install` 可用性 | 已接入 CI | `release-smoke.yml` 的 `pipx-install` job |
| 生产 Authenticode 证书 | 未完成；Sigstore 已完成 | `docs/verification/authenticode.md`：自动化与校验就绪，缺 CA 证书 |
| 3 个真实外部用户 | 未完成（0 / 3） | 一键试跑与邀请包已就绪：`scripts/trial.ps1`、`docs/trials/`；2026-11-16 本机 3.10 全新 venv 149 秒 PASS，仍不能替代真人 |
| Python 3.10 兼容 | 已修复并验证 | 试跑发现 `datetime.UTC`（3.11+）导致 `ImportError`，已改为 `timezone.utc`；2026-11-16 本机 3.10 隔离 venv 完成安装、CLI、SARIF、demo（149 秒）；开发环境 243 tests |
| 第二个旗舰项目 | 已选型 MCP Guard | `docs/career/second-project-mcp-guard.md` |

## 干净环境回归的最低执行步骤（真机 VM）

1. 新建 Windows 11 虚拟机，只安装系统更新和 Edge。
2. 先试 `pipx install <wheel-url>`；再试 MSI 双击安装。
3. 记录 SmartScreen 原文、UAC 提示、每步耗时。
4. 启动应用，跑 demo，卸载，检查 `%LOCALAPPDATA%` 与注册表残留。
5. 结果写入 `docs/verification/user-trials.md`，不要只写“通过”。

## 生产签名需要的东西

- 受信任 CA 签发的 Authenticode 证书（或企业签名服务）。
- 证书私钥的保护方案，不得进入仓库。
- 时间戳服务 URL。
- 在干净机器上验证签名链、SmartScreen 行为与卸载后的文件残留。

这些都需要外部身份审核或付费，代码无法替代。
