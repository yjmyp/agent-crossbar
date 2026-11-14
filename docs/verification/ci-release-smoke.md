# GitHub Actions 干净环境发布 smoke

日期：2026-11-14

## 结论

三个 GitHub 托管的干净 runner 全部通过 wheel 安装、CLI 阻断、SARIF 生成和
`scripts/demo.py` 全链路：

| Runner | 结果 | 说明 |
| --- | --- | --- |
| `windows-latest` | 通过 | 干净 Windows VM 镜像，Python 3.13，wheel 安装 |
| `ubuntu-latest` | 通过 | 干净 Linux VM，Python 3.13，wheel 安装 + Sigstore keyless 签名 |
| `macos-latest` | 通过 | 干净 macOS VM，Python 3.13，wheel 安装 |

每个 job 都做了：

1. `python -m build --wheel`
2. 新建空 venv
3. 只安装 wheel（不安装仓库开发依赖）
4. 断言 `agent_crossbar.__file__` 位于 venv，没有回落到仓库源码
5. 对含 `shell=True` 的样本执行 `crossbar-security`
6. 断言退出码为 1，且 SARIF 非空
7. 在干净环境执行 `scripts/demo.py`，断言 `review.md` 与 `review.sarif` 存在
8. 上传 wheel、SARIF、评审报告为 artifact

Ubuntu job 额外执行 `cosign sign-blob`，产出 keyless 签名与证书。

`pipx-install` job 另做：`python -m pipx install dist/*.whl`，再从 PATH 调用
`crossbar-security`，验证“用户不建 venv 也能用”。

## verify workflow 的四个 job

| Job | 内容 |
| --- | --- |
| `python` | `ruff check` + 211 个 pytest |
| `frontend` | typecheck、eslint、63 个 vitest、生产构建 |
| `node-scripts` | 8 个 PowerShell 辅助函数与 CDP 选择器单元测试 |
| `rust` | `cargo fmt --check` + `cargo test` + `cargo check` |

### 这一轮修掉的 CI 问题（都是真实问题）

1. **前端 job 把 scripts 测试一起跑了**：`vitest` 默认收集 `scripts/**/*.test.mjs`，
   这些测试依赖 `powershell.exe`，在 Ubuntu 必挂。已拆出 `vitest.scripts.config.ts`，
   两边互不干扰。
2. **rust job 在 Ubuntu 必挂**：crate 里有 Windows 凭据管理器逻辑，已改为
   `windows-latest`。
3. **rust 在 Windows 也挂**：`tauri-build` 要求
   `src-tauri/binaries/agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe` 存在，
   而该文件被 gitignore。job 里先建占位文件（编译期只需要存在，单元测试不启动它）。
4. **两个 MSI 选择测试在 CI 上失败**：原实现依赖 `sleep(1100)` 与真实文件时间，
   在 CI 上不稳定。已改为用 `utimes` 设置显式时间戳，不依赖时钟与 sleep。
5. **MSVC 长路径下 `ring` 编译报 D8050**：job 级设置
   `CARGO_PROFILE_*_DEBUG=0`，编译不需要调试信息。

## MSI

`clean windows MSI build + install` job：

- 安装 Python/Node/Rust
- 构建 PyInstaller sidecar
- 执行 `npm run tauri build`（**这一步成功**）
- `msiexec /i ... /qn` 静默安装
- 检查安装后的 `Agent Crossbar.exe`
- `msiexec /x ... /qn` 卸载

**已知阻塞**：在 GitHub 托管 runner 上，`msiexec` 静默安装会挂起，原实现没有超时，
两个 job 卡了 45 分钟。已改为 10 分钟硬超时 + 保留 `msi-install.log`。

因此当前结论是：

- **MSI 能构建**：产物已上传为 artifact。
- **MSI 静默安装在托管 runner 上未通过**：需要在一台真正的 Windows 11 桌面上
  记录安装日志，判断是安装包问题还是 runner 环境限制。
- 不把 wheel smoke 冒充 MSI 回归。

## 复现

```bash
# 本地起同样流程
uv run --with build python -m build --wheel -o build/wheels
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/trial.ps1
```