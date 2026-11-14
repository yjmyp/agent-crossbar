# 安全规则独立基准

生成时间：2026-11-13T20:31:41.438209+00:00
扫描引擎：`agent_crossbar.security.engine` v0.1.0

标签由人工阅读公开项目源码后写入 `scripts/security_benchmark/manifest.json`，
不是扫描器输出。基准只衡量已支持规则族，不能代表完整安全审计能力。

## 总览

| 口径 | 命中 | 误报 | 精确率 | 召回率 |
| --- | --- | --- | --- | --- |
| 限定应用代码 | 5 | 1 | 83.3% | 71.4% |
| 整仓库不设过滤 | 5 | 25 | 16.7% | 71.4% |

整仓库口径会把第三方压缩库、教程、示例证书和测试脚本算进来，
因此精确率明显更低。这两个数字应同时公开，而不是只报好看的一个。

## DSVW (Damn Small Vulnerable Web)

- 仓库：https://github.com/stamparm/DSVW.git
- 固定提交：`9ca3c9acf3defa0a6148d40e5f5cebeb5dcbb908`
- 扫描文件：10
- 限定口径：命中 2 / 误报 0 / 精确率 100.0% / 召回率 50.0%
- 未检出：dsvw.py:22, dsvw.py:29
- 明确不覆盖：reflected XSS, XXE, XPath injection

## OWASP NodeGoat

- 仓库：https://github.com/OWASP/NodeGoat.git
- 固定提交：`c5cb68a7084e4ae7dcc60e6a98768720a81841e8`
- 扫描文件：92
- 限定口径：命中 3 / 误报 1 / 精确率 75.0% / 召回率 100.0%
- 未检出：无
- 明确不覆盖：NoSQL injection ($where), broken authentication, access control

## 复现

```bash
python scripts/security-benchmark.py --prepare
```

脚本会按 manifest 中固定的 commit 拉取两个公开仓库到 `.bench-cache/`，
然后重新扫描并覆盖本报告。

