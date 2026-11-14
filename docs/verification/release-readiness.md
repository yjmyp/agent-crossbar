# 发布就绪状态（2026-11-14）

这份文件只记录事实，不把未完成写成完成。

| 项目 | 状态 | 证据或阻塞 |
| --- | --- | --- |
| 3 分钟演示视频 | 已完成（程序化渲染） | `outputs/agent-crossbar-demo-3min.mp4`，179.4 秒；终端实录 + 已验证数字 + 架构卡片，不是真人出镜 |
| 大仓库性能 | 已完成 | `docs/verification/security-performance.md`；Django 5.1.4 3994 文件 34.4 s，VS Code 1.95.0 6362 文件 51.3 s（3 次中位数，热缓存） |
| 干净 Python 环境安装 | 已完成 | `docs/verification/packaging-clean-env.md`；wheel 安装、policy.yaml、CLI、SARIF 均通过 |
| 干净 Windows 虚拟机回归 | 未完成 | 本机没有 Windows Sandbox / Hyper-V / VirtualBox / VMware；无法伪造 |
| 生产 Authenticode 证书 | 未完成 | 需要购买代码签名证书并保护私钥；仓库内没有生产证书 |
| 3 个真实外部用户 | 未完成（0 / 3） | 需要真人独立试用；`docs/verification/user-trials.md` 保留空表，不编造 |

## 干净虚拟机回归的最低执行步骤

1. 新建 Windows 11 虚拟机，只安装系统更新和 Edge。
2. 安装 `uv`、Node.js LTS、Rust stable 与 MSVC Build Tools。
3. 克隆固定 commit，执行 `make bootstrap` 与 `make demo`。
4. 运行 MSI 安装、启动、卸载，确认用户数据保留。
5. 记录每一步耗时、报错原文、是否需要管理员权限。
6. 把结果写入 `docs/verification/user-trials.md`，不要只写“通过”。

## 生产签名需要的东西

- 受信任 CA 签发的 Authenticode 证书（或企业签名服务）。
- 证书私钥的保护方案，不得进入仓库。
- 时间戳服务 URL。
- 在干净机器上验证签名链、SmartScreen 行为与卸载后的文件残留。

