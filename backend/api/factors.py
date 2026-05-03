"""
因子分析 API - 完整 Alpha158 因子体系 (Qlib 原生)
"""

import os
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import FactorAnalysisRequest, FactorAnalysisResponse, FactorIC

router = APIRouter()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ['NUMBA_NUM_THREADS'] = '1'
os.environ['QLIB_NO_MULTI_PROCESS'] = '1'


def _fix_parallel():
    try:
        from qlib.utils.paral import ParallelExt
        from joblib._parallel_backends import MultiprocessingBackend

        def _new_init(self, *args, **kwargs):
            maxtasksperchild = kwargs.pop("maxtasksperchild", None)
            super(ParallelExt, self).__init__(*args, **kwargs)
            ba = getattr(self, '_backend_kwargs', getattr(self, '_backend_args', None))
            if ba is not None and isinstance(self._backend, MultiprocessingBackend):
                ba["maxtasksperchild"] = maxtasksperchild

        ParallelExt.__init__ = _new_init
    except Exception:
        pass


@router.post("/analyze")
async def analyze_factors(params: FactorAnalysisRequest):
    """
    因子 IC 分析 - 完整 Alpha158 因子 (Qlib 原生)

    使用 Qlib 的 Alpha158 handler 生成全部 158 个因子，
    然后计算每个因子的 Spearman Rank IC 和 ICIR。
    """
    try:
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        qlib.config.N_PROC = 1
        _fix_parallel()

        start_str = str(params.start_date)
        end_str = str(params.end_date)
        pred_period = params.predict_period

        logger.info(f"Alpha158 因子分析: {start_str}~{end_str}, 预测期={pred_period}天")

        # ── 1. 使用 Qlib 原生 Alpha158 handler 生成全部 158 个因子 ──
        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": start_str,
                        "end_time": end_str,
                        "fit_start_time": start_str,
                        "fit_end_time": end_str,
                        "instruments": "csi300",
                    },
                },
                "segments": {
                    "test": (start_str, end_str),
                },
            },
        })

        logger.info("Alpha158 数据集构建完成")

        # ── 2. 获取特征数据 ──
        # dataset prepares features internally; we get them from the handler
        df_features = dataset.prepare("test", col_set="feature")

        # 如果 prepare 不可用，直接从 handler 获取
        if df_features is None or (hasattr(df_features, 'empty') and df_features.empty):
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")

        if df_features is None or df_features.empty:
            raise HTTPException(status_code=500, detail="Alpha158 因子数据为空")

        logger.info(f"特征数据: {df_features.shape}, 列数: {len(df_features.columns)}")

        # ── 3. 获取收盘价计算前向收益 ──
        stock_codes = df_features.index.get_level_values("instrument").unique().tolist()[:80]
        raw_df = D.features(stock_codes, ["$close"], start_time=start_str, end_time=end_str)

        if raw_df is None or raw_df.empty:
            raise HTTPException(status_code=500, detail="无法获取收盘价数据")

        # ── 4. 计算前向收益 ──
        dates = sorted(raw_df.index.get_level_values("datetime").unique())
        n_dates = len(dates)

        if n_dates <= pred_period + 5:
            raise HTTPException(
                status_code=400,
                detail=f"交易日不足 ({n_dates} 天)，至少需要 {pred_period + 5} 天"
            )

        # 构建前向收益 Series
        future_returns = {}
        for code in stock_codes:
            try:
                prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                ret = prices.pct_change(pred_period).shift(-pred_period)
                for dt, val in ret.items():
                    if not np.isnan(val):
                        future_returns[(code, dt)] = val
            except Exception:
                continue

        fr_series = pd.Series(future_returns, name="future_return")
        fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])

        # ── 5. 计算每个因子的 Spearman Rank IC ──
        from scipy.stats import spearmanr

        factors_ics = []
        feature_names = [str(c) for c in df_features.columns]

        for feat_name in feature_names[:params.top_k]:
            try:
                feat_col = df_features[feat_name] if feat_name in df_features.columns else df_features.iloc[:, feature_names.index(feat_name)]

                # 按日期计算 daily IC
                daily_ics = []
                test_dates = df_features.index.get_level_values("datetime").unique()

                for dt in test_dates:
                    try:
                        fv = feat_col.xs(dt, level="datetime").dropna()
                        fr = fr_series.xs(dt, level="datetime").dropna()
                        common = fv.index.intersection(fr.index)

                        if len(common) < 15:
                            continue

                        fv_vals = fv[common].values
                        fr_vals = fr[common].values

                        valid = np.isfinite(fv_vals) & np.isfinite(fr_vals)
                        fv_vals = fv_vals[valid]
                        fr_vals = fr_vals[valid]

                        if len(fv_vals) < 15:
                            continue

                        ic, _ = spearmanr(fv_vals, fr_vals)
                        if not np.isnan(ic):
                            daily_ics.append(ic)
                    except Exception:
                        continue

                if daily_ics:
                    mean_ic = np.mean(daily_ics)
                    std_ic = np.std(daily_ics)
                    icir = mean_ic / std_ic if std_ic > 0 else 0

                    factors_ics.append(FactorIC(
                        factor=feat_name,
                        ic=round(float(mean_ic), 4),
                        rank_ic=round(float(mean_ic), 4),
                        icir=round(float(icir), 2)
                    ))

            except Exception as e:
                logger.warning(f"因子 {feat_name} IC 计算失败: {e}")
                continue

        # 按 |IC| 排序
        factors_ics.sort(key=lambda x: abs(x.ic), reverse=True)

        logger.info(f"Alpha158 因子分析完成: {len(factors_ics)}/{len(feature_names)} 个因子有有效 IC")

        return FactorAnalysisResponse(
            start_date=params.start_date,
            end_date=params.end_date,
            predict_period=params.predict_period,
            factors=factors_ics,
            summary={
                "total_factors": len(factors_ics),
                "total_alpha158": len(feature_names),
                "positive_factors": sum(1 for f in factors_ics if f.ic > 0),
                "negative_factors": sum(1 for f in factors_ics if f.ic < 0),
                "best_factor": factors_ics[0].factor if factors_ics else None,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"因子分析失败: {str(e)}")


@router.get("/list")
async def list_factors():
    """获取完整 Alpha158 因子列表"""
    from qlib.contrib.data.handler import Alpha158

    fields, names = Alpha158.get_feature_config(Alpha158)

    factors = []
    categories = {
        "KMID": "K线", "KLEN": "K线", "KMID2": "K线",
        "KUP": "K线", "KUP2": "K线", "KLOW": "K线", "KLOW2": "K线",
        "KSFT": "K线", "KSFT2": "K线",
        "OPEN": "价格", "HIGH": "价格", "LOW": "价格", "VWAP": "价格",
        "ROC": "动量", "MA": "均线", "STD": "波动率",
        "BETA": "Beta", "RSQR": "R²", "RESI": "残差",
        "MAX": "极值", "MIN": "极值", "QTLU": "分位数", "QTLD": "分位数",
        "RANK": "排名", "RSV": "RSV", "IMAX": "极值位置", "IMIN": "极值位置",
        "IMXD": "极值距离", "CORR": "相关性", "CORD": "相关性",
        "CNTP": "计数", "CNTN": "计数", "CNTD": "计数",
        "SUMP": "求和", "SUMN": "求和", "SUMD": "求和",
        "VMA": "成交量均线", "VSTD": "成交量波动", "WVMA": "加权成交量",
        "VSUMP": "成交量求和", "VSUMN": "成交量求和", "VSUMD": "成交量求和",
    }

    for name in names:
        cat = "其他"
        for prefix, category in categories.items():
            if name.startswith(prefix):
                cat = category
                break
        factors.append({"name": name, "category": cat})

    return {"total": len(factors), "factors": factors}
