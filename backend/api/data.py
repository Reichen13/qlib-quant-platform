"""
数据健康检查 API - 数据源状态监控与异常告警
"""

import os
import json
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


class DataUpdateRequest(BaseModel):
    """数据更新请求"""

    type: Literal["stocks", "all", "etf", "index"] = Field(default="stocks")
    start_date: str | None = Field(default=None, description="起始日期 YYYY-MM-DD，默认从 Qlib 最新日期开始")
    end_date: str | None = Field(default=None, description="结束日期 YYYY-MM-DD，默认到今天")
    max_stocks: int | None = Field(default=None, ge=1, le=5000, description="最多更新多少只股票，测试时可填较小值")
    codes: list[str] | None = Field(default=None, description="可选：只更新/修复指定股票代码")
    rebuild_stale: bool = Field(default=False, description="Repair existing stale zero/NaN OHLC rows")


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
        if (
            code.startswith("sh6")
            or code.startswith("sz0")
            or code.startswith("sz3")
            or code.startswith("bj4")
            or code.startswith("bj8")
            or code.startswith("bj920")
        ):
            codes.add(code)
    return {"total": len(codes)}


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
    baostock_check = _check_baostock_industry() if include_external else _baostock_skipped_status()

    # 总体状态
    statuses = [
        qlib_check.get("status", "error"),
        stocks_check.get("status", "error"),
        baostock_check.get("status", "error"),
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
        },
    }


@router.get("/logs")
async def data_update_logs(include_external: bool = False):
    """
    数据更新日志 — 返回实际数据源状态（非硬编码）

    基于 Qlib 日历文件和 Baostock 服务可用性生成真实数据状态报告。
    """
    qlib_check = _check_qlib_data()
    stocks_check = _check_stocks_data()
    baostock_check = _check_baostock_industry() if include_external else _baostock_skipped_status()

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

    # Baostock 行业数据
    bao_status = baostock_check.get("status", "error")
    logs.append({
        "type": bao_status if bao_status == "normal" else "warning",
        "title": f"Baostock 行业数据{'可用' if bao_status == 'normal' else '不可用'}",
        "detail": baostock_check.get("message", "未知"),
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
    command = [sys.executable, str(script_path), "--start", start_date]
    if request.end_date:
        command.extend(["--end", request.end_date])
    if request.max_stocks:
        command.extend(["--max", str(request.max_stocks)])
    for code in _normalize_update_codes(request.codes):
        command.extend(["--code", code])
    if request.rebuild_stale:
        command.append("--rebuild-stale")

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
        "message": "数据更新任务已启动",
    }
    _start_update_thread(task_id, command)
    return response


@router.get("/update/{task_id}")
async def get_data_update_progress(task_id: str):
    """查询数据更新任务状态。"""
    with _tasks_lock:
        task = _update_tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="数据更新任务不存在")
        return task.copy()
