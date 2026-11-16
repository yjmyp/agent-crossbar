# 安全规则独立基准

生成时间：2026-11-15T17:05:41.141786+00:00
扫描引擎：`agent_crossbar.security.engine` v0.2.0

标签由人工阅读公开项目源码后写入 `scripts/security_benchmark/manifest.json`，
不是扫描器输出。基准只衡量已支持规则族，不能代表完整安全审计能力。

## 总览

| 口径 | 命中 | 误报 | 精确率 | 召回率 |
| --- | --- | --- | --- | --- |
| 整仓库不设过滤 | 5 | 17 | 22.7% | 71.4% |
| 默认忽略规则 | 5 | 3 | 62.5% | 71.4% |
| 默认忽略 + 有期白名单 | 5 | 0 | 100.0% | 71.4% |
| 限定应用代码 | 5 | 0 | 100.0% | 71.4% |
| 限定应用代码 + 有期白名单 | 5 | 0 | 100.0% | 71.4% |

误报治理曲线：不设过滤 -> 默认忽略目录 -> 带 owner 与到期时间的规则白名单。
默认忽略 `vendor/`、`third_party/`、教程、示例、`fixtures/`、压缩产物与示例证书；
白名单在 `scripts/security_benchmark/policy.yaml`，过期条目自动失效。
所有口径同时公开，不只报最好看的一个。

## DSVW (Damn Small Vulnerable Web)

- 仓库：https://github.com/stamparm/DSVW.git
- 固定提交：`9ca3c9acf3defa0a6148d40e5f5cebeb5dcbb908`
- 扫描文件：10
- 默认忽略后：命中 2 / 误报 0 / 精确率 100.0%
- 白名单后：命中 2 / 误报 0 / 抑制 0 / 精确率 100.0%
- 限定口径：命中 2 / 误报 0 / 精确率 100.0% / 召回率 50.0%
- 未检出：dsvw.py:22, dsvw.py:29
- 明确不覆盖：reflected XSS, XXE, XPath injection

## OWASP NodeGoat

- 仓库：https://github.com/OWASP/NodeGoat.git
- 固定提交：`c5cb68a7084e4ae7dcc60e6a98768720a81841e8`
- 扫描文件：68
- 默认忽略后：命中 3 / 误报 3 / 精确率 50.0%
- 白名单后：命中 3 / 误报 0 / 抑制 3 / 精确率 100.0%
- 限定口径：命中 3 / 误报 0 / 精确率 100.0% / 召回率 100.0%
- 未检出：无
- 明确不覆盖：NoSQL injection ($where), broken authentication, access control

## 复现

```bash
python scripts/security-benchmark.py --prepare
```

脚本会按 manifest 中固定的 commit 拉取两个公开仓库到 `.bench-cache/`，
然后重新扫描并覆盖本报告。

