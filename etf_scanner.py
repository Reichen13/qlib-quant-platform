"""A股ETF全量扫描器

逻辑：
1. 用 akshare 获取全量 ETF 列表（约900只）
2. 用 yfinance 拉取近期行情（限流时自动跳过）
3. 用量化指标打分：动量 + 趋势 + 量比 + 波动率
4. 输出排名前20的 ETF

适合在 VPS 上运行（akshare 直连无代理问题）
本地运行需要先解除代理或等 yfinance 限流解除

运行：
    python etf_scanner.py           # 完整扫描
    python etf_scanner.py --top 30  # 显示前30
    python etf_scanner.py --min-vol 5000  # 过滤成交量<5000万的小ETF
"""
import os
import sys
import time
import argparse
import pathlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def _get_etf_list_akshare() -> pd.DataFrame:
    """用 akshare 获取全量 ETF 列表（VPS 上运行）"""
    import akshare as ak
    for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(k, None)
    os.environ["no_proxy"] = "*"

    try:
        df = ak.fund_etf_spot_em()
        # 统一列名
        col_map = {"代码": "code", "名称": "name", "最新价": "price",
                   "涨跌幅": "pct_chg", "成交量": "volume", "成交额": "amount"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["code"] = df["code"].astype(str).str.zfill(6)
        print(f"  akshare 获取 ETF 列表: {len(df)} 只")
        return df
    except Exception as e:
        print(f"  akshare 失败: {e}")
        return pd.DataFrame()


def _get_etf_list_builtin() -> pd.DataFrame:
    """内置的主流 ETF 列表（本地无 akshare 时的备用）"""
    etfs = [
        # 宽基
        ("510300", "沪深300ETF"), ("510500", "中证500ETF"),
        ("159915", "创业板ETF"),  ("510050", "上证50ETF"),
        ("512100", "中证1000ETF"),("588000", "科创50ETF"),
        # 行业
        ("512880", "证券ETF"),    ("512010", "医药ETF"),
        ("515030", "新能源车ETF"),("512660", "军工ETF"),
        ("512400", "有色金属ETF"),("159995", "芯片ETF"),
        ("512200", "房地产ETF"),  ("515880", "通信ETF"),
        ("512690", "酒ETF"),      ("512170", "医疗ETF"),
        ("516160", "新能源ETF"),  ("516950", "碳中和ETF"),
        ("159869", "消费ETF"),    ("159740", "恒生ETF"),
        # 海外
        ("513500", "标普500ETF"), ("513100", "纳指ETF"),
        ("513050", "中概互联"),   ("159934", "黄金ETF"),
        ("518880", "黄金ETF2"),   ("512760", "半导体ETF"),
        ("159605", "港股通ETF"),  ("516180", "食品饮料"),
        ("516220", "煤炭ETF"),    ("159766", "旅游ETF"),
    ]
    df = pd.DataFrame(etfs, columns=["code", "name"])
    print(f"  使用内置 ETF 列表: {len(df)} 只")
    return df


def _fetch_history(code: str, days: int = 60) -> pd.DataFrame:
    """拉取单只 ETF 历史数据"""
    import yfinance as yf

    # 转换代码格式
    if code.startswith("5"):
        yf_code = f"{code}.SS"
    elif code.startswith("1"):
        yf_code = f"{code}.SZ"
    else:
        yf_code = f"{code}.SS"

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")

    try:
        t = yf.Ticker(yf_code)
        df = t.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        df = df.rename(columns={"Open": "open", "High": "high",
                                 "Low": "low", "Close": "close", "Volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]].astype(float)
    except Exception:
        return pd.DataFrame()


def _score_etf(code: str, name: str, df: pd.DataFrame,
               min_vol: float = 1000) -> dict | None:
    """对单只 ETF 打量化综合分"""
    if df.empty or len(df) < 20:
        return None

    close = df["close"]
    volume = df["volume"]

    # 成交量过滤（万元）
    avg_amount = close.iloc[-5:].mean() * volume.iloc[-5:].mean() / 10000
    if avg_amount < min_vol:
        return None  # 流动性不足

    # ── 动量因子 ──
    mom5  = (close.iloc[-1] / close.iloc[-5]  - 1) * 100 if len(df) >= 5  else 0
    mom10 = (close.iloc[-1] / close.iloc[-10] - 1) * 100 if len(df) >= 10 else 0
    mom20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(df) >= 20 else 0

    # ── 趋势因子（均线多头排列）──
    ma5  = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    price = close.iloc[-1]

    trend_score = 0
    if price > ma5:   trend_score += 1
    if price > ma10:  trend_score += 1
    if price > ma20:  trend_score += 1
    if ma5 > ma10:    trend_score += 1
    if ma10 > ma20:   trend_score += 1
    trend_pct = trend_score / 5  # 0-1

    # ── 量比（近5日均量 / 近20日均量）──
    vol_ratio = volume.iloc[-5:].mean() / volume.iloc[-20:].mean()
    vol_score = min(vol_ratio / 2, 1.0)  # 量比>2才满分

    # ── RSI ──
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = (100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1]

    # RSI 在 40-70 区间得分高（不超买不超卖）
    if 40 <= rsi <= 70:
        rsi_score = 1.0
    elif 30 <= rsi < 40 or 70 < rsi <= 80:
        rsi_score = 0.6
    else:
        rsi_score = 0.2

    # ── 波动率（越低越稳健）──
    vol_20d = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)
    vol_penalty = max(0, 1 - vol_20d / 0.5)  # 年化50%波动率以上开始扣分

    # ── 综合评分 ──
    # 动量(35%) + 趋势(30%) + 量比(20%) + RSI(15%)，再乘波动率惩罚
    norm_mom = np.clip((mom20 + 10) / 20, 0, 1)  # -10%~+10% 映射到 0~1
    final = (norm_mom * 0.35 + trend_pct * 0.30 +
             vol_score * 0.20 + rsi_score * 0.15) * vol_penalty

    return {
        "code": code,
        "name": name,
        "price": round(price, 3),
        "score": round(final, 4),
        "mom5":  round(mom5, 2),
        "mom10": round(mom10, 2),
        "mom20": round(mom20, 2),
        "trend": f"{trend_score}/5",
        "vol_ratio": round(vol_ratio, 2),
        "rsi": round(rsi, 1),
        "vol_20d": round(vol_20d * 100, 1),
        "avg_amount_万": round(avg_amount, 0),
        "signal": "买入" if final > 0.65 else ("关注" if final > 0.45 else "回避"),
    }


def scan(top_n: int = 20, min_vol: float = 1000, use_builtin: bool = False):
    """主扫描流程"""
    print("=" * 60)
    print(f"  A股ETF全量扫描  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. 获取 ETF 列表
    print("\n[1] 获取 ETF 列表...")
    if use_builtin:
        etf_df = _get_etf_list_builtin()
    else:
        etf_df = _get_etf_list_akshare()
        if etf_df.empty:
            print("  akshare 不可用，改用内置列表")
            etf_df = _get_etf_list_builtin()

    total = len(etf_df)
    print(f"  待扫描: {total} 只")

    # 2. 批量拉取并打分
    print(f"\n[2] 批量分析（预计 {total * 0.5 / 60:.0f} 分钟）...")
    results = []
    fail = skip = 0

    for i, row in etf_df.iterrows():
        code = str(row.get("code", row.get(0, ""))).zfill(6)
        name = row.get("name", row.get(1, code))

        df = _fetch_history(code, days=60)
        if df.empty:
            fail += 1
        else:
            scored = _score_etf(code, name, df, min_vol=min_vol)
            if scored:
                results.append(scored)
            else:
                skip += 1

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{total}] 有效:{len(results)} 跳过:{skip} 失败:{fail}")

        time.sleep(0.3)

    # 3. 排名输出
    if not results:
        print("\n无有效数据，请检查网络或等待限流解除")
        return

    df_result = pd.DataFrame(results).sort_values("score", ascending=False)

    print(f"\n{'='*60}")
    print(f"  ETF 量化排名 TOP{top_n}  （成交额 >{min_vol:.0f}万）")
    print(f"{'='*60}")
    print(f"{'排名':<4} {'代码':<8} {'名称':<14} {'评分':>6} {'20日%':>7} "
          f"{'趋势':>6} {'量比':>6} {'RSI':>5} {'信号':>6}")
    print("-" * 65)

    for rank, (_, row) in enumerate(df_result.head(top_n).iterrows(), 1):
        sig_icon = "🟢" if row["signal"] == "买入" else ("🟡" if row["signal"] == "关注" else "🔴")
        print(f"{rank:<4} {row['code']:<8} {row['name']:<14} "
              f"{row['score']:>6.3f} {row['mom20']:>+7.1f}% "
              f"{row['trend']:>6} {row['vol_ratio']:>6.2f} "
              f"{row['rsi']:>5.1f} {sig_icon}{row['signal']}")

    # 保存结果
    out_path = pathlib.Path(__file__).parent / "etf_scan_result.csv"
    df_result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n完整结果已保存: {out_path}")
    print(f"共扫描 {total} 只，有效 {len(results)} 只，"
          f"跳过(流动性不足) {skip} 只，失败 {fail} 只")

    return df_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股ETF全量量化扫描器")
    parser.add_argument("--top",     type=int,   default=20,   help="显示前N名")
    parser.add_argument("--min-vol", type=float, default=1000, help="最低日均成交额（万元）")
    parser.add_argument("--builtin", action="store_true",      help="使用内置ETF列表（不调akshare）")
    args = parser.parse_args()

    scan(top_n=args.top, min_vol=args.min_vol, use_builtin=args.builtin)
