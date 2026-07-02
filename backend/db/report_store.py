"""
智能体报告持久化存储（SQLite）

替代 agent_debate.py 中的内存 _report_store dict。
"""
import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime

from loguru import logger

DB_PATH = Path.home() / ".qlib" / "agent_reports.db"
TTL_SECONDS = 7 * 24 * 3600  # 7 天自动清理


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_reports (
            task_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            report_json TEXT,
            error TEXT,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def save_report(task_id: str, code: str, status: str, report: dict | None = None, error: str | None = None):
    """保存或更新报告"""
    conn = _get_db()
    report_json = json.dumps(report, ensure_ascii=False) if report else None
    created_at = time.time()

    conn.execute("""
        INSERT OR REPLACE INTO agent_reports (task_id, code, status, report_json, error, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (task_id, code, status, report_json, error, created_at))
    conn.commit()
    conn.close()
    logger.debug(f"报告已保存: {task_id} status={status}")


def get_report(task_id: str) -> dict | None:
    """获取报告"""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM agent_reports WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    result = {
        "task_id": row["task_id"],
        "code": row["code"],
        "status": row["status"],
    }
    if row["report_json"]:
        try:
            result["report"] = json.loads(row["report_json"])
        except json.JSONDecodeError:
            result["report"] = {}
    if row["error"]:
        result["error"] = row["error"]

    return result


def get_history(code: str, limit: int = 10) -> list:
    """获取股票历史分析记录"""
    conn = _get_db()
    rows = conn.execute(
        "SELECT task_id, status, report_json, created_at FROM agent_reports WHERE code = ? ORDER BY created_at DESC LIMIT ?",
        (code, limit),
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        entry = {
            "task_id": row["task_id"],
            "status": row["status"],
            "created_at": datetime.fromtimestamp(row["created_at"]).isoformat(),
        }
        if row["report_json"]:
            try:
                report = json.loads(row["report_json"])
                # 只返回摘要字段
                if "pm_decision" in report:
                    entry["rating"] = report["pm_decision"].get("rating", "?")
                    entry["thesis"] = report["pm_decision"].get("thesis", "")[:200]
            except json.JSONDecodeError:
                pass
        results.append(entry)

    return results


def list_reports(limit: int = 50) -> list[dict]:
    """获取最近的智能体分析报告。"""
    conn = _get_db()
    rows = conn.execute(
        "SELECT task_id, code, status, report_json, error, created_at FROM agent_reports ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        entry = {
            "task_id": row["task_id"],
            "code": row["code"],
            "status": row["status"],
            "error": row["error"],
            "created_at": datetime.fromtimestamp(row["created_at"]).isoformat(),
            "updated_at": datetime.fromtimestamp(row["created_at"]).isoformat(),
        }
        if row["report_json"]:
            try:
                report = json.loads(row["report_json"])
                if "pm_decision" in report:
                    entry["rating"] = report["pm_decision"].get("rating", "?")
                    entry["thesis"] = report["pm_decision"].get("thesis", "")[:200]
            except json.JSONDecodeError:
                pass
        results.append(entry)

    return results


def cleanup_old_reports():
    """清理过期报告"""
    cutoff = time.time() - TTL_SECONDS
    conn = _get_db()
    conn.execute("DELETE FROM agent_reports WHERE created_at < ?", (cutoff,))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted > 0:
        logger.info(f"清理了 {deleted} 条过期智能体报告")
