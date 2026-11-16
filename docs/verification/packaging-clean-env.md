# 干净 Python 环境安装验证

日期：2026-11-16

## 结论

wheel 在一个全新虚拟环境中安装成功，`policy.yaml` 随包分发，console script
`crossbar-security` 可直接执行，扫描 `work/demo/repo` 时按预期返回退出码 1
并生成 SARIF。**这不是干净虚拟机验证**，只是干净 Python 环境验证。

## 实测步骤

```powershell
uv build --wheel
uv venv work/clean-env-20261114/.venv --python 3.13
uv pip install --python work/clean-env-20261114/.venv/Scripts/python.exe `
  dist/agent_crossbar-0.1.0-py3-none-any.whl
work/clean-env-20261114/.venv/Scripts/crossbar-security.exe `
  --root work/demo/repo --format sarif -o work/clean-env-20261114/security.sarif --lang zh
```

## 结果

- 安装依赖：63 个包，全部从 wheel 与公开索引解析，耗时约 4 秒。
- `agent_crossbar.__file__` 位于新虚拟环境的 `site-packages`。
- `site-packages/agent_crossbar/security/policy.yaml` 存在。
- CLI 退出码为 1，因为演示仓库包含未豁免的 `CS-PY-003`。
- SARIF 文件生成成功，大小 14,703 字节。

## 2026-11-16 复跑

用 `scripts/trial.ps1` 从一个全新 venv 完整复跑，结果为 **PASS，149 秒**：

- 新建 venv 26,004 ms；依赖安装 108,200 ms。
- 真实 console script `crossbar-security.exe --help` 通过。
- 不安全样本按预期退出码 1，并生成 SARIF。
- `scripts/demo.py` 通过，输出 `block` 结论和 1 个阻断 finding。
- 报告：`docs/verification/local-trial-20261116.md`。

第一次复跑曾因 `pypi.org` 15 秒读超时失败；`scripts/trial.ps1` 已改为
`--timeout 60 --retries 5`，并支持 `-PipIndexUrl` 覆盖镜像源。

## 未完成

- 没有在干净 Windows 虚拟机执行 MSI 安装、卸载、升级与用户数据保留回归。
- 本机没有 Windows Sandbox、Hyper-V、VirtualBox 或 VMware，无法在本次会话补做。
- 没有生产 Authenticode 证书，签名验证仍只覆盖测试证书/开发流程。

