"""
Alpha158 因子缓存
缓解每次因子分析/回测都重新计算全部 158 个因子的性能问题。
缓存基于 (start_time, end_time, instruments) 的 MD5 hash，默认 TTL 24 小时。
"""

import hashlib
import json
import os
from pathlib import Path
import pandas as pd
from loguru import logger

CACHE_DIR = Path.home() / ".qlib" / "alpha158_cache"


def _get_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _make_key(start_time: str, end_time: str, instruments: str,
              fit_start_time: str = None, fit_end_time: str = None) -> str:
    config = {
        "start_time": str(start_time),
        "end_time": str(end_time),
        "instruments": str(instruments),
        "fit_start_time": str(fit_start_time) if fit_start_time else None,
        "fit_end_time": str(fit_end_time) if fit_end_time else None,
    }
    raw = json.dumps(config, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def load_cached_features(start_time: str, end_time: str, instruments: str = "csi300",
                         fit_start_time: str = None, fit_end_time: str = None,
                         max_age_hours: int = 24) -> pd.DataFrame | None:
    """尝试加载缓存的 Alpha158 特征。返回 DataFrame 或 None。"""
    key = _make_key(start_time, end_time, instruments, fit_start_time, fit_end_time)
    cache_path = _get_cache_dir() / f"{key}_features.parquet"

    if not cache_path.exists():
        return None

    age_hours = (pd.Timestamp.now() - pd.Timestamp.fromtimestamp(
        cache_path.stat().st_mtime)).total_seconds() / 3600

    if age_hours > max_age_hours:
        logger.info(f"Alpha158 缓存已过期: {key[:8]}... (age={age_hours:.1f}h > {max_age_hours}h)")
        return None

    try:
        df = pd.read_parquet(cache_path)
        logger.info(f"Alpha158 缓存命中: {key[:8]}... ({len(df)} rows, {len(df.columns)} cols, age={age_hours:.1f}h)")
        return df
    except Exception as e:
        logger.warning(f"Alpha158 缓存读取失败: {e}")
        return None


def save_features_cache(df_features: pd.DataFrame, start_time: str, end_time: str,
                        instruments: str = "csi300", fit_start_time: str = None,
                        fit_end_time: str = None) -> None:
    """保存 Alpha158 特征到缓存。"""
    key = _make_key(start_time, end_time, instruments, fit_start_time, fit_end_time)
    cache_path = _get_cache_dir() / f"{key}_features.parquet"
    try:
        df_features.to_parquet(cache_path)
        logger.info(f"Alpha158 特征已缓存: {key[:8]}... ({len(df_features)} rows, {len(df_features.columns)} cols)")
    except Exception as e:
        logger.warning(f"Alpha158 缓存写入失败: {e}")


def clear_expired_cache(max_age_hours: int = 168) -> int:
    """清理过期缓存，返回清理文件数。"""
    import time
    count = 0
    now = time.time()
    cache_dir = _get_cache_dir()
    for f in cache_dir.glob("*.parquet"):
        if now - f.stat().st_mtime > max_age_hours * 3600:
            f.unlink()
            count += 1
    if count:
        logger.info(f"清理了 {count} 个过期 Alpha158 缓存文件")
    return count
