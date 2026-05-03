"""Qlib Alpha158 + LightGBM 基准回测（修复版）"""
import warnings, qlib
warnings.filterwarnings("ignore")
from qlib.config import REG_CN
from qlib.utils import init_instance_by_config
from qlib.contrib.strategy import TopkDropoutStrategy
from qlib.contrib.evaluate import backtest_daily, risk_analysis
import pandas as pd

qlib.init(provider_uri='~/.qlib/qlib_data/cn_data', region=REG_CN)

print("=" * 60)
print("  Qlib Alpha158 + LightGBM 基准回测")
print("=" * 60)

# ── 数据集 ──
dataset = init_instance_by_config({
    "class": "DatasetH",
    "module_path": "qlib.data.dataset",
    "kwargs": {
        "handler": {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": "2008-01-01", "end_time": "2020-09-01",
                "fit_start_time": "2008-01-01", "fit_end_time": "2017-12-31",
                "instruments": "csi300",
            },
        },
        "segments": {
            "train": ("2008-01-01", "2016-12-31"),
            "valid": ("2017-01-01", "2018-12-31"),
            "test":  ("2019-01-01", "2020-09-01"),
        },
    },
})
print("\n[1] Alpha158 数据集构建完成（CSI300, 2008-2020）")

# ── 模型 ──
model = init_instance_by_config({
    "class": "LGBModel",
    "module_path": "qlib.contrib.model.gbdt",
    "kwargs": {
        "loss": "mse", "colsample_bytree": 0.8879,
        "learning_rate": 0.2, "subsample": 0.8789,
        "lambda_l1": 205.6999, "lambda_l2": 580.9768,
        "max_depth": 8, "num_leaves": 210, "num_threads": 4,
    }
})
print("\n[2] 训练 LightGBM...")
model.fit(dataset)
pred = model.predict(dataset)
print(f"    预测条数: {len(pred)}")

# ── IC 分析 ──
print("\n[3] IC 分析...")
test_data = dataset.prepare("test", col_set=["feature", "label"])
if isinstance(test_data, tuple):
    test_x, test_y = test_data
else:
    test_y = test_data["label"]

# 手动计算 IC（Pearson + Spearman）
from scipy import stats
import numpy as np

pred_test = pred  # 只保留测试集
label_test = test_y.squeeze()

# 对齐索引
common_idx = pred_test.index.intersection(label_test.index)
p = pred_test.loc[common_idx]
l = label_test.loc[common_idx]

# 按日期计算截面 IC
ic_list = []
ric_list = []  # Rank IC
for date, grp in p.groupby(level="datetime"):
    if date not in l.index.get_level_values("datetime"):
        continue
    l_date = l.xs(date, level="datetime")
    p_date = grp.xs(date, level="datetime") if "datetime" in grp.index.names else grp
    common = p_date.index.intersection(l_date.index)
    if len(common) < 10:
        continue
    pv = p_date.loc[common].values
    lv = l_date.loc[common].values
    ic, _ = stats.pearsonr(pv, lv)
    ric, _ = stats.spearmanr(pv, lv)
    ic_list.append(ic)
    ric_list.append(ric)

ic_arr = np.array(ic_list)
ric_arr = np.array(ric_list)
print(f"    IC 均值:   {ic_arr.mean():.4f}")
print(f"    IC Std:    {ic_arr.std():.4f}")
print(f"    ICIR:      {ic_arr.mean()/ic_arr.std():.4f}")
print(f"    Rank IC:   {ric_arr.mean():.4f}")
print(f"    IC > 0:    {(ic_arr>0).mean():.1%}")

# ── 回测（含交易成本）──
print("\n[4] 回测 (TopkDropout k=50, 含交易成本)...")
strategy = TopkDropoutStrategy(topk=50, n_drop=5, signal=pred)

port_analysis_config = {
    "executor": {
        "class": "SimulatorExecutor",
        "module_path": "qlib.backtest.executor",
        "kwargs": {"time_per_step": "day", "generate_portfolio_metrics": True},
    },
    "backtest": {
        "start_time": "2019-01-01", "end_time": "2020-09-01",
        "account": 1_000_000, "benchmark": "SH000300",
        "exchange_kwargs": {
            "codes": "csi300", "freq": "day",
            "limit_threshold": 0.095,
            "deal_price": "close",
            "open_cost": 0.0005,   # 佣金 0.05%
            "close_cost": 0.0015,  # 佣金 + 印花税 0.15%
            "min_cost": 5,
        },
    },
}

report, _ = backtest_daily(
    start_time="2019-01-01", end_time="2020-09-01",
    strategy=strategy,
    executor=port_analysis_config["executor"],
    account=1_000_000, benchmark="SH000300",
    exchange_kwargs=port_analysis_config["backtest"]["exchange_kwargs"],
)

# ── 风险指标 ──
print("\n[5] 超额收益（相对沪深300）:")
excess = report["return"] - report["bench"]
ra = risk_analysis(excess)
print(ra.to_string())

print("\n[6] 策略绝对收益:")
ra2 = risk_analysis(report["return"])
print(ra2.to_string())

# ── 汇总对比 ──
print("\n" + "=" * 60)
print("  与当前 a-stock-quant v6.0 对比")
print("=" * 60)
print(f"{'指标':<20} {'Qlib Alpha158':>15} {'当前系统':>15}")
print("-" * 52)

# 计算 Qlib 实际指标
r = report["return"]
bench = report["bench"]
ex = r - bench
ann_r = r.mean() * 252
ann_std = r.std() * np.sqrt(252)
sharpe = ann_r / ann_std if ann_std > 0 else 0
cum = (1 + r).cumprod()
dd = (cum / cum.cummax() - 1).min()
wr = (r > 0).mean()

ann_ex = ex.mean() * 252
ex_std = ex.std() * np.sqrt(252)
ir = ann_ex / ex_std if ex_std > 0 else 0

print(f"{'IC (测试集)':<20} {ic_arr.mean():>14.4f} {'0.093':>15}")
print(f"{'ICIR':<20} {ic_arr.mean()/ic_arr.std():>14.4f} {'N/A':>15}")
print(f"{'Rank IC':<20} {ric_arr.mean():>14.4f} {'N/A':>15}")
print(f"{'年化收益':<20} {ann_r:>14.1%} {'21.2%':>15}")
print(f"{'年化波动':<20} {ann_std:>14.1%} {'N/A':>15}")
print(f"{'Sharpe（含成本）':<20} {sharpe:>14.3f} {'0.55（无成本）':>15}")
print(f"{'最大回撤':<20} {dd:>14.1%} {'-16.9%':>15}")
print(f"{'胜率':<20} {wr:>14.1%} {'55.9%':>15}")
print(f"{'信息比率(IR)':<20} {ir:>14.3f} {'N/A':>15}")
print(f"{'交易成本':<20} {'25bps/次':>15} {'0（未建模）':>15}")
print("=" * 60)
print("\n注意：当前系统指标未含交易成本，Qlib 含 25bps/次成本")

report.to_csv("/home/jason/projects/qlib-workspace/backtest_report.csv")
print("详细报告已保存至 backtest_report.csv")
