# GitHub Actions 干净环境发布 smoke

日期：2026-11-14

运行：https://github.com/yjmyp/agent-crossbar/actions/runs/43590081493

## 结论

三个 GitHub 托管的干净 runner 全部通过 wheel 安装、CLI 阻断、SARIF 生成和
`scripts/demo.py` 全链路：

| Runner | 结果 | 说明 |
| --- | --- | --- |
| `windows-latest` | 通过 | 干净 Windows VM，Python 3.13，wheel 安装 |
| `ubuntu-latest` | 通过 | 干净 Linux VM，Python 3.13，wheel 安装 + Sigstore keyless 签名 |
| `macos-latest` | 通过 | 干净 macOS VM，Python 3.13，wheel 安装 |

每个 job 都做了：

1. `python -m build --wheel`
2. 新建空 venv
3. 只安装 wheel（不安装仓库开发依赖）
4. 对含 `shell=True` 的样本执行 `crossbar-security`
5. 断言退出码为 1，且 SARIF 非空
6. 在干净环境执行 `scripts/demo.py`，断言 `review.md` 与 `review.sarif` 存在
7. 上传 wheel、SARIF、评审报告为 artifact

Ubuntu job 额外执行 `cosign sign-blob`，产出 keyless 签名与证书。

## MSI

`clean windows MSI build + install` job 仍在构建/安装验证中。该 job 会：

- 安装 Python/Node/Rust
- 构建 PyInstaller sidecar
- 执行 `npm run tauri build`
- `msiexec /i ... /qn` 静默安装
- 检查安装后的 `Agent Crossbar.exe`
- `msiexec /x ... /qn` 卸载

结果单独记录在
[`release-readiness.md`](release-readiness.md)，不把 wheel smoke 冒充 MSI 回归。

