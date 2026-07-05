"""
数据健康检查 API - 数据源状态监控与异常告警
"""

import os
import json
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field

from auth import verify_api_key
from db.task_store import TaskStore
from utils.code_normalization import normalize_stock_code

router = APIRouter()
_MAX_FEATURE_DATE_SAMPLE = 300
_MAX_ADJUSTMENT_SAMPLE = 80
_ONE_FACTOR_TOLERANCE = 1e-6


class DataUpdateRequest(BaseModel):
    """数据更新请求"""

    type: Literal["stocks", "all", "core", "etf", "index"] = Field(default="stocks")
    start_date: str | None = Field(default=None, description="起始日期 YYYY-MM-DD，默认从 Qlib 最新日期开始")
    end_date: str | None = Field(default=None, description="结束日期 YYYY-MM-DD，默认到今天")
    max_stocks: int | None = Field(default=None, ge=1, le=5000, description="最多更新多少只股票，测试时可填较小值")
    codes: list[str] | None = Field(default=None, description="可选：只更新/修复指定股票代码")
    rebuild_stale: bool = Field(default=False, description="Repair existing stale zero/NaN OHLC rows")
    overwrite_existing: bool = Field(default=False, description="Overwrite existing non-zero price fields in the requested window")


_update_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()
data_update_task_store = TaskStore(Path.home() / ".qlib" / "data_update_tasks.db", table_name="data_update_tasks")


async def require_data_update_key(_=Depends(verify_api_key)):
    """数据更新会修改本地 Qlib 数据，线上必须配置 API_KEY 后才允许触发。"""
    expected = os.getenv("API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务器未配置 API_KEY，已禁用网页触发数据更新。请先在服务器环境变量中配置 API_KEY。",
        )


def _get_latest_trade_date() -> str:
    """从 Qlib 日历获取最近一个交易日"""
    try:
        cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
        if cal_path.exists():
            dates = cal_path.read_text().strip().split("\n")
            return dates[-1] if dates else ""
    except Exception:
        pass
    return ""


def _feature_latest_date(bin_path: Path, calendar: list[str]) -> str:
    """Return the latest calendar date represented by a Qlib feature bin file."""
    try:
        import numpy as np

        raw = np.fromfile(bin_path, dtype="<f")
        if len(raw) < 2:
            return ""
        start_idx = int(raw[0])
        end_idx = start_idx + len(raw) - 2
        if 0 <= end_idx < len(calendar):
            return calendar[end_idx]
    except Exception:
        logger.debug(f"无法读取特征文件最新日期: {bin_path}")
    return ""


def _sample_feature_files(feature_files: list[Path]) -> list[Path]:
    if len(feature_files) <= _MAX_FEATURE_DATE_SAMPLE:
        return feature_files
    last = len(feature_files) - 1
    return [
        feature_files[round(i * last / (_MAX_FEATURE_DATE_SAMPLE - 1))]
        for i in range(_MAX_FEATURE_DATE_SAMPLE)
    ]


def _get_stock_feature_date_summary(data_dir: Path, calendar: list[str]) -> dict:
    """Summarize actual close.day.bin dates without being fooled by one updated file."""
    feature_files = sorted((data_dir / "features").glob("*/close.day.bin"))
    latest_dates: list[str] = []
    for bin_path in _sample_feature_files(feature_files):
        latest_date = _feature_latest_date(bin_path, calendar)
        if latest_date:
            latest_dates.append(latest_date)
    if not latest_dates:
        return {
            "representative_date": "",
            "max_date": "",
            "min_date": "",
            "sample_size": 0,
            "max_date_coverage": 0.0,
        }

    sorted_dates = sorted(latest_dates)
    max_date = sorted_dates[-1]
    counts = Counter(latest_dates)
    return {
        "representative_date": sorted_dates[len(sorted_dates) // 2],
        "max_date": max_date,
        "min_date": sorted_dates[0],
        "sample_size": len(sorted_dates),
        "max_date_coverage": round(counts[max_date] / len(sorted_dates), 4),
    }


def _get_stock_feature_latest_date(data_dir: Path, calendar: list[str]) -> str:
    """Return the representative feature date used for health and update start date."""
    return _get_stock_feature_date_summary(data_dir, calendar)["representative_date"]


def _read_feature_values(bin_path: Path) -> list[float]:
    """Read Qlib float feature values, ignoring the leading start-index slot."""
    try:
        import numpy as np

        raw = np.fromfile(bin_path, dtype="<f")
        if len(raw) < 2:
            return []
        values = raw[1:]
        finite = values[np.isfinite(values)]
        return [float(v) for v in finite]
    except Exception:
        logger.debug(f"无法读取 Qlib 特征文件: {bin_path}")
        return []


def _read_feature_raw_values(bin_path: Path) -> list[float]:
    """Read Qlib float feature values including NaN gaps, ignoring the start-index slot."""
    try:
        import numpy as np

        raw = np.fromfile(bin_path, dtype="<f")
        if len(raw) < 2:
            return []
        return [float(value) for value in raw[1:]]
    except Exception:
        logger.debug(f"无法读取 Qlib 原始特征文件: {bin_path}")
        return []


def _read_calendar_dates(data_dir: Path) -> list[str]:
    cal_path = data_dir / "calendars" / "day.txt"
    if not cal_path.exists():
        return []
    return [line.strip() for line in cal_path.read_text().splitlines() if line.strip()]


def _read_feature_points(bin_path: Path, calendar: list[str]) -> list[dict]:
    try:
        import numpy as np

        raw = np.fromfile(bin_path, dtype="<f")
        if len(raw) < 2:
            return []
        start_idx = int(raw[0])
        points = []
        for offset, value in enumerate(raw[1:]):
            if not np.isfinite(value):
                continue
            cal_idx = start_idx + offset
            points.append({
                "date": calendar[cal_idx] if 0 <= cal_idx < len(calendar) else "",
                "value": float(value),
            })
        return points
    except Exception:
        logger.debug(f"无法读取 Qlib 特征序列: {bin_path}")
        return []


def _find_large_price_jump(points: list[dict], threshold: float = 0.35, calendar: list[str] | None = None) -> dict | None:
    """检测超过阈值的单日跳变。跨NaN区间的累计涨跌（停牌复牌）不当单日跳变。"""
    cal_idx = {d: i for i, d in enumerate(calendar)} if calendar else {}
    previous = None
    for point in points:
        value = point.get("value")
        date = point.get("date", "")
        if value <= 0:
            previous = None
            continue
        if previous and previous.get("value", 0) > 0:
            prev_date = previous.get("date", "")
            if cal_idx and prev_date and date:
                pi = cal_idx.get(prev_date, -1)
                ci = cal_idx.get(date, -1)
                if pi >= 0 and ci >= 0 and (ci - pi) > 1:
                    previous = point
                    continue
            jump_pct = value / previous["value"] - 1.0
            if abs(jump_pct) >= threshold:
                return {
                    "date": date,
                    "previous_date": prev_date,
                    "close": round(value, 4),
                    "previous_close": round(previous["value"], 4),
                    "jump_pct": round(jump_pct, 4),
                }
        previous = point
    return None


def _check_price_adjustment_policy() -> dict:
    """Diagnose whether price adjustment policy is visible and auditable."""
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    feature_dir = data_dir / "features"
    calendar = _read_calendar_dates(data_dir)
    if not feature_dir.exists():
        return {
            "source": "Qlib cn_data 复权口径",
            "status": "error",
            "adjustment_mode": "unknown",
            "factor_field_status": "missing",
            "message": "未找到 Qlib 特征目录，无法判断复权口径",
            "sample_size": 0,
        }

    close_files = sorted(
        path for path in feature_dir.glob("*/close.day.bin")
        if _is_a_share_feature_code(path.parent.name)
    )
    sample_files = _sample_feature_files(close_files)
    if len(sample_files) > _MAX_ADJUSTMENT_SAMPLE:
        sample_files = _sample_feature_files(sample_files)[:_MAX_ADJUSTMENT_SAMPLE]

    sampled = 0
    factor_missing = 0
    factor_empty = 0
    all_one_factor = 0
    has_non_one_factor = 0
    latest_one_factor = 0
    possible_unadjusted_jumps = 0
    examples: list[dict] = []
    suspect_examples: list[dict] = []

    for close_path in sample_files:
        sampled += 1
        code = close_path.parent.name
        factor_path = close_path.parent / "factor.day.bin"

        close_points = _read_feature_points(close_path, calendar)
        jump = _find_large_price_jump(close_points, calendar=calendar)
        if jump:
            possible_unadjusted_jumps += 1
            if len(suspect_examples) < 10:
                suspect_examples.append({"code": code, **jump})

        if not factor_path.exists():
            factor_missing += 1
            if len(examples) < 5:
                examples.append({"code": code, "issue": "factor_missing"})
            continue

        factor_values = _read_feature_values(factor_path)
        if not factor_values:
            factor_empty += 1
            if len(examples) < 5:
                examples.append({"code": code, "issue": "factor_empty"})
            continue

        non_one_values = [v for v in factor_values if abs(v - 1.0) > _ONE_FACTOR_TOLERANCE]
        if non_one_values:
            has_non_one_factor += 1
        else:
            all_one_factor += 1

        if abs(factor_values[-1] - 1.0) <= _ONE_FACTOR_TOLERANCE:
            latest_one_factor += 1

    if sampled == 0:
        return {
            "source": "Qlib cn_data 复权口径",
            "status": "error",
            "adjustment_mode": "unknown",
            "factor_field_status": "missing",
            "message": "未找到可诊断的股票日线文件",
            "sample_size": 0,
        }

    available_factor_count = sampled - factor_missing - factor_empty
    latest_one_ratio = latest_one_factor / available_factor_count if available_factor_count > 0 else 0.0

    if factor_missing == sampled or (factor_missing + factor_empty) == sampled:
        status = "warning"
        adjustment_mode = "unknown"
        factor_field_status = "missing"
        message = "未找到可用 factor 字段，无法确认除权复权口径"
    elif has_non_one_factor == 0:
        status = "warning"
        adjustment_mode = "qfq_price_with_placeholder_factor"
        factor_field_status = "placeholder_1.0"
        message = "factor 字段全为 1.0（占位符），数据可能为旧口径（前复权+占位因子），建议重建"
    elif latest_one_ratio >= 0.8:
        status = "warning"
        adjustment_mode = "qfq_price_with_mixed_factor"
        factor_field_status = "mixed_real_and_placeholder"
        message = "多数最新样本 factor 为 1.0，疑似增量数据为旧口径占位因子，建议全量重建"
    else:
        status = "normal"
        adjustment_mode = "back_adjusted_with_cumulative_factor"
        factor_field_status = "real_cumulative_factor"
        message = "$close 为后复权价（原始价 x 累积后复权因子），$factor 为累积后复权因子，面向用户价格已自动换算前复权（=真实市价）"

    warnings: list[str] = []
    if possible_unadjusted_jumps:
        status = "warning"
        message = f"{message}；另发现疑似大幅跳变，需要抽查是否为未复权或数据断点"
        warnings.append(f"样本中 {possible_unadjusted_jumps} 只出现超过 35% 的单日跳变，建议抽查是否为未复权或数据修复断点")
    warnings.append("当前口径：baostock 单源写入，后复权（backAdjustFactor），增量只追加不重写历史")

    return {
        "source": "Qlib cn_data 复权口径",
        "status": status,
        "adjustment_mode": adjustment_mode,
        "factor_field_status": factor_field_status,
        "message": message,
        "sample_size": sampled,
        "factor_missing_count": factor_missing,
        "factor_empty_count": factor_empty,
        "all_one_factor_count": all_one_factor,
        "non_one_factor_count": has_non_one_factor,
        "latest_one_factor_count": latest_one_factor,
        "possible_unadjusted_jump_count": possible_unadjusted_jumps,
        "source_policy": {
            "primary_use": "research_backtest_factor",
            "expected_price_adjustment": "back_adjusted_with_cumulative_factor",
            "write_source": "Baostock adjustflag=3 (raw price) + query_adjust_factor (backAdjustFactor)",
            "user_facing_price": "前复权（自动换算：后复权价 / 最新factor），与券商真实市价一致",
            "factor_semantics": "累积后复权因子，历史不可变（增量只追加不重写历史）",
            "execution_price_note": "实盘成交价应以实时未复权行情或券商行情为准",
        },
        "warnings": warnings,
        "examples": examples,
        "suspect_examples": suspect_examples,
    }


def _get_stock_latest_trade_date() -> str:
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    cal_path = data_dir / "calendars" / "day.txt"
    if not cal_path.exists():
        return ""
    calendar = [line.strip() for line in cal_path.read_text().splitlines() if line.strip()]
    return _get_stock_feature_latest_date(data_dir, calendar) or (calendar[-1] if calendar else "")


def _get_instrument_count(instruments_path: Path) -> dict:
    """Count unique instrument codes while tolerating duplicated rows and code case differences."""
    if not instruments_path.exists():
        return {"total": 0, "raw_total": 0, "duplicate_count": 0}

    raw_codes = []
    for line in instruments_path.read_text().splitlines():
        parts = line.strip().split("\t")
        if parts and parts[0]:
            raw_codes.append(parts[0].lower())

    unique_codes = set(raw_codes)
    return {
        "total": len(unique_codes),
        "raw_total": len(raw_codes),
        "duplicate_count": len(raw_codes) - len(unique_codes),
    }


def _get_feature_stock_count(data_dir: Path) -> dict:
    """Count A-share instruments that have local close.day.bin feature files."""
    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {"total": 0}

    codes = set()
    for bin_path in feature_dir.glob("*/close.day.bin"):
        code = bin_path.parent.name.lower()
        if _is_a_share_feature_code(code):
            codes.add(code)
    return {"total": len(codes)}


def _is_a_share_feature_code(code: str) -> bool:
    normalized = str(code or "").lower()
    return (
        normalized.startswith("sh6")
        or normalized.startswith("sz0")
        or normalized.startswith("sz3")
        or normalized.startswith("bj4")
        or normalized.startswith("bj8")
        or normalized.startswith("bj920")
    )


def _summarize_close_value_quality(data_dir: Path) -> dict:
    """Sample close.day.bin density so hollow securities do not look healthy."""
    import math

    feature_dir = data_dir / "features"
    if not feature_dir.exists():
        return {
            "sample_size": 0,
            "effective_value_density": 0.0,
            "max_consecutive_nan": 0,
            "hollow_count": 0,
            "quality_examples": [],
        }

    close_files = sorted(
        path for path in feature_dir.glob("*/close.day.bin")
        if _is_a_share_feature_code(path.parent.name)
    )
    sample_files = _sample_feature_files(close_files)
    finite_values = total_values = max_consecutive_nan = hollow_count = 0
    examples: list[dict] = []

    for close_path in sample_files:
        values = _read_feature_raw_values(close_path)
        if not values:
            continue
        total_values += len(values)
        finite_count = 0
        current_nan = 0
        file_max_nan = 0
        for value in values:
            if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
                finite_values += 1
                finite_count += 1
                current_nan = 0
            else:
                current_nan += 1
                file_max_nan = max(file_max_nan, current_nan)
        max_consecutive_nan = max(max_consecutive_nan, file_max_nan)
        density = finite_count / len(values)
        if len(values) >= 200 and density < 0.2:
            hollow_count += 1
            if len(examples) < 5:
                examples.append({
                    "code": close_path.parent.name,
                    "length": len(values),
                    "finite_count": finite_count,
                    "density": round(density, 4),
                    "max_consecutive_nan": file_max_nan,
                })

    density = finite_values / total_values if total_values else 0.0
    # 最近 90 个交易日密度检查（股改钉子户/退市重上市的长停不应误报为数据缺陷）
    import math as _math, numpy as _np
    recent_gap = False
    cal = []
    try:
        cal_path = data_dir / "calendars" / "day.txt"
        if cal_path.exists():
            cal = cal_path.read_text(encoding="utf-8").strip().splitlines()
            if len(cal) >= 90:
                recent = cal[-90:]
                for close_path in sample_files:
                    raw = _np.fromfile(str(close_path), dtype="<f")
                    start_idx = int(raw[0]) if len(raw) >= 1 else 0
                    recent_nan = 0
                    for j in range(len(recent)):
                        off = (len(cal) - 90 + j) - start_idx
                        if 0 <= off < len(raw) - 1:
                            v = float(raw[1 + off])
                            if not (_math.isfinite(v) and v > 0):
                                recent_nan += 1
                            else:
                                recent_nan = 0
                    if recent_nan > 30:
                        recent_gap = True
                        break
    except Exception:
        pass
    return {
        "sample_size": len(sample_files),
        "effective_value_density": round(density, 4),
        "max_consecutive_nan": max_consecutive_nan,
        "hollow_count": hollow_count,
        "recent_gap_warning": recent_gap,
        "quality_examples": examples,
    }

def _check_qlib_data() -> dict:
    """检查 Qlib cn_data 数据状态"""
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    today = datetime.now()

    if not data_dir.exists():
        return {
            "source": "Qlib cn_data",
            "exists": False,
            "status": "error",
            "message": "Qlib 数据目录不存在",
        }

    # 检查日历
    cal_path = data_dir / "calendars" / "day.txt"
    last_date = ""
    lag_days = -1
    if cal_path.exists():
        dates = cal_path.read_text().strip().split("\n")
        feature_summary = _get_stock_feature_date_summary(data_dir, dates)
        close_quality = _summarize_close_value_quality(data_dir)
        last_date = feature_summary["representative_date"] or (dates[-1] if dates else "")
        if last_date:
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                # 计算交易日滞后：用自然日数除以1.4估算交易日
                natural_lag = (today - last_dt).days
                lag_days = max(0, int(natural_lag * 0.7))
            except Exception:
                lag_days = -1

    # 检查特征数据
    features_dir = data_dir / "features"
    n_features = 0
    if features_dir.exists():
        n_features = len(list(features_dir.glob("**/*")))

    # 判定状态
    if not last_date:
        status = "error"
        message = "无法确定最后交易日"
    elif lag_days == -1:
        status = "warning"
        message = "日历解析异常"
    elif lag_days <= 1:
        status = "normal"
        message = "数据正常"
    elif lag_days <= 3:
        status = "warning"
        message = f"数据滞后约 {lag_days} 个交易日"
    else:
        status = "error"
        message = f"数据严重滞后约 {lag_days} 个交易日，可能已停止更新"

    return {
        "source": "Qlib cn_data",
        "exists": True,
        "status": status,
        "last_date": last_date,
        "lag_days": lag_days,
        "message": message,
        "n_features": n_features,
        "data_dir": str(data_dir),
        "sample_latest_date": feature_summary.get("max_date", "") if cal_path.exists() else "",
        "sample_latest_coverage": feature_summary.get("max_date_coverage", 0.0) if cal_path.exists() else 0.0,
    }


def _check_stocks_data() -> dict:
    """检查股票日线数据状态（使用 Qlib 日历作为真实来源）"""
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    cal_path = data_dir / "calendars" / "day.txt"
    csi300_counts = _get_instrument_count(data_dir / "instruments" / "csi300.txt")
    feature_stock_counts = _get_feature_stock_count(data_dir)

    if cal_path.exists():
        dates = cal_path.read_text().strip().split("\n")
        feature_summary = _get_stock_feature_date_summary(data_dir, dates)
        last_date = feature_summary["representative_date"] or (dates[-1] if dates else "")
        close_quality = _summarize_close_value_quality(data_dir)
        today = datetime.now()
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            lag_days = max(0, int((today - last_dt).days * 0.7))
        except Exception:
            lag_days = -1

        if lag_days <= 1:
            status, msg = "normal", "数据正常"
        elif lag_days <= 3:
            status, msg = "warning", f"滞后约 {lag_days} 个交易日"
        else:
            status, msg = "error", f"严重滞后约 {lag_days} 个交易日"

        if close_quality["sample_size"] and (
            close_quality["effective_value_density"] < 0.8
            or close_quality["recent_gap_warning"]
            or close_quality["hollow_count"] > 0
        ):
            status = "error"
            msg = (
                f"日线有效值密度异常({close_quality['effective_value_density']:.1%})，"
                f"近90交易日存在有效值缺口，疑似数据断层"
            )

        return {
            "total": feature_stock_counts["total"],
            "raw_total": feature_stock_counts["total"],
            "duplicate_count": 0,
            "csi300_total": csi300_counts["total"],
            "csi300_raw_total": csi300_counts["raw_total"],
            "csi300_duplicate_count": csi300_counts["duplicate_count"],
            "last_date": last_date,
            "lag_days": lag_days,
            "status": status,
            "message": msg,
            "sample_latest_date": feature_summary.get("max_date", ""),
            "sample_latest_coverage": feature_summary.get("max_date_coverage", 0.0),
            **close_quality,
        }

    return {"total": 0, "last_date": "", "lag_days": -1, "status": "error", "message": "日历文件不存在"}


def _check_baostock_industry() -> dict:
    """检查 Baostock 行业数据可用性"""
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == '0':
            bs.logout()
            return {"source": "Baostock 行业分类", "status": "normal", "message": "服务可连接"}
        bs.logout()
        return {"source": "Baostock 行业分类", "status": "error", "message": f"登录失败: {lg.error_msg}"}
    except ImportError:
        return {"source": "Baostock 行业分类", "status": "error", "message": "baostock 未安装"}
    except Exception as e:
        return {"source": "Baostock 行业分类", "status": "warning", "message": str(e)}


def _baostock_skipped_status() -> dict:
    return {
        "source": "Baostock 行业分类",
        "status": "unknown",
        "message": "快速检查模式未连接外部 Baostock 服务",
    }


def _check_tdx_mcp(include_external: bool = False) -> dict:
    try:
        from services.tdx_mcp_provider import TdxMcpProvider

        provider = TdxMcpProvider.from_env()
        status = provider.safe_status()
        if not provider.is_configured:
            return {
                "source": "通达信官方 MCP",
                "status": "unknown",
                "configured": False,
                "message": "未配置 TDX_API_KEY",
                **status,
            }
        if not include_external:
            return {
                "source": "通达信官方 MCP",
                "status": "unknown",
                "configured": True,
                "message": "已配置；快速检查模式未连接外部 MCP",
                **status,
            }

        tools = provider.list_tools()
        if tools:
            return {
                "source": "通达信官方 MCP",
                "status": "normal",
                "configured": True,
                "message": f"服务可用，发现 {len(tools)} 个工具",
                "tools": [tool.get("name") for tool in tools if isinstance(tool, dict)],
                **status,
            }
        return {
            "source": "通达信官方 MCP",
            "status": "warning",
            "configured": True,
            "message": "已配置，但未能列出 MCP 工具",
            **status,
        }
    except Exception as e:
        return {
            "source": "通达信官方 MCP",
            "status": "warning",
            "configured": bool(os.getenv("TDX_API_KEY")),
            "message": str(e),
        }


def _resolve_update_script() -> Path:
    return Path(__file__).resolve().parents[2] / "update_cn_data.py"


def _normalize_update_codes(codes: list[str] | None) -> list[str]:
    if not codes:
        return []
    normalized = []
    seen = set()
    for code in codes:
        try:
            qlib_code = normalize_stock_code(code, target="qlib").lower()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"股票代码格式不支持: {code}") from exc
        if qlib_code not in seen:
            seen.add(qlib_code)
            normalized.append(qlib_code)
    return normalized


def _read_instrument_codes(names: list[str], limit: int | None = None) -> list[str]:
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    codes: list[str] = []
    seen: set[str] = set()
    for name in names:
        path = data_dir / "instruments" / f"{name}.txt"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split("	")
            if not parts or not parts[0]:
                continue
            code = parts[0].lower()
            if code not in seen:
                seen.add(code)
                codes.append(code)
                if limit and len(codes) >= limit:
                    return codes
    return codes


def _get_core_update_codes(limit: int | None = 800) -> list[str]:
    """Return a priority update universe for fast daily use.

    Includes major index constituents where available plus important ETFs,
    user-facing demo symbols, pair-trading examples, and recent strategy themes.
    """
    priority = [
        "sh510050",  # 上证50ETF，用于修复/跟踪上证50相关链路
        "sh510300",
        "sh000016",  # 上证50指数；若本地无 feature 文件会被更新脚本自然跳过
        "sh600519",
        "sz000001",
        "sz300308",
        "sz300502",
        "sz300394",
        "sh600036",
        "sh601318",
    ]
    codes: list[str] = []
    seen: set[str] = set()
    for code in priority + _read_instrument_codes(["csi300", "csi500", "all"], limit=limit):
        normalized = code.lower()
        if normalized not in seen:
            seen.add(normalized)
            codes.append(normalized)
        if limit and len(codes) >= limit:
            break
    return codes


def _clear_module_caches() -> dict:
    """Clear in-process caches that can hide freshly written Qlib data."""
    cleared: list[str] = []
    failures: dict[str, str] = {}

    cache_specs = [
        ("api.etf", "_cache"),
        ("api.pair", "_pair_cache"),
        ("api.sectors", "_cache"),
    ]
    for module_name, attr_name in cache_specs:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            cache = getattr(module, attr_name, None)
            if hasattr(cache, "clear"):
                cache.clear()
                cleared.append(f"{module_name}.{attr_name}")
        except Exception as exc:
            failures[f"{module_name}.{attr_name}"] = str(exc)

    try:
        stocks_module = __import__("api.stocks", fromlist=["_full_name_cache", "_cache_loaded"])
        stocks_module._full_name_cache.clear()
        stocks_module._cache_loaded = False
        cleared.append("api.stocks._full_name_cache")
    except Exception as exc:
        failures["api.stocks._full_name_cache"] = str(exc)

    try:
        factor_utils = __import__("core.factor_utils", fromlist=["_industry_cache"])
        factor_utils._industry_cache.clear()
        cleared.append("core.factor_utils._industry_cache")
    except Exception as exc:
        failures["core.factor_utils._industry_cache"] = str(exc)

    alpha158_cache = Path.home() / ".qlib" / "alpha158_cache"
    if alpha158_cache.exists():
        try:
            import shutil

            shutil.rmtree(alpha158_cache)
            cleared.append("alpha158_cache")
        except Exception as exc:
            failures["alpha158_cache"] = str(exc)

    return {
        "cache_cleared": bool(cleared),
        "cleared": cleared,
        "cache_clear_failures": failures,
    }


def _reload_qlib_runtime() -> dict:
    """Reinitialize Qlib so D.features sees files written by the update script."""
    try:
        from main import init_qlib

        return {"qlib_reloaded": bool(init_qlib())}
    except Exception as exc:
        logger.warning(f"数据更新后刷新 Qlib 运行态失败: {exc}")
        return {"qlib_reloaded": False, "qlib_reload_error": str(exc)}


def _refresh_runtime_after_update() -> dict:
    """Refresh local runtime state after a successful data update."""
    cache_result = _clear_module_caches()
    qlib_result = _reload_qlib_runtime()
    result = {
        **cache_result,
        **qlib_result,
    }
    logger.info(f"数据更新后运行态刷新结果: {result}")
    return result


def _find_running_update() -> dict | None:
    with _tasks_lock:
        for task in _update_tasks.values():
            if task.get("status") == "running":
                return task.copy()
    try:
        data_update_task_store.init_db()
        for task in data_update_task_store.list_tasks(limit=20):
            if task.get("status") == "running":
                full_task = _get_persisted_task(task["task_id"])
                return full_task or task
    except Exception as e:
        logger.warning(f"读取持久化数据更新任务失败，回退内存状态: {e}")
    return None


def _persist_task(task_id: str, task: dict):
    data_update_task_store.init_db()
    if task.get("status") == "completed":
        data_update_task_store.set_completed(task_id, json.dumps(task, ensure_ascii=False))
    elif task.get("status") == "failed":
        data_update_task_store.set_failed(
            task_id,
            task.get("message") or task.get("error") or "数据更新失败",
            json.dumps({**task, "status": "failed"}, ensure_ascii=False),
        )
    else:
        if data_update_task_store.get_task(task_id) is None:
            data_update_task_store.create_task(task_id, json.dumps({
                "type": task.get("type"),
                "command_preview": task.get("command_preview"),
            }, ensure_ascii=False))
        data_update_task_store.set_running(
            task_id,
            int(task.get("progress") or 5),
            json.dumps(task, ensure_ascii=False),
        )


def _get_persisted_task(task_id: str) -> dict | None:
    task = data_update_task_store.get_task(task_id)
    if task is None:
        return None
    payload = {}
    if task.get("result_json"):
        try:
            payload = json.loads(task["result_json"])
        except Exception:
            payload = {}
    elif task.get("params_json"):
        try:
            payload = json.loads(task["params_json"])
        except Exception:
            payload = {}
    return {
        **payload,
        "task_id": task_id,
        "status": payload.get("status") or task.get("status"),
        "progress": payload.get("progress") if payload.get("progress") is not None else task.get("progress"),
        "message": payload.get("message") or task.get("error") or "数据更新任务运行中",
        "error": task.get("error"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def _save_task(update_task_id: str, **updates):
    with _tasks_lock:
        current = _update_tasks.get(update_task_id, {})
        current.update(updates)
        if current.get("status") == "completed" and "runtime_refresh" not in current:
            current["runtime_refresh"] = _refresh_runtime_after_update()
        _update_tasks[update_task_id] = current
        task_snapshot = current.copy()
    _persist_task(update_task_id, task_snapshot)


def _run_update_process(task_id: str, command: list[str]):
    started_at = datetime.now().isoformat()
    _save_task(
        task_id,
        status="running",
        progress=15,
        message="数据更新脚本已启动，正在写入 Qlib 数据目录",
        started_at=started_at,
    )

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _save_task(task_id, pid=process.pid, progress=30)
        stdout, stderr = process.communicate()
        finished_at = datetime.now().isoformat()

        if process.returncode == 0:
            tail = "\n".join(stdout.strip().splitlines()[-8:])
            _save_task(
                task_id,
                status="completed",
                progress=100,
                message=tail or "数据更新完成",
                stdout_tail=tail,
                stderr_tail="\n".join(stderr.strip().splitlines()[-8:]),
                finished_at=finished_at,
                returncode=process.returncode,
            )
        else:
            err_tail = "\n".join((stderr or stdout).strip().splitlines()[-8:])
            _save_task(
                task_id,
                status="failed",
                progress=100,
                message=err_tail or f"数据更新失败，退出码 {process.returncode}",
                stdout_tail="\n".join(stdout.strip().splitlines()[-8:]),
                stderr_tail=err_tail,
                finished_at=finished_at,
                returncode=process.returncode,
            )
    except Exception as e:
        logger.exception(f"数据更新任务 {task_id} 启动失败")
        _save_task(
            task_id,
            status="failed",
            progress=100,
            message=str(e),
            finished_at=datetime.now().isoformat(),
        )


def _start_update_thread(task_id: str, command: list[str]):
    thread = threading.Thread(target=_run_update_process, args=(task_id, command), daemon=True)
    thread.start()
    return thread


@router.get("/health")
async def data_health_check(include_external: bool = False):
    """
    数据健康检查 - 检查所有数据源状态

    检查项:
    - Qlib cn_data 数据目录是否存在、最后更新日期
    - 股票日线数据滞后天数
    - Baostock 行业数据服务可用性（默认不检查，避免外部网络拖慢页面）
    """
    qlib_check = _check_qlib_data()
    stocks_check = _check_stocks_data()
    adjustment_check = _check_price_adjustment_policy()
    baostock_check = _check_baostock_industry() if include_external else _baostock_skipped_status()
    tdx_check = _check_tdx_mcp(include_external)

    # 总体状态
    statuses = [
        qlib_check.get("status", "error"),
        stocks_check.get("status", "error"),
        adjustment_check.get("status", "warning"),
        baostock_check.get("status", "error"),
        tdx_check.get("status", "unknown"),
    ]
    if "error" in statuses:
        overall = "degraded"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "healthy"

    logger.info(f"数据健康检查: 总体={overall}, Qlib={qlib_check.get('status')}, "
                f"Baostock={baostock_check.get('status')}")

    return {
        "overall_status": overall,
        "checked_at": datetime.now().isoformat(),
        "sources": {
            "qlib": qlib_check,
            "price_adjustment": adjustment_check,
            "stocks": {
                **stocks_check,
                "etf": stocks_check,
                "index": {
                    "total": 12,
                    "last_date": stocks_check.get("last_date", ""),
                    "lag_days": stocks_check.get("lag_days", -1),
                    "status": stocks_check.get("status", "error"),
                },
            },
            "baostock_industry": baostock_check,
            "tdx_mcp": tdx_check,
        },
    }


def _freshness_module_matrix(stocks_check: dict, adjustment_check: dict) -> list[dict]:
    qlib_date = stocks_check.get("last_date") or ""
    sample_date = stocks_check.get("sample_latest_date") or qlib_date
    coverage = stocks_check.get("sample_latest_coverage", 0)
    canonical_adjustment = "front_adjusted"
    return [
        {
            "key": "quote",
            "name": "行情分析",
            "primary_source": "qlib",
            "uses_qlib_daily_bar": True,
            "latest_date": qlib_date,
            "sample_latest_date": sample_date,
            "coverage": coverage,
            "price_adjustment": canonical_adjustment,
            "freshness_policy": "以本地 Qlib 日线为准",
        },
        {
            "key": "backtest",
            "name": "模型回测 / 因子 / 深度学习",
            "primary_source": "qlib",
            "uses_qlib_daily_bar": True,
            "latest_date": qlib_date,
            "sample_latest_date": sample_date,
            "coverage": coverage,
            "price_adjustment": canonical_adjustment,
            "freshness_policy": "训练、测试、回测统一读取 Qlib D.features",
        },
        {
            "key": "screening",
            "name": "盘后选股 / 均值回归 / 交易计划",
            "primary_source": "qlib",
            "uses_qlib_daily_bar": True,
            "latest_date": qlib_date,
            "sample_latest_date": sample_date,
            "coverage": coverage,
            "price_adjustment": canonical_adjustment,
            "freshness_policy": "候选筛选与 ATR/止损计划统一使用 Qlib 日线",
        },
        {
            "key": "pair",
            "name": "配对交易",
            "primary_source": "qlib",
            "uses_qlib_daily_bar": True,
            "latest_date": qlib_date,
            "sample_latest_date": sample_date,
            "coverage": coverage,
            "price_adjustment": canonical_adjustment,
            "freshness_policy": "价差和相关性统一使用 Qlib 收盘价",
        },
        {
            "key": "risk_portfolio",
            "name": "风险管理 / 组合优化",
            "primary_source": "qlib_with_external_fallback",
            "uses_qlib_daily_bar": True,
            "latest_date": qlib_date,
            "sample_latest_date": sample_date,
            "coverage": coverage,
            "price_adjustment": canonical_adjustment,
            "freshness_policy": "优先 Qlib；Qlib 不可用时个别接口会回退 yfinance",
        },
        {
            "key": "macro",
            "name": "宏观策略 / 新闻 / 部分行业板块",
            "primary_source": "external",
            "uses_qlib_daily_bar": False,
            "latest_date": "external_provider_dependent",
            "sample_latest_date": "external_provider_dependent",
            "coverage": None,
            "price_adjustment": "not_applicable_or_provider_default",
            "freshness_policy": "来自 akshare/yfinance/新闻源，不受 Qlib 更新按钮完全控制",
        },
    ]


@router.get("/freshness")
async def data_freshness_matrix():
    """Return module-level data-source freshness and price-adjustment policy."""
    stocks_check = _check_stocks_data()
    adjustment_check = _check_price_adjustment_policy()
    coverage = stocks_check.get("sample_latest_coverage", 0)
    modules = _freshness_module_matrix(stocks_check, adjustment_check)
    return {
        "checked_at": datetime.now().isoformat(),
        "canonical_price_adjustment": "front_adjusted",
        "canonical_price_adjustment_label": "前复权/可比复权价",
        "policy_summary": "全链路研究、筛选、回测、风险和交易计划尽量统一使用 Qlib 前复权可比日线；实盘成交价需另看未复权实时行情。",
        "coverage": {
            "representative_latest_date": stocks_check.get("last_date", ""),
            "sample_latest_date": stocks_check.get("sample_latest_date", ""),
            "sample_latest_coverage": coverage,
            "status": "complete" if coverage == 1 else "partial",
        },
        "adjustment_check": adjustment_check,
        "modules": modules,
        "warnings": [
            "当前更新按钮主要更新 Qlib 股票日线；ETF/指数/宏观/新闻等外部源不一定同步刷新。",
            "若 sample_latest_coverage 小于 1，说明只有部分股票到了最新交易日，回测和筛选应优先使用快速核心池或指定标的更新。",
        ],
    }


@router.get("/logs")
async def data_update_logs(include_external: bool = False):
    """
    数据更新日志 — 返回实际数据源状态（非硬编码）

    基于 Qlib 日历文件和 Baostock 服务可用性生成真实数据状态报告。
    """
    qlib_check = _check_qlib_data()
    stocks_check = _check_stocks_data()
    adjustment_check = _check_price_adjustment_policy()
    baostock_check = _check_baostock_industry() if include_external else _baostock_skipped_status()
    tdx_check = _check_tdx_mcp(include_external)

    now = datetime.now()

    logs = []

    # Qlib 数据源状态
    qlib_status = qlib_check.get("status", "error")
    if qlib_status == "normal":
        logs.append({
            "type": "success",
            "title": "Qlib 数据源状态正常",
            "detail": f"最后交易日: {qlib_check.get('last_date', 'N/A')}, 特征文件: {qlib_check.get('n_features', 0)} 个",
            "time": now.strftime("%Y-%m-%d %H:%M"),
        })
    else:
        logs.append({
            "type": qlib_status,
            "title": f"Qlib 数据源异常",
            "detail": qlib_check.get("message", "未知"),
            "time": now.strftime("%Y-%m-%d %H:%M"),
        })

    # 股票数据状态
    stock_status = stocks_check.get("status", "error")
    logs.append({
        "type": stock_status if stock_status == "normal" else "warning",
        "title": f"股票日线数据{'正常' if stock_status == 'normal' else '需关注'}",
        "detail": f"成分股 {stocks_check.get('total', 0)} 只, 最后交易日: {stocks_check.get('last_date', 'N/A')}",
        "time": now.strftime("%Y-%m-%d %H:%M"),
    })

    logs.append({
        "type": "success" if adjustment_check.get("status") == "normal" else "warning",
        "title": "复权口径诊断",
        "detail": adjustment_check.get("message", "未能判断复权口径"),
        "time": now.strftime("%Y-%m-%d %H:%M"),
    })

    # Baostock 行业数据
    bao_status = baostock_check.get("status", "error")
    logs.append({
        "type": bao_status if bao_status == "normal" else "warning",
        "title": f"Baostock 行业数据{'可用' if bao_status == 'normal' else '不可用'}",
        "detail": baostock_check.get("message", "未知"),
        "time": now.strftime("%Y-%m-%d %H:%M"),
    })

    tdx_status = tdx_check.get("status", "unknown")
    logs.append({
        "type": "success" if tdx_status == "normal" else "warning",
        "title": "通达信官方 MCP",
        "detail": tdx_check.get("message", "未知"),
        "time": now.strftime("%Y-%m-%d %H:%M"),
    })

    return {
        "logs": logs,
        "checked_at": now.isoformat(),
    }


@router.post("/update", dependencies=[Depends(require_data_update_key)])
async def start_data_update(request: DataUpdateRequest):
    """启动 Qlib cn_data 后台增量更新任务。"""
    if request.type in {"etf", "index"}:
        raise HTTPException(
            status_code=400,
            detail="当前后端只支持 Qlib 股票日线数据更新；ETF/指数尚未接入独立更新脚本。",
        )

    running = _find_running_update()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"已有数据更新任务正在运行: {running.get('task_id')}",
        )

    script_path = _resolve_update_script()
    if not script_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"数据更新脚本不存在: {script_path}",
        )

    start_date = request.start_date or _get_stock_latest_trade_date() or "2020-09-26"
    effective_codes = _normalize_update_codes(request.codes)
    if request.type == "core" and not effective_codes:
        effective_codes = _get_core_update_codes()

    command = [sys.executable, str(script_path), "--start", start_date]
    if request.end_date:
        command.extend(["--end", request.end_date])
    if request.max_stocks:
        command.extend(["--max", str(request.max_stocks)])
    for code in effective_codes:
        command.extend(["--code", code])
    if request.rebuild_stale:
        command.append("--rebuild-stale")
    if request.overwrite_existing:
        command.append("--overwrite-existing")

    task_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    _save_task(
        task_id,
        task_id=task_id,
        type=request.type,
        status="running",
        progress=5,
        message="数据更新任务已排队",
        started_at=now,
        command_preview=" ".join(command),
    )

    response = {
        "task_id": task_id,
        "status": "running",
        "progress": 5,
        "mode": request.type,
        "target_codes": len(effective_codes),
        "message": "数据更新任务已启动",
    }
    _start_update_thread(task_id, command)
    return response


@router.get("/update/{task_id}")
async def get_data_update_progress(task_id: str):
    """查询数据更新任务状态。"""
    with _tasks_lock:
        task = _update_tasks.get(task_id)
        if task is not None:
            return task.copy()

    persisted_task = _get_persisted_task(task_id)
    if persisted_task is not None:
        return persisted_task

    raise HTTPException(status_code=404, detail="数据更新任务不存在")
