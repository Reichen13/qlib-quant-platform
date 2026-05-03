"""ETF 全量筛选器

从预置的A股主要ETF池（300+只）批量下载数据，
计算动量、夏普、回撤等指标，输出推荐排名。

运行：
    python etf_screener.py                    # 筛选全部ETF（约10分钟）
    python etf_screener.py --top 20           # 只显示前20名
    python etf_screener.py --fast             # 只用50只核心ETF（约1分钟）
    python etf_screener.py --out etf_rank.csv # 导出CSV
"""
import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── ETF 池 ──────────────────────────────────────────────────────────────
# 格式：{yfinance代码: 中文名称}
# 50只核心ETF（快速模式）
CORE_ETFS = {
    # 宽基
    "510300.SS": "沪深300ETF",
    "510500.SS": "中证500ETF",
    "159915.SZ": "创业板ETF",
    "510050.SS": "上证50ETF",
    "588000.SS": "科创50ETF",
    "159919.SZ": "沪深300ETF(嘉实)",
    "512100.SS": "中证1000ETF",
    "159902.SZ": "中证100ETF",
    "515780.SS": "中证800ETF",
    "510810.SS": "上证180ETF",
    # 科技/成长
    "159995.SZ": "芯片ETF",
    "515700.SS": "新能源ETF",
    "515030.SS": "新能源车ETF",
    "159740.SZ": "恒生科技ETF",
    "513050.SS": "中概互联ETF",
    "159509.SZ": "新兴成长ETF",
    "512480.SS": "半导体ETF",
    "159766.SZ": "人工智能ETF",
    "515880.SS": "通信ETF",
    "159801.SZ": "航天军工ETF",
    # 消费/医药
    "512010.SS": "医药ETF",
    "159929.SZ": "医疗ETF",
    "512690.SS": "酒ETF",
    "515170.SS": "消费ETF",
    "159928.SZ": "消费ETF(华宝)",
    "159996.SZ": "家电ETF",
    "515900.SS": "食品饮料ETF",
    "512760.SS": "芯片ETF(国联)",
    "159941.SZ": "纳指ETF",
    "513500.SS": "标普500ETF",
    # 金融/周期
    "512880.SS": "证券ETF",
    "512000.SS": "券商ETF",
    "159931.SZ": "银行ETF",
    "512400.SS": "有色金属ETF",
    "512660.SS": "军工ETF",
    "512200.SS": "房地产ETF",
    "159611.SZ": "煤炭ETF",
    "516160.SS": "新材料ETF",
    "561560.SS": "基建ETF",
    "159996.SZ": "家电ETF(华夏)",
    # 海外/跨市场
    "513100.SS": "纳指100ETF",
    "513520.SS": "日经ETF",
    "513060.SS": "恒生ETF",
    "513080.SS": "法国CAC40ETF",
    "159920.SZ": "恒生ETF(华夏)",
    "513330.SS": "恒生科技ETF",
    "513010.SS": "德国ETF",
    "513360.SS": "香港科技ETF",
    "159605.SZ": "原油ETF",
    "518880.SS": "黄金ETF",
}

# 全量ETF池（300+只，覆盖主要行业和主题）
FULL_ETFS = {
    **CORE_ETFS,
    # 更多行业ETF
    "515000.SS": "可选消费ETF",
    "512580.SS": "环保ETF",
    "159893.SZ": "互联网ETF",
    "516950.SS": "碳中和ETF",
    "562800.SS": "绿色电力ETF",
    "159869.SZ": "光伏ETF",
    "516510.SS": "光伏产业ETF",
    "516150.SS": "新能源50ETF",
    "159801.SZ": "航空航天ETF",
    "512980.SS": "传媒ETF",
    "512290.SS": "生物科技ETF",
    "159756.SZ": "机器人ETF",
    "562500.SS": "数字经济ETF",
    "516580.SS": "智能驾驶ETF",
    "159628.SZ": "云计算ETF",
    "516160.SS": "工业互联ETF",
    "159516.SZ": "数据要素ETF",
    "560080.SS": "央企ETF",
    "515900.SS": "中华红利ETF",
    "510810.SS": "上证行业龙头ETF",
    "516800.SS": "物流ETF",
    "516880.SS": "旅游ETF",
    "516830.SS": "畜牧养殖ETF",
    "516180.SS": "体育ETF",
    "159648.SZ": "跨境电商ETF",
    "516110.SS": "工程机械ETF",
    "516060.SS": "化工ETF",
    "516380.SS": "超导ETF",
    "560010.SS": "稀土ETF",
    "516200.SS": "有色金属ETF(华夏)",
    "159631.SZ": "铜ETF",
    "159618.SZ": "钢铁ETF",
    "159617.SZ": "煤炭ETF(国泰)",
    "516890.SS": "基础化工ETF",
    "563000.SS": "同业存单ETF",
    "511260.SS": "十年国债ETF",
    "511010.SS": "国债ETF",
    "511380.SS": "城投债ETF",
    "511880.SS": "银行间货币ETF",
}


def fetch_etf(code: str, start: str, end: str) -> pd.Series:
    """拉取单只ETF收盘价"""
    try:
        t = yf.Ticker(code)
        df = t.history(start=start, end=end, auto_adjust=True)
        if df.empty or len(df) < 20:
            return pd.Series(dtype=float)
        df.index = df.index.tz_localize(None)
        return df["Close"].rename(code)
    except Exception:
        return pd.Series(dtype=float)


def calc_metrics(price: pd.Series, benchmark: pd.Series = None) -> dict:
    """计算评分指标"""
    ret = price.pct_change().dropna()
    if len(ret) < 20:
        return {}

    # 动量
    total_ret = price.iloc[-1] / price.iloc[0] - 1
    ret_1m = price.iloc[-1] / price.iloc[-21] - 1 if len(price) >= 21 else np.nan
    ret_3m = price.iloc[-1] / price.iloc[-63] - 1 if len(price) >= 63 else np.nan
    ret_6m = price.iloc[-1] / price.iloc[-126] - 1 if len(price) >= 126 else np.nan

    # 风险指标
    ann_vol = ret.std() * np.sqrt(252)
    ann_ret = (1 + total_ret) ** (252 / max(len(ret), 1)) - 1
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    cum = (1 + ret).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

    # 趋势强度（在均线上方的比例）
    ma20 = price.rolling(20).mean()
    above_ma20 = (price > ma20).sum() / len(price)
    ma60 = price.rolling(60).mean()
    above_ma60 = (price > ma60).sum() / len(price) if len(price) >= 60 else np.nan

    # 相对强度（vs 沪深300）
    rel_strength = np.nan
    if benchmark is not None and len(benchmark) > 0:
        common = price.index.intersection(benchmark.index)
        if len(common) > 20:
            p = price.loc[common]
            b = benchmark.loc[common]
            rel = (p / p.iloc[0]) / (b / b.iloc[0])
            rel_strength = rel.iloc[-1] - 1  # 相对沪深300的超额

    return {
        "total_ret": round(total_ret, 4),
        "ret_1m": round(ret_1m, 4) if not np.isnan(ret_1m) else np.nan,
        "ret_3m": round(ret_3m, 4) if not np.isnan(ret_3m) else np.nan,
        "ret_6m": round(ret_6m, 4) if not np.isnan(ret_6m) else np.nan,
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 4),
        "calmar": round(calmar, 3),
        "above_ma20": round(above_ma20, 3),
        "above_ma60": round(above_ma60, 3) if not np.isnan(above_ma60) else np.nan,
        "rel_strength": round(rel_strength, 4) if not np.isnan(rel_strength) else np.nan,
        "data_points": len(price),
    }


def score_etf(m: dict) -> float:
    """综合评分（越高越好）"""
    if not m:
        return -999

    score = 0
    # 动量（权重50%）：近1月/3月/6月动量
    if not np.isnan(m.get("ret_1m", np.nan)):
        score += m["ret_1m"] * 20   # 近1月*20
    if not np.isnan(m.get("ret_3m", np.nan)):
        score += m["ret_3m"] * 10   # 近3月*10
    if not np.isnan(m.get("ret_6m", np.nan)):
        score += m["ret_6m"] * 5    # 近6月*5

    # 风险调整（权重30%）
    score += m["sharpe"] * 0.3
    score += m["calmar"] * 0.1

    # 趋势（权重20%）
    score += (m["above_ma20"] - 0.5) * 0.5
    if not np.isnan(m.get("above_ma60", np.nan)):
        score += (m["above_ma60"] - 0.5) * 0.3

    # 相对强度加分
    if not np.isnan(m.get("rel_strength", np.nan)):
        score += m["rel_strength"] * 3

    return round(score, 4)


def run_screener(
    fast: bool = False,
    lookback_days: int = 252,
    top_n: int = 20,
    output_path: str = None,
    delay: float = 0.3,
):
    etf_pool = CORE_ETFS if fast else FULL_ETFS
    end = pd.Timestamp.now().strftime("%Y-%m-%d")
    start = (pd.Timestamp.now() - pd.Timedelta(days=lookback_days + 10)).strftime("%Y-%m-%d")

    print(f"=== ETF 全量筛选 ===")
    print(f"ETF池: {len(etf_pool)} 只  {'[快速模式]' if fast else '[全量模式]'}")
    print(f"数据区间: {start} ~ {end}\n")

    # 先拉基准（沪深300）
    print("[0] 拉取沪深300基准...")
    bench = fetch_etf("510300.SS", start, end)
    print(f"    基准数据: {len(bench)} 个交易日\n")

    results = []
    fail_count = 0
    t0 = time.time()

    for i, (code, name) in enumerate(etf_pool.items()):
        price = fetch_etf(code, start, end)
        if price.empty:
            fail_count += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(etf_pool)}] 已处理 {i+1-fail_count} 只有效")
            time.sleep(delay)
            continue

        m = calc_metrics(price, bench)
        if not m:
            fail_count += 1
            time.sleep(delay)
            continue

        m["code"] = code
        m["name"] = name
        m["score"] = score_etf(m)
        results.append(m)

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            speed = (i + 1) / elapsed
            remain = (len(etf_pool) - i - 1) / speed if speed > 0 else 0
            print(f"  [{i+1}/{len(etf_pool)}] 有效:{len(results)} 失败:{fail_count} "
                  f"速度:{speed:.1f}/s 剩余:{remain:.0f}s")

        time.sleep(delay)

    if not results:
        print("无有效数据")
        return

    df = pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)
    df.index += 1  # 排名从1开始

    # 格式化输出
    print(f"\n{'='*70}")
    print(f"  ETF 综合评分排名 TOP {top_n}")
    print(f"  回看周期: {lookback_days}天  基准: 沪深300")
    print(f"{'='*70}")
    print(f"{'排名':<4} {'代码':<14} {'名称':<20} {'评分':<8} "
          f"{'1月':<8} {'3月':<8} {'6月':<8} {'Sharpe':<8} {'最大回撤':<10}")
    print("-" * 70)

    for rank, row in df.head(top_n).iterrows():
        ret1m = f"{row['ret_1m']:.1%}" if not np.isnan(row.get('ret_1m', np.nan)) else "N/A"
        ret3m = f"{row['ret_3m']:.1%}" if not np.isnan(row.get('ret_3m', np.nan)) else "N/A"
        ret6m = f"{row['ret_6m']:.1%}" if not np.isnan(row.get('ret_6m', np.nan)) else "N/A"
        print(f"{rank:<4} {row['code']:<14} {row['name'][:18]:<20} "
              f"{row['score']:<8.3f} {ret1m:<8} {ret3m:<8} {ret6m:<8} "
              f"{row['sharpe']:<8.3f} {row['max_dd']:.1%}")

    print(f"{'='*70}")
    print(f"\n共 {len(results)} 只有效 / {fail_count} 只无数据")
    print(f"耗时: {(time.time()-t0)/60:.1f} 分钟")

    if output_path:
        df.to_csv(output_path, encoding="utf-8-sig")
        print(f"已导出: {output_path}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股ETF全量筛选器")
    parser.add_argument("--fast",  action="store_true", help="快速模式（50只核心ETF，约1分钟）")
    parser.add_argument("--top",   type=int, default=20, help="显示前N名")
    parser.add_argument("--days",  type=int, default=252, help="回看天数（默认252=1年）")
    parser.add_argument("--out",   default=None, help="导出CSV路径")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔秒数（默认0.3）")
    args = parser.parse_args()

    run_screener(
        fast=args.fast,
        lookback_days=args.days,
        top_n=args.top,
        output_path=args.out,
        delay=args.delay,
    )
