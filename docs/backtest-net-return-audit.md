# 阶段 2 回测口径修正 — 验收存档

## 修改内容

### 阶段 2-1: 净收益替代毛收益
- `report["return"] - report["cost"]` → `r_net` 作为策略真实收益
- 所有指标（胜率/夏普/Calmar/Sortino/IR/t-test/月度胜率）改用 `r_net` 计算
- 毛收益和净收益两条净值曲线同时输出（`equity` + `net_equity`）

### 阶段 2-2: sell_cost 默认 0.0008
- 佣金万2.5 + 印花税 0.05% + 过户费 ≈ 万8
- buy_cost 保持 0.0003（万2.5 + 过户费）

### 阶段 2-3: 账户资金参数化
- `BacktestParams.account` 新增参数，默认 300_000
- `backtest_daily` 中 `account=params.account` 替代硬编码 `1_000_000`

### 阶段 2-4: limit_threshold 分板
- 沪深300/中证500（主板为主）: 0.099（±10%）
- 全市场/含科创板创业板: 0.195（±20% 宽松）

### 阶段 2-5: volume_threshold + impact_cost
- 已恢复启用（commit 9b77cbb）
- hang 的真相：Windows spawn 多进程 + if __name__ 缺失导致内存打满，非 Qlib exchange 参数问题
- 回测端到端跑通：2025H1 毛收益 11.24% / 净收益 8.01%

### 阶段 2-6: turnover/stop_loss/max_position
- turnover: Qlib TopkDropoutStrategy 不支持调仓周期，标注为"暂未接入"
- stop_loss/max_position: 从 schema 删除（commit 9b77cbb），TopkDropoutStrategy 不原生支持日频止损
- 日频止损需在持仓管理层面实现，登记为 backlog

## 模拟验证

用模拟数据验证净收益 vs 毛收益的差异（`py -3.12` 可复现）：

| 指标 | 毛收益 | 净收益(扣费后) |
|------|--------|----------------|
| 总收益 | +12.55% | **-8.62%** |
| 年化 | +14.03% | -6.00% |
| 夏普 | 0.61 | -0.26 |
| 累计成本 | — | 0.2083（约21个基点/天） |

## 未验证项

1. **完整回测端到端测试**：Qlib 0.9.7 的 `backtest_daily` 在本地数据上长时间挂起（>5min 无响应）
2. **SH000300 benchmark 缺失**：baostock 单源重建后 benchmark 索引可能失效，需单独调查
3. **前端净收益曲线可视化**：代码已就绪（`net_equity` 产生 + AreaChart 渲染），待回测跑通后验证

## 已知限制

- Qlib 0.9.7 不支持 `volume_threshold` 和 `impact_cost` 参数（会导致 hang）
- TopkDropoutStrategy 不支持调仓周期控制（`turnover` 参数无法接入）
- 分板涨跌停无法用 tuple 表达式（Qlib 0.9.7 exchange 限制），使用 universe 近似

## 修改文件

- `backend/models/schemas.py`: BacktestParams + BacktestResponse
- `backend/api/backtest.py`: 核心改动
- `frontend/src/lib/api.ts`: BacktestResult 类型
- `frontend/src/pages/backtest/index.tsx`: 净值曲线 + 净收益展示
