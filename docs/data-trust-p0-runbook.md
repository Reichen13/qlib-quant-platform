# P0 数据可信门禁与尾部复权修复 Runbook

## 背景

2026-07 增量更新曾把腾讯 fallback（`factor=1.0` / 前复权尺度）拼进历史后复权 bin，导致最新交易日假跳空。  
系统现已：

1. **默认禁止腾讯未对齐写入**（`update_cn_data.fetch`）
2. **扫描 / 修复 / 断言**脚本
3. **data_trust 门禁**：不可信时清空 buyable、拒绝股票池刷新与回测

## 一键流程

```bash
# 1) 扫描污染代码列表
python scripts/scan_tail_adjustment_splice.py --out ~/.qlib/cache/tail_splice_codes.txt

# 2) Baostock 覆盖修复（从 2024 起重写窗口）
python scripts/repair_tail_adjustment_splice.py --codes-file ~/.qlib/cache/tail_splice_codes.txt --start 2024-01-01

# 3) 断言（exit 0=可交易，exit 2=仍禁止）
python scripts/assert_data_trust.py --no-cache
```

小样本验证：

```bash
python update_cn_data.py --code sh600519 --start 2024-01-01 --rebuild-stale --overwrite-existing
```

验收：末日 `factor` 应 >1.01（有分红股），近 5 日无 ±30% 鬼跳，前复权价 ≈ 市价。

## API

| 接口 | 行为 |
|---|---|
| `GET /api/data/health` | 含 `sources.data_trust`；不可信时 `overall_status=degraded`，`trading_allowed=false` |
| `GET /api/data/trust?refresh=1` | 强制重算信任报告 |
| `POST /api/screening/run` | 不可信时清空 buyable，不落筛选买入历史 |
| `POST /api/stock-pool/{id}/refresh` | 默认 503 |
| `POST /api/backtest/run` | 默认 503；`allow_untrusted_data=true` 可强制 |
| `GET /api/dashboard/focus` | 不可信时 `buyable_top3=[]` |

## 环境变量

- `ALLOW_TENCENT_FALLBACK=1`：允许腾讯写入，但必须能与历史后复权尺度对齐，否则仍 skip。

## ICIR 选股

`backend/core/factor_scoring.py`：截面 z-score × **带符号** ICIR（禁止 `abs(icir)` 丢掉方向）。
