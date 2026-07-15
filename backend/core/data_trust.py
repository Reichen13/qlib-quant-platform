"""Qlib cn_data trading-trust gate.

Evaluates whether local daily bars are consistent enough to drive buy signals,
stock-pool ranking, or backtests. Focuses on the Stage-1 regression mode that
reappeared in 2026-07: historical back-adjusted prices spliced with trailing
forward-adjusted / placeholder-factor rows.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import HTTPException
from loguru import logger

CN_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"
CACHE_PATH = Path.home() / ".qlib" / "cache" / "data_trust.json"
CACHE_TTL_SECONDS = 900  # 15 minutes

# Hard gates for trading / ranking / backtest
MAX_SEVERE_SPLICE_RATIO = 0.02  # >20% jump when factor collapses to ~1.0
MAX_TAIL_PLACEHOLDER_RATIO = 0.15  # latest factor ~1 while history has real factor
MIN_SAMPLE_SIZE = 50
DEFAULT_SAMPLE_SIZE = 400
JUMP_THRESHOLD = 0.20
PLACEHOLDER_FACTOR_MAX = 1.01
REAL_FACTOR_MIN = 1.5


def _read_calendar(data_dir: Path) -> list[str]:
    cal_path = data_dir / "calendars" / "day.txt"
    if not cal_path.exists():
        return []
    return [line.strip() for line in cal_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _is_a_share_code(code: str) -> bool:
    c = code.lower()
    return (
        c.startswith("sh6")
        or c.startswith("sz0")
        or c.startswith("sz3")
        or c.startswith("bj4")
        or c.startswith("bj8")
        or c.startswith("bj920")
    )


def _sample_feature_dirs(feature_root: Path, max_sample: int) -> list[Path]:
    dirs = sorted(
        p for p in feature_root.iterdir()
        if p.is_dir() and _is_a_share_code(p.name) and (p / "close.day.bin").exists()
    )
    if len(dirs) <= max_sample:
        return dirs
    if max_sample <= 1:
        return dirs[:1]
    last = len(dirs) - 1
    return [dirs[round(i * last / (max_sample - 1))] for i in range(max_sample)]


def _inspect_stock(close_path: Path, factor_path: Path, calendar: list[str]) -> dict[str, Any] | None:
    try:
        close_raw = np.fromfile(close_path, dtype="<f")
        if len(close_raw) < 3:
            return None
        start = int(close_raw[0])
        closes = close_raw[1:]

        factors = None
        if factor_path.exists():
            factor_raw = np.fromfile(factor_path, dtype="<f")
            if len(factor_raw) >= 2:
                factors = factor_raw[1:]

        valid = np.where(np.isfinite(closes) & (closes > 0))[0]
        if len(valid) < 2:
            return None

        i1 = int(valid[-1])
        i0 = int(valid[-2])
        d1 = calendar[start + i1] if 0 <= start + i1 < len(calendar) else ""
        c0 = float(closes[i0])
        c1 = float(closes[i1])
        chg = c1 / c0 - 1.0 if c0 > 0 else 0.0

        f0 = f1 = None
        if factors is not None:
            if i0 < len(factors) and np.isfinite(factors[i0]):
                f0 = float(factors[i0])
            if i1 < len(factors) and np.isfinite(factors[i1]):
                f1 = float(factors[i1])

        # Historical max real factor (for placeholder detection)
        hist_real_factor = False
        if factors is not None and len(factors):
            finite = factors[np.isfinite(factors)]
            if len(finite) and float(np.nanmax(finite)) > PLACEHOLDER_FACTOR_MAX:
                hist_real_factor = True

        tail_placeholder = bool(
            hist_real_factor and f1 is not None and f1 <= PLACEHOLDER_FACTOR_MAX
        )
        severe_splice = bool(
            f0 is not None
            and f1 is not None
            and f0 >= REAL_FACTOR_MIN
            and f1 <= PLACEHOLDER_FACTOR_MAX
            and abs(chg) >= JUMP_THRESHOLD
        )
        large_jump = abs(chg) >= 0.35

        return {
            "code": close_path.parent.name,
            "last_date": d1,
            "prev_close": round(c0, 4),
            "last_close": round(c1, 4),
            "change_pct": round(chg, 4),
            "prev_factor": f0,
            "last_factor": f1,
            "tail_placeholder": tail_placeholder,
            "severe_splice": severe_splice,
            "large_jump": large_jump,
        }
    except Exception:
        return None


def _fingerprint(data_dir: Path) -> str:
    cal = data_dir / "calendars" / "day.txt"
    features = data_dir / "features"
    cal_mtime = cal.stat().st_mtime if cal.exists() else 0
    # Cheap dir fingerprint: count of feature dirs via one-level listdir length
    n_features = 0
    feat_mtime = 0.0
    if features.exists():
        try:
            entries = list(features.iterdir())
            n_features = len(entries)
            # sample a few mtimes
            for p in entries[:: max(1, len(entries) // 5)][:5]:
                close = p / "close.day.bin"
                if close.exists():
                    feat_mtime = max(feat_mtime, close.stat().st_mtime)
        except Exception:
            pass
    return f"{cal_mtime:.0f}:{n_features}:{feat_mtime:.0f}"


def _load_cache(fingerprint: str) -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if payload.get("fingerprint") != fingerprint:
            return None
        if time.time() - float(payload.get("cached_at", 0)) > CACHE_TTL_SECONDS:
            return None
        return payload.get("report")
    except Exception:
        return None


def _save_cache(fingerprint: str, report: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(
                {"fingerprint": fingerprint, "cached_at": time.time(), "report": report},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"data_trust cache write failed: {e}")


def evaluate_data_trust(
    data_dir: Path | None = None,
    max_sample: int = DEFAULT_SAMPLE_SIZE,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Return a trust report. `trusted=False` means buy signals must be blocked."""
    data_dir = Path(data_dir) if data_dir else CN_DATA_DIR
    fingerprint = _fingerprint(data_dir)
    if use_cache:
        cached = _load_cache(fingerprint)
        if cached is not None:
            return cached

    calendar = _read_calendar(data_dir)
    feature_root = data_dir / "features"
    if not calendar or not feature_root.exists():
        report = {
            "trusted": False,
            "status": "error",
            "trading_allowed": False,
            "message": "Qlib cn_data 日历或特征目录缺失，禁止产出买入信号",
            "sample_size": 0,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "thresholds": {
                "max_severe_splice_ratio": MAX_SEVERE_SPLICE_RATIO,
                "max_tail_placeholder_ratio": MAX_TAIL_PLACEHOLDER_RATIO,
            },
            "metrics": {},
            "reasons": ["cn_data_missing"],
            "examples": [],
            "fingerprint": fingerprint,
        }
        if use_cache:
            _save_cache(fingerprint, report)
        return report

    samples = _sample_feature_dirs(feature_root, max_sample)
    rows: list[dict[str, Any]] = []
    for stock_dir in samples:
        row = _inspect_stock(stock_dir / "close.day.bin", stock_dir / "factor.day.bin", calendar)
        if row:
            rows.append(row)

    n = len(rows)
    severe = sum(1 for r in rows if r["severe_splice"])
    placeholder = sum(1 for r in rows if r["tail_placeholder"])
    large_jumps = sum(1 for r in rows if r["large_jump"])
    severe_ratio = severe / n if n else 1.0
    placeholder_ratio = placeholder / n if n else 1.0
    large_jump_ratio = large_jumps / n if n else 1.0

    reasons: list[str] = []
    if n < MIN_SAMPLE_SIZE:
        reasons.append(f"sample_too_small:{n}")
    if severe_ratio > MAX_SEVERE_SPLICE_RATIO:
        reasons.append(
            f"severe_tail_splice_ratio={severe_ratio:.2%} > {MAX_SEVERE_SPLICE_RATIO:.0%}"
        )
    if placeholder_ratio > MAX_TAIL_PLACEHOLDER_RATIO:
        reasons.append(
            f"tail_factor_placeholder_ratio={placeholder_ratio:.2%} > {MAX_TAIL_PLACEHOLDER_RATIO:.0%}"
        )

    trusted = len(reasons) == 0
    if trusted:
        status = "trusted"
        message = (
            f"尾部复权一致性通过（样本 {n}）：严重拼接 {severe_ratio:.2%}，"
            f"尾部 factor 占位 {placeholder_ratio:.2%}"
        )
    else:
        status = "untrusted"
        message = (
            "本地 Qlib 日线尾部复权不一致，已禁止买入信号/股票池刷新/回测。"
            "请先运行 scripts/scan_tail_adjustment_splice.py 与 "
            "scripts/repair_tail_adjustment_splice.py 修复后重试。"
        )

    examples = [r for r in rows if r["severe_splice"] or r["large_jump"]][:10]
    report = {
        "trusted": trusted,
        "status": status,
        "trading_allowed": trusted,
        "message": message,
        "sample_size": n,
        "calendar_last": calendar[-1] if calendar else "",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "thresholds": {
            "max_severe_splice_ratio": MAX_SEVERE_SPLICE_RATIO,
            "max_tail_placeholder_ratio": MAX_TAIL_PLACEHOLDER_RATIO,
            "jump_threshold": JUMP_THRESHOLD,
        },
        "metrics": {
            "severe_splice_count": severe,
            "severe_splice_ratio": round(severe_ratio, 4),
            "tail_placeholder_count": placeholder,
            "tail_placeholder_ratio": round(placeholder_ratio, 4),
            "large_jump_count": large_jumps,
            "large_jump_ratio": round(large_jump_ratio, 4),
        },
        "reasons": reasons,
        "examples": examples,
        "fingerprint": fingerprint,
        "repair_hints": [
            "python scripts/scan_tail_adjustment_splice.py --out ~/.qlib/cache/tail_splice_codes.txt",
            "python scripts/repair_tail_adjustment_splice.py --codes-file ~/.qlib/cache/tail_splice_codes.txt --start 2024-01-01",
            "python scripts/assert_data_trust.py",
        ],
    }
    if use_cache:
        _save_cache(fingerprint, report)
    return report


def invalidate_data_trust_cache() -> None:
    try:
        if CACHE_PATH.exists():
            CACHE_PATH.unlink()
    except Exception:
        pass


def require_data_trusted(
    *,
    action: str,
    allow_untrusted: bool = False,
    max_sample: int = DEFAULT_SAMPLE_SIZE,
) -> dict[str, Any]:
    """Raise HTTP 503 when data is untrusted and override is not set."""
    report = evaluate_data_trust(max_sample=max_sample)
    if report.get("trusted"):
        return report
    if allow_untrusted:
        logger.warning(f"data_trust override for action={action}: {report.get('reasons')}")
        return {**report, "override": True, "trading_allowed": False}
    raise HTTPException(
        status_code=503,
        detail={
            "error": "data_untrusted",
            "action": action,
            "message": report.get("message"),
            "reasons": report.get("reasons"),
            "metrics": report.get("metrics"),
            "examples": report.get("examples", [])[:5],
            "repair_hints": report.get("repair_hints"),
            "checked_at": report.get("checked_at"),
        },
    )


def apply_untrusted_screening_block(result: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Force screening output into non-buyable mode when data is untrusted."""
    blocked = dict(result)
    buckets = dict(blocked.get("buckets") or {})
    buyable = list(buckets.get("buyable") or [])
    watch = list(buckets.get("watch_only") or [])
    for item in buyable:
        moved = dict(item)
        moved["action"] = "降级"
        moved["bucket"] = "watch_only"
        moved["reason"] = "数据尾部复权不可信，买入信号已全局关闭"
        watch.append(moved)
    buckets["buyable"] = []
    buckets["watch_only"] = watch
    blocked["buckets"] = buckets

    candidates = []
    for item in blocked.get("candidates") or []:
        row = dict(item)
        if row.get("bucket") == "buyable":
            row["bucket"] = "watch_only"
            row["action"] = "降级"
            row["reason"] = "数据尾部复权不可信，买入信号已全局关闭"
        candidates.append(row)
    blocked["candidates"] = candidates

    warnings = list(blocked.get("warnings") or [])
    msg = f"DATA_UNTRUSTED: {report.get('message')}"
    if msg not in warnings:
        warnings.insert(0, msg)
    for reason in report.get("reasons") or []:
        tag = f"data_trust:{reason}"
        if tag not in warnings:
            warnings.append(tag)
    blocked["warnings"] = warnings
    blocked["trading_allowed"] = False
    blocked["data_trust"] = {
        "trusted": False,
        "status": report.get("status"),
        "metrics": report.get("metrics"),
        "reasons": report.get("reasons"),
        "checked_at": report.get("checked_at"),
    }
    return blocked
