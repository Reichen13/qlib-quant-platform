"""Factor scoring helpers for stock-pool Layer2.

Canonical scoring:
  1) Cross-sectionally z-score each factor (avoid magnitude domination)
  2) Weight by signed IC / ICIR (negative IC factors are inverted, not abs-weighted)
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def cross_sectional_zscore(latest_factors: pd.DataFrame) -> pd.DataFrame:
    """Z-score each factor column across instruments on one date."""
    z = latest_factors.copy()
    for col in z.columns:
        series = z[col]
        valid = series.notna() & np.isfinite(series)
        if int(valid.sum()) > 1:
            mu = float(series[valid].mean())
            sigma = float(series[valid].std())
            if not np.isfinite(sigma) or sigma == 0:
                sigma = 1.0
            z.loc[valid, col] = (series[valid] - mu) / sigma
            z.loc[~valid, col] = 0.0
        else:
            z[col] = 0.0
    return z.fillna(0.0)


def signed_weight(icir: float | None, ic: float | None = None) -> float:
    """Return signed weight; prefer ICIR, fall back to IC; 0 if missing."""
    if icir is not None and np.isfinite(icir) and icir != 0:
        return float(icir)
    if ic is not None and np.isfinite(ic) and ic != 0:
        return float(ic)
    return 0.0


def score_with_signed_icir(
    latest_factors: pd.DataFrame,
    icir_map: Mapping[str, float],
    ic_map: Mapping[str, float] | None = None,
    factor_names: list[str] | None = None,
) -> dict[str, float]:
    """Score instruments using signed ICIR × cross-sectional z-scores.

    Returns mapping instrument_key -> score (higher = more long-friendly).
    """
    ic_map = ic_map or {}
    names = list(factor_names) if factor_names is not None else list(latest_factors.columns)
    z = cross_sectional_zscore(latest_factors[names] if names else latest_factors)

    weights = {name: signed_weight(icir_map.get(name), ic_map.get(name)) for name in z.columns}
    # Drop pure-zero weights to avoid all-zero scores when cache is empty-like
    active = {k: w for k, w in weights.items() if w != 0}
    if not active:
        # Equal-weight z-score mean
        scores = z.mean(axis=1)
        return {str(idx): float(val) for idx, val in scores.items()}

    denom = sum(abs(w) for w in active.values()) or 1.0
    out: dict[str, float] = {}
    for instrument in z.index:
        row = z.loc[instrument]
        score = 0.0
        for name, w in active.items():
            val = row.get(name, 0.0)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            score += float(val) * w
        out[str(instrument)] = float(score / denom)
    return out


def instrument_to_yf_code(instrument: str) -> str:
    """SH600519 / SZ000001 -> 600519.SS / 000001.SZ"""
    inst = str(instrument).upper()
    if inst.startswith("SH"):
        return inst[2:] + ".SS"
    if inst.startswith("SZ"):
        return inst[2:] + ".SZ"
    if inst.startswith("BJ"):
        return inst[2:] + ".BJ"
    return inst
