# 签名就绪状态

日期：2026-11-14

## 已经做到

- GitHub Actions 在 `ubuntu-latest` 上对 wheel 执行 Sigstore keyless 签名。
- 签名使用 GitHub OIDC，不需要把长期私钥放进仓库。
- 产物包含 `.whl`、`.sig`、`.pem`，可被第三方验证。

验证命令：

```bash
cosign verify-blob \
  --certificate dist/agent_crossbar.pem \
  --signature dist/agent_crossbar.sig \
  dist/agent_crossbar-0.1.0-py3-none-any.whl
```

Sigstore 证明“这个 wheel 由这个仓库的这次 workflow 构建”，但它**不是**
Windows Authenticode，不能让 SmartScreen 显示受信任发布者。

## 仍然缺什么

生产 Authenticode 需要：

1. 受信任 CA 签发的代码签名证书，或企业签名服务。
2. 通过身份/组织验证；个人学生身份通常需要 OSS 项目申请或付费。
3. 私钥保护方案：HSM、云密钥库或 CI secret，不能进仓库。
4. 时间戳服务。
5. 在干净 Windows 机器上验证签名链、SmartScreen 和卸载残留。

这些都需要外部身份审核或付费，代码无法替代。**仓库不会生成一个自签名证书
然后把它写成“生产签名”。**

## 可选路径

| 路径 | 适合 | 代价 |
| --- | --- | --- |
| Certum Open Source Code Signing | 公开开源项目 | 免费/低成本，需审核 |
| SignPath Foundation | 公开开源项目 | 免费，需申请 |
| Azure Trusted Signing | 有 Azure 身份的组织 | 付费 + 组织验证 |
| 标准 OV/EV 代码签名证书 | 商业发布 | 每年数百美元起，需企业验证 |

## 申请前准备

- 仓库公开 URL、许可证、README、发布 artifact。
- 项目说明、下载量/用户量（有就写，没有不编）。
- 维护者身份证明与联系方式。
- 签名后的发布流程：谁触发、谁审批、私钥在哪里。

## 当前结论

- **Sigstore 产物签名：已完成。**
- **Windows Authenticode 生产签名：未完成，阻塞在证书与身份验证。**

