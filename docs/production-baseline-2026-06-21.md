# 2026-06-21 线上部署前基线

采集时间：2026-06-21，Asia/Shanghai。

本文件记录部署前的公开只读状态，用于后续验证“代码部署”和“数据修复”是否真的在线上生效。未访问 SSH，未触发数据更新、因子分析或其他写入/重计算操作。

## GitHub 状态

仓库：`https://github.com/Reichen13/qlib-quant-platform`

`main` 最新提交：

```text
98c7e18d1e012bc75cb823e9bf0d963b372004f7
```

本地 `main` 与 `origin/main` 一致。

## 线上健康状态

公开地址：

```text
http://49.235.215.39:9090
```

`GET /health` 返回：

```json
{
  "status": "healthy",
  "qlib": "initialized",
  "timestamp": "2026-06-21T12:35:15.426851"
}
```

说明：后端服务可访问，Qlib 已初始化。

## 数据健康状态

`GET /api/data/health` 关键结果：

```text
overall_status: warning
qlib last_date: 2026-06-18
qlib lag_days: 2
qlib data_dir: /root/.qlib/qlib_data/cn_data
qlib n_features: 31169
qlib sample_latest_coverage: 0.74
stocks total: 3876
stocks last_date: 2026-06-18
stocks lag_days: 2
csi300_total: 653
index total: 12
index last_date: 2026-06-18
```

说明：

- 当前线上股票覆盖数量已经接近全市场规模，但仍低于 4000+ 的完整 A 股范围。
- 数据日期到 `2026-06-18`，按接口判断滞后约 2 个交易日。
- Qlib 数据目录在线上为 `/root/.qlib/qlib_data/cn_data`，后续备份和修复要以服务器实际目录为准。

## 600519 K 线 0 值基线

`GET /api/quote/600519?frequency=daily&indicators=true` 统计结果：

```json
{
  "code": "SH600519",
  "total": 61,
  "first": "2026-03-20",
  "first_valid": "2026-04-30",
  "zero_ohlc_count": 28,
  "last": "2026-06-18",
  "last_close": 1215.0
}
```

说明：

- 线上接口不是缺少 2026 年 4 月以前的日期，而是 `2026-03-20` 到 `2026-04-29` 之间存在 28 行开高低收全为 0 的无效 K 线。
- 第一条有效 K 线仍是 `2026-04-30`。
- 这证明当前线上还没有部署并执行本轮的 K 线 0 值修复。

## 后续部署验证标准

部署代码后先运行：

```bash
bash scripts/verify_current_fixes.sh
```

若 `600519` 仍显示 `QUOTE_ZERO_OHLC_PRESENT`，再执行单只股票修复：

```bash
python update_cn_data.py --code sh600519 --start 2026-03-20 --end 2026-06-19 --rebuild-stale
```

修复成功的最小标准：

- `zero_ohlc_count` 从 28 明显下降，理想为 0。
- `first_valid` 早于 `2026-04-30`。
- 行情分析中贵州茅台 K 线不再只从 4 月底开始显示。

## 公开接口巡检补充

同日只读巡检主要公开接口，结果如下：

| 接口 | 状态 | 耗时 | 结论 |
|---|---:|---:|---|
| `/health` | 200 | 165 ms | 正常 |
| `/api/data/health` | 200 | 735 ms | 正常返回，整体 warning |
| `/api/stocks/search?q=600519` | 200 | 32 ms | 搜索正常，市场识别为 SH |
| `/api/quote/600519?frequency=daily&indicators=true` | 200 | 56 ms | 返回很快，但仍有 0 值 OHLC |
| `/api/etf/signals?days=20` | timeout | 20031 ms | ETF 信号接口仍会超时 |
| `/api/sectors/performance?days=10` | 200 | 3518 ms | 可返回，但偏慢 |
| `/api/pair/list` | 200 | 30 ms | 可返回，部分配对指标为空/数据不足 |
| `/api/index/performance?index=hs300` | 200 | 45 ms | 正常 |

后续判断：

- K 线 0 值问题已经有本地修复和定向数据修复脚本，等待服务器部署后验证。
- 因子分析 504 已有本地后台任务修复，等待服务器部署后验证。
- ETF 信号接口 `20s` 超时仍是独立遗留问题；本轮未把 ETF 信号计算改成后台任务或缓存，后续应单独优化。
- 板块表现接口可返回但约 `3.5s`，如页面体验仍卡顿，可后续做缓存或预计算。
