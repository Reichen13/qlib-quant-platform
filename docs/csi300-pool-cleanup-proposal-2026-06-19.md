# CSI300 股票池治理候选方案 - 2026-06-19

本方案只基于线上当前文件：

`/home/ubuntu/.qlib/qlib_data/cn_data/instruments/csi300.txt`

用户已确认并执行方案 B。线上原文件已备份，当前 `csi300.txt` 已替换为去污染、去重后的 653 行版本。

线上备份文件：

`/home/ubuntu/.qlib/qlib_data/cn_data/instruments/csi300.txt.bak-scheme-b-20260619-232110`

## 当前状态

| 指标 | 数值 |
| --- | ---: |
| 原始行数 | 820 |
| 唯一代码数 | 690 |
| 重复行数 | 130 |
| 已确认退市/历史污染唯一代码 | 37 |
| 已确认退市/历史污染行数 | 40 |

这说明当前 `csi300.txt` 不是严格意义上的“当前 CSI300 300 只成分股”，更像历史成分股集合或多期合并结果。

## 已生成候选文件

本地候选目录：

`server_merge_work/csi300_cleanup/`

文件：

- `csi300.current.txt`：线上当前文件副本
- `csi300.remove-stale.txt`：方案 A，只移除退市/历史污染项
- `csi300.remove-stale.report.json`：方案 A 报告
- `csi300.remove-stale-dedupe.txt`：方案 B，移除退市/历史污染项并去重
- `csi300.remove-stale-dedupe.report.json`：方案 B 报告

## 方案 A：只移除退市/历史污染项

影响：

| 指标 | 处理前 | 处理后 |
| --- | ---: | ---: |
| 原始行数 | 820 | 780 |
| 唯一代码数 | 690 | 653 |
| 重复行数 | 130 | 127 |
| 移除行数 | - | 40 |

优点：

- 改动较小；
- 只移除已确认 `status=0` 且有 `out_date` 的历史污染项；
- 仍保留原文件的重复结构，较少影响依赖历史成分股时间段的逻辑。

缺点：

- 仍不是标准 300 只；
- 仍保留 127 行重复；
- 因子分析/回测仍可能使用一个偏大的历史样本池。

## 方案 B：移除污染项并去重

影响：

| 指标 | 处理前 | 处理后 |
| --- | ---: | ---: |
| 原始行数 | 820 | 653 |
| 唯一代码数 | 690 | 653 |
| 重复行数 | 130 | 0 |
| 移除行数 | - | 167 |

优点：

- 口径更清楚；
- 不再重复统计成分股；
- 当前健康检查、因子分析、回测样本更容易解释。

缺点：

- 改动较大；
- 仍然不是“当前 CSI300 300 只”，只是当前文件去污染去重后的 653 只；
- 如果某些历史回测逻辑依赖重复行或历史成分区间，可能改变回测样本。

执行状态：已执行。

执行后验证：

- `/api/data/health` 连续返回 `healthy`
- `stocks.total = 653`
- `stocks.raw_total = 653`
- `stocks.duplicate_count = 0`
- `stocks.last_date = 2026-06-18`
- `quant-backend` 容器状态为 `healthy`

## 不建议直接做的事

暂不建议直接把股票池改成“当前 300 只”。原因：

- 需要权威指数成分来源和日期口径；
- 当前项目可能把 `csi300.txt` 当作历史样本池使用；
- 直接压缩到当前 300 只会明显改变历史回测和因子分析结果。

## 建议决策

已按用户确认选择方案 B：

移除 37 个已确认退市/历史污染代码对应的 40 行，同时去除其它重复行。历史行情文件未删除。

中期再做：

1. 新增一个独立文件，例如 `csi300_current.txt`，只存当前 300 成分股；
2. 让页面或策略明确选择“历史样本池”还是“当前 CSI300”；
3. 再决定是否把因子分析默认样本改成当前成分股。

## 若执行方案 A

执行前必须备份：

```bash
cp /home/ubuntu/.qlib/qlib_data/cn_data/instruments/csi300.txt \
  /home/ubuntu/.qlib/qlib_data/cn_data/instruments/csi300.txt.bak-$(date +%Y%m%d-%H%M%S)
```

然后将 `csi300.remove-stale.txt` 替换为线上 `csi300.txt`。

执行后验证：

- `/api/data/health` 仍为 `healthy`
- `stocks.total` 应为 `653`
- `stocks.raw_total` 应为 `780`
- `duplicate_count` 应为 `127`
