# 免费/低成本代码签名申请材料（可直接粘贴）

生产 Authenticode 证书无法由代码生成，必须由 CA 审核身份。下面是能直接提交的
申请材料，适用于 SignPath Foundation、Certum Open Source Code Signing 等
面向开源项目的计划。**没有提交之前，简历里不能写“已完成代码签名”。**

## 项目基本信息

- 项目名：Agent Crossbar
- 仓库：https://github.com/yjmyp/agent-crossbar
- 许可证：（填仓库实际许可证，没有就先补一个 OSI 许可证）
- 语言：Python 3.10+ / TypeScript / Rust (Tauri)
- 发布物：Python wheel、Windows MSI、Windows 可执行文件
- 维护者：（真实姓名 + 邮箱 + GitHub 账号）

## 一句话简介

Agent Crossbar is a local-first delivery gate for AI-agent-generated code. It
scans changes with deterministic rules, checks run-level behaviour budgets, and
requires time-boxed risk waivers, producing a single block/fix/ship decision with
Markdown and SARIF output.

## 用途说明（英文，直接粘贴）

> The signed artifacts are the Python wheel and the Windows installer of a
> developer tool. Users run it locally against their own repositories. The tool
> never uploads source code, never calls a model by default, and has no network
> server component. Code signing is required so that Windows users can verify
> the installer's publisher and so that enterprise users can allow the
> executable under application-control policies.

## 为什么需要签名

- 用户双击 MSI 时，SmartScreen 目前会拦截未签名安装包。
- 企业环境的应用白名单通常要求有效 Authenticode 签名。
- 用户需要能验证“这个安装包确实来自本项目发布流程”。

## 安全承诺（申请时通常会被问）

- 私钥不进入仓库，不进入 CI 日志。
- 私钥存放在硬件令牌或云 HSM；CI 通过密钥库短期凭证签名。
- 每次发布由仓库 tag 触发，产物附带 SHA-256 与 Sigstore 签名。
- 已实现：`scripts/sign-windows.ps1`、`scripts/verify-authenticode.ps1`、
  `.github/workflows/release.yml`。
- 未实现（如被问，如实说）：还没有第三方安全审计。

## 提交清单

| 材料 | 状态 |
| --- | --- |
| 公开仓库 | 有 |
| OSI 许可证 | 已补 MIT（`LICENSE`），如你要换协议自行替换 |
| README 与构建说明 | 有 |
| 可下载的 release 产物 | 打第一个 tag 后生成 |
| 维护者身份证明 | 需本人提供 |
| 项目用途说明 | 本文件 |
| 无私钥入库的证明 | `.gitignore` + 仓库无 `.pfx` 历史 |
