"""
回测任务 SQLite 持久化存储
替换内存字典 backtest_tasks，进程重启不丢失数据
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

DEFAULT_DB_PATH = Path.home() / ".qlib" / "backtest_tasks.db"


class TaskStore:
    """回测任务持久化存储"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self._db_path = str(db_path)
        self._lock = threading.Lock()

    def init_db(self) -> None:
        """初始化数据库表"""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    params_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created
                ON backtest_tasks(created_at DESC)
            """)
            conn.commit()
            conn.close()
        logger.info(f"TaskStore 初始化完成: {self._db_path}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_task(self, task_id: str, params_json: str = "{}") -> None:
        now = self._now()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO backtest_tasks (task_id, status, progress, params_json, created_at, updated_at) VALUES (?, 'running', 5, ?, ?, ?)",
                (task_id, params_json, now, now),
            )
            conn.commit()
            conn.close()

    def update_progress(self, task_id: str, progress: int) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE backtest_tasks SET progress = ?, updated_at = ? WHERE task_id = ?",
                (progress, self._now(), task_id),
            )
            conn.commit()
            conn.close()

    def set_completed(self, task_id: str, result_json: str) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE backtest_tasks SET status = 'completed', progress = 100, result_json = ?, updated_at = ? WHERE task_id = ?",
                (result_json, self._now(), task_id),
            )
            conn.commit()
            conn.close()

    def set_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE backtest_tasks SET status = 'failed', progress = 0, error = ?, updated_at = ? WHERE task_id = ?",
                (error, self._now(), task_id),
            )
            conn.commit()
            conn.close()

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM backtest_tasks WHERE task_id = ?", (task_id,)).fetchone()
            conn.close()
            if row is None:
                return None
            return dict(row)

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM backtest_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            conn.close()

    def list_tasks(self, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT task_id, status, progress, params_json, error, created_at, updated_at FROM backtest_tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def cleanup_old(self, max_age_hours: int = 168) -> int:
        """清理超过指定时间的旧任务"""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            count = conn.execute("DELETE FROM backtest_tasks WHERE created_at < ?", (cutoff,)).rowcount
            conn.commit()
            conn.close()
        if count:
            logger.info(f"清理了 {count} 个过期任务")
        return count


# 全局单例
task_store = TaskStore()
