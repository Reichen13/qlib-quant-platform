"""
Alpha158 因子缓存
缓解每次因子分析/回测都重新计算全部 158 个因子的性能问题。

缓存 key 包含：
  - instruments / 日期窗口（按月）
  - 本地 cn_data 指纹（日历 mtime + 抽样 close/factor bin 的 mtime/size）

数据更新后指纹变化 → 自动 miss；也可在数据更新回调里 clear_all_cache()。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
from loguru import logger

CACHE_DIR = Path.home() / ".qlib" / "alpha158_cache"
CN_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"
FINGERPRINT_CACHE: dict[str, tuple[float, str]] = {}
FINGERPRINT_TTL_SEC = 60.0  # process-local fingerprint refresh


def _get_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def compute_data_fingerprint(data_dir: Path | None = None, sample_size: int = 64) -> str:
    """Cheap fingerprint of local Qlib cn_data for cache invalidation.

    Includes:
      - calendars/day.txt mtime + size
      - evenly sampled features/*/close.day.bin and factor.day.bin mtime + size
      - feature directory count
    """
    data_dir = Path(data_dir) if data_dir else CN_DATA_DIR
    cache_key = str(data_dir)
    now = time.time()
    cached = FINGERPRINT_CACHE.get(cache_key)
    if cached and (now - cached[0]) < FINGERPRINT_TTL_SEC:
        return cached[1]

    h = hashlib.md5()
    cal = data_dir / "calendars" / "day.txt"
    if cal.exists():
        st = cal.stat()
        h.update(f"cal:{st.st_mtime_ns}:{st.st_size}".encode())
    else:
        h.update(b"cal:missing")

    features = data_dir / "features"
    if features.exists():
        try:
            dirs = sorted(
                p for p in features.iterdir()
                if p.is_dir() and (p / "close.day.bin").exists()
            )
        except Exception:
            dirs = []
        h.update(f"nfeat:{len(dirs)}".encode())
        if dirs:
            n = min(sample_size, len(dirs))
            if n == 1:
                picks = [dirs[0]]
            else:
                picks = [dirs[round(i * (len(dirs) - 1) / (n - 1))] for i in range(n)]
            for p in picks:
                for name in ("close.day.bin", "factor.day.bin"):
                    fpath = p / name
                    if fpath.exists():
                        st = fpath.stat()
                        h.update(f"{p.name}:{name}:{st.st_mtime_ns}:{st.st_size}".encode())
                    else:
                        h.update(f"{p.name}:{name}:missing".encode())
    else:
        h.update(b"features:missing")

    digest = h.hexdigest()[:16]
    FINGERPRINT_CACHE[cache_key] = (now, digest)
    return digest


def invalidate_fingerprint_cache() -> None:
    FINGERPRINT_CACHE.clear()


def _make_key(
    start_time: str,
    end_time: str,
    instruments: str,
    fit_start_time: str = None,
    fit_end_time: str = None,
    data_fingerprint: str | None = None,
) -> str:
    from datetime import datetime

    try:
        st = datetime.fromisoformat(str(start_time)[:10])
        et = datetime.fromisoformat(str(end_time)[:10])
        start_month = st.strftime("%Y-%m")
        end_month = et.strftime("%Y-%m")
    except Exception:
        start_month = str(start_time)[:7]
        end_month = str(end_time)[:7]

    fp = data_fingerprint or compute_data_fingerprint()
    config = {
        "instruments": str(instruments),
        "start_month": start_month,
        "end_month": end_month,
        "data_fp": fp,
        # fit window affects processor stats; include if provided
        "fit_start": str(fit_start_time)[:10] if fit_start_time else "",
        "fit_end": str(fit_end_time)[:10] if fit_end_time else "",
    }
    raw = json.dumps(config, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def load_cached_features(
    start_time: str,
    end_time: str,
    instruments: str = "core650",
    fit_start_time: str = None,
    fit_end_time: str = None,
    max_age_hours: int = 24,
) -> pd.DataFrame | None:
    """尝试加载缓存的 Alpha158 特征。指纹不匹配或过期则返回 None。"""
    fp = compute_data_fingerprint()
    key = _make_key(start_time, end_time, instruments, fit_start_time, fit_end_time, fp)
    cache_path = _get_cache_dir() / f"{key}_features.parquet"

    # Exact key miss: do NOT fall back to older-fingerprint caches covering date range
    # (that was the P1 bug: repaired prices still hit stale Alpha158 cache).
    if not cache_path.exists():
        logger.info(f"Alpha158 缓存未命中 key={key[:8]}... fp={fp}")
        return None

    # Sidecar fingerprint double-check
    meta_file = _meta_path(cache_path)
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("data_fp") and meta.get("data_fp") != fp:
                logger.info(
                    f"Alpha158 缓存指纹过期: cache_fp={meta.get('data_fp')} current_fp={fp}"
                )
                return None
        except Exception as e:
            logger.debug(f"Alpha158 meta read failed: {e}")

    age_hours = (
        pd.Timestamp.now() - pd.Timestamp.fromtimestamp(cache_path.stat().st_mtime)
    ).total_seconds() / 3600

    if age_hours > max_age_hours:
        logger.info(
            f"Alpha158 缓存已过期: {cache_path.name[:8]}... "
            f"(age={age_hours:.1f}h > {max_age_hours}h)"
        )
        return None

    try:
        df = pd.read_parquet(cache_path)
        logger.info(
            f"Alpha158 缓存命中: {cache_path.name[:8]}... "
            f"({len(df)} rows, {len(df.columns)} cols, age={age_hours:.1f}h, fp={fp})"
        )
        return df
    except Exception as e:
        logger.warning(f"Alpha158 缓存读取失败: {e}")
        return None


def save_features_cache(
    df_features: pd.DataFrame,
    start_time: str,
    end_time: str,
    instruments: str = "core650",
    fit_start_time: str = None,
    fit_end_time: str = None,
) -> None:
    """保存 Alpha158 特征到缓存（写入 data fingerprint sidecar）。"""
    fp = compute_data_fingerprint()
    key = _make_key(start_time, end_time, instruments, fit_start_time, fit_end_time, fp)
    cache_path = _get_cache_dir() / f"{key}_features.parquet"
    try:
        df_features.to_parquet(cache_path)
        meta = {
            "data_fp": fp,
            "instruments": str(instruments),
            "start_time": str(start_time)[:10],
            "end_time": str(end_time)[:10],
            "rows": int(len(df_features)),
            "cols": int(len(df_features.columns)),
            "saved_at": pd.Timestamp.now().isoformat(),
        }
        _meta_path(cache_path).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            f"Alpha158 特征已缓存: {key[:8]}... "
            f"({len(df_features)} rows, {len(df_features.columns)} cols, fp={fp})"
        )
    except Exception as e:
        logger.warning(f"Alpha158 缓存写入失败: {e}")


def clear_expired_cache(max_age_hours: int = 168) -> int:
    """清理过期缓存，返回清理文件数。"""
    count = 0
    now = time.time()
    cache_dir = _get_cache_dir()
    for f in cache_dir.glob("*.parquet"):
        if now - f.stat().st_mtime > max_age_hours * 3600:
            try:
                f.unlink()
                meta = _meta_path(f)
                if meta.exists():
                    meta.unlink()
                count += 1
            except Exception:
                pass
    if count:
        logger.info(f"清理了 {count} 个过期 Alpha158 缓存文件")
    return count


def clear_all_cache() -> int:
    """Delete all Alpha158 cache files (call after data rebuild)."""
    invalidate_fingerprint_cache()
    count = 0
    cache_dir = _get_cache_dir()
    if not cache_dir.exists():
        return 0
    for f in list(cache_dir.glob("*.parquet")) + list(cache_dir.glob("*.meta.json")):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    if count:
        logger.info(f"已清空 Alpha158 缓存 {count} 个文件")
    return count
