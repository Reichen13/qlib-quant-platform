"""System diagnostics and task-center API."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

try:
    from db.task_store import task_store as backtest_task_store
except Exception:  # pragma: no cover - startup fallback only
    backtest_task_store = None

try:
    from db.report_store import list_reports as list_agent_reports
except Exception:  # pragma: no cover - startup fallback only
    list_agent_reports = None

router = APIRouter()


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _qlib_data_status() -> dict[str, Any]:
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    calendar_path = data_dir / "calendars" / "day.txt"
    features_dir = data_dir / "features"
    instruments_dir = data_dir / "instruments"
    latest_calendar_date = None

    if calendar_path.exists():
        try:
            lines = [line.strip() for line in calendar_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            latest_calendar_date = lines[-1] if lines else None
        except Exception:
            latest_calendar_date = None

    feature_count = 0
    if features_dir.exists():
        try:
            feature_count = sum(1 for item in features_dir.iterdir() if item.is_dir())
        except Exception:
            feature_count = 0

    exists = data_dir.exists() and calendar_path.exists() and features_dir.exists()
    return {
        "path": str(data_dir),
        "exists": exists,
        "calendar_exists": calendar_path.exists(),
        "features_exists": features_dir.exists(),
        "instruments_exists": instruments_dir.exists(),
        "latest_calendar_date": latest_calendar_date,
        "feature_count": feature_count,
        "status": "healthy" if exists else "warning",
    }


def environment_check() -> dict[str, Any]:
    dependencies = {
        "fastapi": _module_available("fastapi"),
        "uvicorn": _module_available("uvicorn"),
        "pyqlib": _module_available("qlib"),
        "pandas": _module_available("pandas"),
        "numpy": _module_available("numpy"),
        "lightgbm": _module_available("lightgbm"),
        "gym": _module_available("gym"),
        "cvxpy": _module_available("cvxpy"),
        "langchain_openai": _module_available("langchain_openai"),
    }
    qlib_data = _qlib_data_status()
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    frontend = {
        "path": str(frontend_dir),
        "exists": frontend_dir.exists(),
        "package_json": (frontend_dir / "package.json").exists(),
        "node_modules": (frontend_dir / "node_modules").exists(),
    }

    warnings = []
    if not qlib_data["exists"]:
        warnings.append("Qlib 数据目录不完整")
    missing_dependencies = [name for name, ok in dependencies.items() if not ok]
    if missing_dependencies:
        warnings.append(f"缺少 Python 依赖: {', '.join(missing_dependencies)}")
    if not frontend["node_modules"]:
        warnings.append("frontend/node_modules 不存在，请先运行 npm install")

    return {
        "overall_status": "healthy" if not warnings else "warning",
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "dependencies": dependencies,
        "qlib_data": qlib_data,
        "frontend": frontend,
        "warnings": warnings,
    }


def _parse_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _normalize_task(row: dict[str, Any], task_type: str) -> dict[str, Any]:
    task_id = row.get("task_id")
    status = row.get("status")
    task = {
        "task_id": task_id,
        "type": task_type,
        "status": status,
        "progress": row.get("progress", 0),
        "params": _parse_json(row.get("params_json")),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "detail_url": None,
        "report_url": None,
    }
    if task_type == "backtest" and task_id:
        task["detail_url"] = f"/api/backtest/status/{task_id}"
        if status == "completed":
            task["report_url"] = f"/api/backtest/report/{task_id}.md"
    return task


def _normalize_agent_report(row: dict[str, Any]) -> dict[str, Any]:
    task_id = row.get("task_id")
    return {
        "task_id": task_id,
        "type": "agent_report",
        "status": row.get("status"),
        "progress": 100 if row.get("status") == "completed" else 0,
        "params": {
            "code": row.get("code"),
            "rating": row.get("rating"),
            "thesis": row.get("thesis"),
        },
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at") or row.get("created_at"),
        "detail_url": f"/api/agent/report/{task_id}" if task_id else None,
        "report_url": f"/api/agent/report/{task_id}" if task_id and row.get("status") == "completed" else None,
    }


def task_center(limit: int = 50) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    if backtest_task_store is not None:
        try:
            tasks.extend(_normalize_task(row, "backtest") for row in backtest_task_store.list_tasks(limit))
        except Exception as exc:
            tasks.append({
                "task_id": "backtest-task-store-error",
                "type": "system",
                "status": "failed",
                "progress": 0,
                "params": None,
                "error": str(exc),
                "created_at": None,
                "updated_at": None,
            })

    if list_agent_reports is not None:
        try:
            tasks.extend(_normalize_agent_report(row) for row in list_agent_reports(limit))
        except Exception as exc:
            tasks.append({
                "task_id": "agent-report-store-error",
                "type": "system",
                "status": "failed",
                "progress": 0,
                "params": None,
                "error": str(exc),
                "created_at": None,
                "updated_at": None,
            })

    tasks.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return {
        "total": len(tasks),
        "tasks": tasks[:limit],
    }


@router.get("/environment")
async def get_environment_check():
    return environment_check()


@router.get("/tasks")
async def get_task_center(limit: int = 50):
    return task_center(limit=limit)
