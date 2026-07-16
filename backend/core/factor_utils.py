"""
因子分析工具模块
提供因子中性化、增强 IC 统计、行业加权 IC 分解等功能
从 AlphaPurify 方法论提炼，基于 pandas/numpy/scipy 实现
"""

import pandas as pd
import numpy as np
from scipy.stats import spearmanr, skew, kurtosis
from scipy import stats as scipy_stats
from loguru import logger

# 模块级行业映射缓存
_industry_cache: dict = {}


def load_industry_mapping(instruments: list[str]) -> dict[str, str]:
    """
    ? akshare ?????????? Qlib ????????? Baostock ???????

    ??????????????? {qlib_code: industry} ?????????
    ???????????? {qlib_code: industry_name}??????? "??"?
    """
    global _industry_cache

    cache_key = ",".join(sorted(instruments))
    if cache_key in _industry_cache:
        return _industry_cache[cache_key]

    logger.info(f"??????(akshare): {len(instruments)} ???")
    result = {inst: "??" for inst in instruments}
    wanted = set(instruments)
    found = {}

    # 1. ??????
    from pathlib import Path as _P
    import json as _json
    cache_file = _P.home() / ".qlib" / "industry_mapping_cache.json"
    if cache_file.exists():
        try:
            cached = _json.loads(cache_file.read_text(encoding="utf-8"))
            for code in wanted:
                if code in cached:
                    found[code] = cached[code]
            logger.info(f"??????????: {len(found)}/{len(wanted)}")
        except Exception:
            pass

    # 2. ?????? akshare ????????
    if len(found) < len(wanted):
        try:
            import akshare as ak
            import time as _time

            def _ak_retry(fn, *args, retries=3, **kw):
                last = None
                for _ in range(retries):
                    try:
                        return fn(*args, **kw)
                    except Exception as e:
                        last = e
                        _time.sleep(1.5)
                raise last

            boards = _ak_retry(ak.stock_board_industry_name_em)

            for _, row in boards.iterrows():
                industry = str(row.get("????") or "").strip()
                if not industry:
                    continue
                try:
                    cons = _ak_retry(ak.stock_board_industry_cons_em, symbol=industry)
                    for _, crow in cons.iterrows():
                        raw_code = str(crow.get("??") or "").strip()
                        if not raw_code:
                            continue
                        if raw_code.startswith(("60", "68", "51", "50", "56", "58")):
                            qlib_code = "SH" + raw_code
                        elif raw_code.startswith(("00", "30", "15", "16")):
                            qlib_code = "SZ" + raw_code
                        elif raw_code.startswith(("43", "83", "87", "92", "88")):
                            qlib_code = "BJ" + raw_code
                        else:
                            qlib_code = raw_code
                        if qlib_code in wanted:
                            found[qlib_code] = industry
                except Exception:
                    continue
                if len(found) >= len(wanted):
                    break

            # ?????
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(_json.dumps(found, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"????????(akshare): {e}")

    result.update(found)
    valid = sum(1 for v in result.values() if v != "??")
    logger.info(f"??????(akshare): {valid}/{len(instruments)} ?????")

    _industry_cache[cache_key] = result
    return result

def _load_market_cap(
    instruments: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, float]]:
    """
    从 Baostock 获取股票每日总市值。

    返回: {qlib_code: {date_str: market_cap_float}}
    例: {"SH600519": {"2025-01-02": 2.5e12, ...}}
    """
    result: dict[str, dict[str, float]] = {}

    try:
        import baostock as bs

        lg = bs.login()
        if lg.error_code != "0":
            logger.warning(f"Baostock 登录失败，市值数据不可用: {lg.error_msg}")
            return result

        loaded = 0
        for qlib_code in instruments:
            try:
                market = qlib_code[:2].lower()
                code_num = qlib_code[2:]
                bs_code = f"{market}.{code_num}"

                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,total_mv",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="2",  # 前复权
                )
                if rs.error_code != "0":
                    continue

                mc_dict = {}
                while rs.next():
                    row = rs.get_row_data()
                    date_str = row[0]
                    try:
                        mc_dict[date_str] = float(row[1]) if row[1] else None
                    except (ValueError, TypeError):
                        mc_dict[date_str] = None

                # 过滤非交易日
                result[qlib_code] = {k: v for k, v in mc_dict.items() if v is not None and v > 0}
                if result[qlib_code]:
                    loaded += 1
            except Exception:
                continue

        bs.logout()
        logger.info(f"市值数据加载完成: {loaded}/{len(instruments)} 只有效")

    except ImportError:
        logger.warning("baostock 未安装，市值数据不可用")
    except Exception as e:
        logger.warning(f"市值数据加载失败: {e}")

    return result


def neutralize_factor(
    factor_values: pd.Series,
    industry_map: dict[str, str],
    method: str = "industry",
    market_cap_data: dict | None = None,
) -> pd.Series:
    """
    截面 OLS 中性化。

    逐日期对因子值做：factor = X @ beta + residual，返回 residual

    参数:
        factor_values: MultiIndex (instrument, datetime) 的 Series
        industry_map: {instrument: industry_name}
        method: "industry" (行业回归), "market_cap" (log市值回归),
                "industry+market_cap" (行业+市值联合回归)
        market_cap_data: 可选预加载市值 {code: {date: mcap}}，避免每个因子重复打 Baostock
    返回:
        同 index 的中性化 Series
    """
    if factor_values.empty:
        return factor_values

    # 确保 index 有名称
    if factor_values.index.names[0] is None:
        factor_values.index.names = ["instrument", "datetime"]

    # 如果需要市值中性化，优先用调用方预加载的数据
    if "market_cap" in method:
        if market_cap_data is None:
            dates = factor_values.index.get_level_values("datetime").unique()
            instruments = factor_values.index.get_level_values("instrument").unique().tolist()
            start = str(dates.min())[:10]
            end = str(dates.max())[:10]
            market_cap_data = _load_market_cap(instruments, start, end)
        if not market_cap_data:
            logger.warning("市值数据不可用，回退为行业中性化")
            if method == "market_cap":
                return factor_values  # 无法中性化
            method = "industry"

    dates = factor_values.index.get_level_values("datetime").unique()
    neutralized_parts = []

    skipped_dates = 0
    processed_dates = 0

    for dt in dates:
        try:
            cross = factor_values.xs(dt, level="datetime").dropna()
            if len(cross) < 10:
                skipped_dates += 1
                continue

            # 构建解释变量列表
            X_cols = {}

            if method in ("industry", "industry+market_cap"):
                # 为每只股票获取行业
                industries = pd.Series(
                    {code: industry_map.get(code, "未知") for code in cross.index},
                    name="industry",
                )
                valid_mask = industries != "未知"
                if method == "industry" and valid_mask.sum() < 10:
                    skipped_dates += 1
                    continue

                if valid_mask.sum() >= 5:
                    ind_valid = industries[valid_mask]
                    unique_inds = ind_valid.unique()
                    if len(unique_inds) >= 2:
                        ind_dummies = pd.get_dummies(ind_valid, drop_first=True, dtype=float)
                        for col in ind_dummies.columns:
                            X_cols[f"ind_{col}"] = ind_dummies[col].reindex(cross.index).fillna(0).values
                    else:
                        # 单一行业，不做行业哑变量
                        pass

            if method in ("market_cap", "industry+market_cap"):
                # 获取当日市值
                dt_str = str(dt)[:10]
                mc_series = pd.Series(index=cross.index, dtype=float)
                for code in cross.index:
                    mc = market_cap_data.get(code, {}).get(dt_str) if market_cap_data else None
                    mc_series[code] = mc

                mc_valid = mc_series.dropna()
                if len(mc_valid) >= 10:
                    log_mc = np.log(mc_valid.clip(lower=1e8))  # 防零值
                    X_cols["log_mcap"] = log_mc.reindex(cross.index).fillna(log_mc.median()).values
                elif method == "market_cap":
                    skipped_dates += 1
                    continue

            if not X_cols:
                skipped_dates += 1
                continue

            # 构建设计矩阵
            X_df = pd.DataFrame(X_cols, index=cross.index)
            X_df["const"] = 1.0

            # 对齐样本
            common_idx = X_df.dropna().index
            if len(common_idx) < 10:
                skipped_dates += 1
                continue

            X = X_df.loc[common_idx].values
            y = cross.loc[common_idx].values

            # OLS
            beta, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
            y_pred = X @ beta
            residual_values = y - y_pred

            neutralized = pd.Series(
                residual_values,
                index=pd.MultiIndex.from_arrays(
                    [common_idx, [dt] * len(common_idx)],
                    names=["instrument", "datetime"],
                ),
                name=factor_values.name,
            )
            neutralized_parts.append(neutralized)
            processed_dates += 1

        except Exception as e:
            logger.debug(f"中性化日期 {dt} 失败: {e}")
            skipped_dates += 1
            continue

    if not neutralized_parts:
        logger.warning("中性化: 所有日期都失败，返回原始因子值")
        return factor_values

    result = pd.concat(neutralized_parts)
    result = result.sort_index()
    logger.info(
        f"中性化完成 [{method}]: {processed_dates} 日期成功, {skipped_dates} 日期跳过, "
        f"输出 {len(result)} 条记录"
    )
    return result


def compute_enhanced_ic_stats(daily_ics: list[float]) -> dict:
    """
    从每日 IC 序列计算增强统计指标。

    返回:
        skewness: IC 偏度
        kurtosis: IC 超额峰度 (fisher=True)
        t_statistic: 单样本 t 检验统计量 (H0: mean=0)
        p_value: t 检验 p 值
        information_ratio: mean_ic / std_ic
        ic_autocorr: lag-1 IC 自相关 (Spearman)
    """
    result = {
        "skewness": None,
        "kurtosis": None,
        "t_statistic": None,
        "p_value": None,
        "information_ratio": None,
        "ic_autocorr": None,
    }

    if not daily_ics or len(daily_ics) < 3:
        return result

    arr = np.array(daily_ics, dtype=float)
    arr = arr[np.isfinite(arr)]

    if len(arr) < 3:
        return result

    try:
        result["skewness"] = round(float(skew(arr)), 4)
        result["kurtosis"] = round(float(kurtosis(arr, fisher=True)), 4)

        t_stat, p_val = scipy_stats.ttest_1samp(arr, 0.0)
        result["t_statistic"] = round(float(t_stat), 4)
        result["p_value"] = round(float(p_val), 4)

        mean_ic = np.mean(arr)
        std_ic = np.std(arr, ddof=1)
        result["information_ratio"] = round(float(mean_ic / std_ic), 4) if std_ic > 0 else 0.0

        # lag-1 IC 自相关 (Spearman)
        if len(arr) >= 5:
            ac, _ = spearmanr(arr[:-1], arr[1:])
            result["ic_autocorr"] = round(float(ac), 4) if not np.isnan(ac) else None
    except Exception as e:
        logger.debug(f"增强统计计算失败: {e}")

    return result


def compute_industry_weighted_ic(
    factor_values: pd.Series,
    future_returns: pd.Series,
    industry_map: dict[str, str],
) -> dict[str, float]:
    """
    行业加权 IC 分解。

    对每个 (date, industry) 子组计算 Spearman IC，
    按组内股票数加权，返回时间序列均值的加权贡献。

    返回:
        {industry_name: weighted_contribution}，按 |贡献| 降序
    """
    if factor_values.empty or future_returns.empty:
        return {}

    # 对齐 index
    if factor_values.index.names[0] is None:
        factor_values.index.names = ["instrument", "datetime"]
    if future_returns.index.names[0] is None:
        future_returns.index.names = ["instrument", "datetime"]

    dates = sorted(factor_values.index.get_level_values("datetime").unique())
    industry_contribs: dict[str, list[float]] = {}

    for dt in dates:
        try:
            fv = factor_values.xs(dt, level="datetime").dropna()
            fr = future_returns.xs(dt, level="datetime").dropna()
            common = fv.index.intersection(fr.index)
            if len(common) < 15:
                continue

            # 给每个股票分配行业
            industries = pd.Series({c: industry_map.get(c, "未知") for c in common})
            valid = industries != "未知"
            if valid.sum() < 15:
                continue

            common_valid = common[valid]

            # 按行业分组计算 IC
            for ind in industries[valid].unique():
                ind_stocks = common_valid[industries[valid] == ind]
                if len(ind_stocks) < 5:
                    continue

                fv_ind = fv[ind_stocks].values
                fr_ind = fr[ind_stocks].values
                valid_vals = np.isfinite(fv_ind) & np.isfinite(fr_ind)
                if valid_vals.sum() < 5:
                    continue

                ic, _ = spearmanr(fv_ind[valid_vals], fr_ind[valid_vals])
                if not np.isnan(ic):
                    # 权重 = 行业股票数 / 总股票数
                    weight = len(ind_stocks) / len(common_valid)
                    contrib = ic * weight

                    if ind not in industry_contribs:
                        industry_contribs[ind] = []
                    industry_contribs[ind].append(contrib)

        except Exception:
            continue

    # 时间序列均值
    result = {}
    for ind, contribs in industry_contribs.items():
        if contribs:
            result[ind] = round(float(np.mean(contribs)), 4)

    # 按绝对值排序
    return dict(sorted(result.items(), key=lambda x: abs(x[1]), reverse=True))


def cluster_factors_by_ic(
    daily_ics: dict[str, list[float]],
    icir_map: dict[str, float],
    threshold: float = 0.7,
) -> dict:
    """
    基于 IC 相关性的层次聚类因子降维。

    参数:
        daily_ics: {factor_name: [daily_ic_values]}
        icir_map: {factor_name: icir}
        threshold: 相关性阈值 (默认 0.7)

    返回:
        {
            "n_original": 158,
            "n_effective": 42,
            "reduction_pct": 73.4,
            "clusters": [
                {"representative": "KMID", "members": ["KMID", "KMID2"], "icir": 0.85},
                ...
            ]
        }
    """
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform

    factor_names = list(daily_ics.keys())
    n = len(factor_names)
    if n < 3:
        return {"n_original": n, "n_effective": n, "reduction_pct": 0.0, "clusters": []}

    # 构建 IC 相关性矩阵
    ic_df = pd.DataFrame(daily_ics).dropna()
    if ic_df.shape[0] < 20:
        return {"n_original": n, "n_effective": n, "reduction_pct": 0.0, "clusters": []}

    corr = ic_df.corr(method="spearman").fillna(0)

    # 层次聚类 (average linkage, 基于 1-correlation 距离)
    dist = 1 - corr.abs()
    np.fill_diagonal(dist.values, 0)
    condensed = squareform(dist.values)
    Z = linkage(condensed, method="average")

    # 在给定阈值处切分
    labels = fcluster(Z, t=1 - threshold, criterion="distance")

    # 每簇保留 ICIR 最高的因子
    cluster_map = {}
    for i, label in enumerate(labels):
        fname = factor_names[i]
        if label not in cluster_map:
            cluster_map[label] = []
        cluster_map[label].append(fname)

    clusters = []
    for label, members in cluster_map.items():
        best = max(members, key=lambda f: abs(icir_map.get(f, 0)))
        clusters.append({
            "representative": best,
            "members": sorted(members),
            "icir": round(icir_map.get(best, 0), 2),
        })

    # 按 ICIR 降序
    clusters.sort(key=lambda c: abs(c["icir"]), reverse=True)

    n_effective = len(clusters)

    logger.info(
        f"因子聚类完成: {n} → {n_effective} 独立因子 "
        f"(阈值={threshold}, 缩减率={(1 - n_effective/n)*100:.1f}%)"
    )

    return {
        "n_original": n,
        "n_effective": n_effective,
        "reduction_pct": round((1 - n_effective / n) * 100, 1),
        "clusters": clusters,
    }
