# 安全引擎大仓库性能

生成时间：2026-11-14T09:50:43.416828+00:00
引擎版本：`agent_crossbar.security.engine` v0.1.0
运行环境：Windows-11-10.0.26200-SP0 / Python 3.13.15
CPU：Intel64 Family 6 Model 183 Stepping 1, GenuineIntel

这份报告衡量的是扫描耗时与噪声，不是检出率。仓库没有参与规则编写，
固定 commit，可用下面的命令重建。耗时为多次扫描的中位数，样本同时保留。

## 总览

| 仓库 | 版本 | 扫描文件 | 跳过文件 | 耗时 | 吞吐 | 问题数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Django | `5.1.4` | 3994 | 2833 | 34365.131 ms | 116.22 files/s | 146 |
| Visual Studio Code | `1.95.0` | 6362 | 954 | 51276.404 ms | 124.07 files/s | 509 |

## 明细

### Django

- 固定提交：`3e5887b9b1c1f06fabf96568a6ba7f19aeb9ad6d`
- 扫描文件 / 跳过文件：3994 / 2833
- 引擎内部耗时 / 端到端耗时：34348.592 ms / 34365.131 ms
- 吞吐：116.22 files/s
- 扫描样本：32943 ms, 34365 ms, 34656 ms
- 问题数：146（critical=2, high=121, info=1, low=7, medium=15）
- 高频规则：`CS-PY-004`×82, `CS-JS-002`×37, `CS-JS-004`×10, `CS-PY-011`×7, `CS-PY-010`×4, `CS-PY-001`×1, `CS-SECRET-008`×1, `CS-SECRET-009`×1

### Visual Studio Code

- 固定提交：`912bb683695358a54ae0c670461738984cbb5b95`
- 扫描文件 / 跳过文件：6362 / 954
- 引擎内部耗时 / 端到端耗时：51244.128 ms / 51276.404 ms
- 吞吐：124.07 files/s
- 扫描样本：51281 ms, 51222 ms, 51276 ms
- 问题数：509（high=486, info=2, medium=21）
- 高频规则：`CS-JS-002`×411, `CS-SECRET-009`×60, `CS-JS-004`×21, `CS-JS-001`×11, `CS-JS-005`×4, `CS-PY-000`×2

## 边界

- 这是 Windows 本机热缓存扫描，不是多线程、增量或分布式结果。
- 首次 clone 后受系统文件缓存与 Defender 影响会明显更慢；本报告不取冷启动极值。
- 跳过文件包含二进制、超大文件、缓存目录和命中 ignore 的路径。
- 问题数不等于漏洞数；该报告不提供精确率或召回率，检出率只以
  `docs/verification/security-benchmark.md` 的独立基准为准。
- 没有 10 万文件级别的企业单体仓库数据，不做该量级的承诺。

## 复现

```bash
python scripts/security-perf.py --prepare
```
