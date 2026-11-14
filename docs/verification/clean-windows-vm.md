# 干净 Windows 环境安装回归

本文件只写实际发生过的事。**没有**在本机的 Windows Sandbox / Hyper-V / VirtualBox / VMware
里跑过，因为本机没有这些组件。下面区分“已经有的证据”和“还缺的证据”。

## 已完成的证据

| 证据 | 环境 | 结果 | 链接 |
| --- | --- | --- | --- |
| 干净 Windows runner 安装 wheel、跑 CLI、产出 SARIF、跑 demo | GitHub `windows-latest`（每次都是全新 VM 镜像） | 通过 | Actions run `43590081493` |
| `pipx install` 后从 PATH 调用 `crossbar-security` | GitHub `windows-latest` | 通过 | `.github/workflows/release-smoke.yml` 的 `pipx-install` job |
| 安装后 `agent_crossbar.__file__` 必须指向 venv、不得回落到仓库源码 | 三个 runner | 通过 | 同上，`import origin must be the venv` 步骤 |
| MSI 静默安装 → 找到可执行文件 → 静默卸载 → 可执行文件消失 | GitHub `windows-latest` | 见该 job 结果 | `clean-msi` job |
| 本机 Python 3.10 全新 venv 安装 wheel 并端到端跑通 | 本机 Windows 11 家庭版 | 通过，63 秒 | `scripts/trial.ps1`，报告在临时目录 |

### 这一轮试跑抓到的真实 bug

`pyproject.toml` 声明 `requires-python >= 3.10`，但产品代码使用了 3.11 才有的
`datetime.UTC`。在一台只有 Python 3.10 的机器上，`crossbar-security --help` 直接
`ImportError`。已改为 `datetime.timezone.utc`，17 个文件同步修正。

这不是测试写出来的问题，是“按 README 一步步装”的人会遇到的第一个问题。它说明
干净环境回归必须做，而且必须用**没有开发环境**的 Python 版本去跑。

## 仍然缺的证据

GitHub 托管 runner 是干净 VM，但不是“用户从没装过任何开发工具的桌面”。

要补齐，需要一台真正的 Windows 11 虚拟机，按下面顺序记录：

1. 新建 VM，只装系统更新和 Edge。
2. 先尝试只用 `pipx install <wheel-url>`，记录是否需要额外依赖。
3. 再尝试 MSI 双击安装：记录 SmartScreen 提示原文、UAC 提示、安装耗时。
4. 启动应用，跑一次 demo，然后卸载，确认 `%LOCALAPPDATA%` 与注册表残留。
5. 把每一步的耗时和报错原文写进 `docs/verification/user-trials.md`。

没有这一步之前，`release-readiness.md` 里不能写“干净虚拟机回归通过”，只能写
“GitHub 干净 Windows runner 通过”。

## 复现命令

```powershell
# 构建 wheel
uv run --with build python -m build --wheel -o build/wheels

# 一键试跑（安装 + 不安全样本 + demo + 生成报告）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/trial.ps1
```