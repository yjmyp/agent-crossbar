# 生产签名：现在有什么，缺什么，多少钱

结论先说：**生产 Authenticode 证书买不到“代码里解决”**，它需要企业/个人身份审核。
仓库能做的部分是：证书一到，一条命令签名 + 自动校验 + CI 里强制验证。这部分已经完成。

## 已经完成

| 能力 | 位置 | 状态 |
| --- | --- | --- |
| PFX / 证书指纹两种签名方式 | `scripts/sign-windows.ps1` | 可用 |
| 未配置证书时明确输出 `not_configured`，不伪造签名 | 同上 | 可用 |
| 签名后自动用 `Get-AuthenticodeSignature` 校验 | 同上 + `scripts/verify-authenticode.ps1` | 可用 |
| CI 在检测到 `AGENT_CROSSBAR_PFX_BASE64` 时自动签名 MSI/exe 并强制校验 | `.github/workflows/release-smoke.yml` | 已接入 |
| CI 无论是否签名都产出 `signature-status.json` | 同上 | 已接入 |
| wheel 的 keyless 签名（Sigstore/cosign） | `.github/workflows/release-smoke.yml`、`release.yml` | 已跑通 |

## 缺的东西：证书本身

三条路径，按成本从低到高：

1. **Azure Trusted Signing**：按月订阅，最便宜，但需要 3 年以上的企业实体审核；
   个人开发者通常过不了。适合以后有公司主体时再上。
2. **OV / EV 代码签名证书**（DigiCert、Sectigo、SSL.com 等）：一年几百到几千元，
   需要营业执照或个人身份 + 电话核验，私钥必须放硬件令牌或云 HSM。
3. **自签名证书**：只能用于内部测试，**不能**写进 README 说“已签名”，
   SmartScreen 依然会拦。本仓库不使用这种方式冒充生产签名。

## 证书到位后的操作

申请免费/低成本开源签名的材料已写好：
[`authenticode-application.md`](authenticode-application.md)。需要你补的只有
许可证、真实身份和第一个 release。

```powershell
# 1. 导出 PFX（私钥不要进仓库，不要进聊天记录）
# 2. 配置仓库 secrets
#    AGENT_CROSSBAR_PFX_BASE64       = base64(PFX 文件)
#    AGENT_CROSSBAR_PFX_PASSWORD     = PFX 密码
# 3. 推一个 tag，release workflow 会自动签名并校验
git tag v0.1.1
git push origin v0.1.1
```

本地验证任何已签名文件：

```powershell
powershell -NoProfile -File scripts/verify-authenticode.ps1 .\dist\AgentCrossbar.msi -Json
```

## 简历/面试怎么写

可以写：**“Sigstore keyless 签名已接入 CI；Authenticode 签名的自动化与校验已就绪，
等待 CA 证书。”**

不能写：**“已完成代码签名”**。这两句话差别很大，面试官一查就穿帮。
