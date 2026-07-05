"""
持仓管理数据库 — 存储用户当前持仓和买入记录
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger


class PositionStore:
    """持仓 SQLite 持久化存储，单用户场景无需线程锁"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path.home() / ".qlib" / "positions.db")
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT DEFAULT "",
                    shares INTEGER NOT NULL DEFAULT 0,
                    cost_price REAL NOT NULL DEFAULT 0.0,
                    stop_loss_price REAL DEFAULT NULL,
                    buy_date TEXT DEFAULT "",
                    notes TEXT DEFAULT "",
                    created_at TEXT DEFAULT (datetime("now","localtime")),
                    updated_at TEXT DEFAULT (datetime("now","localtime"))
                )
            """)
            conn.commit()
            logger.info(f"PositionStore 初始化完成: {self.db_path}")
        finally:
            conn.close()

    def list_all(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM positions ORDER BY buy_date DESC"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_by_code(self, code: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM positions WHERE code = ?", (code,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def upsert(self, code: str, name: str, shares: int, cost_price: float,
               stop_loss_price: Optional[float] = None,
               buy_date: str = "", notes: str = "") -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM positions WHERE code = ?", (code,)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE positions SET name=?, shares=?, cost_price=?,
                    stop_loss_price=?, buy_date=?, notes=?, updated_at=?
                    WHERE code=?
                """, (name, shares, cost_price, stop_loss_price,
                      buy_date, notes, now, code))
            else:
                conn.execute("""
                    INSERT INTO positions (code, name, shares, cost_price,
                    stop_loss_price, buy_date, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (code, name, shares, cost_price, stop_loss_price,
                      buy_date, notes, now, now))
            conn.commit()
            return self.get_by_code(code) or {}
        finally:
            conn.close()

    def delete(self, code: str) -> bool:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM positions WHERE code = ?", (code,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_all(self) -> int:
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM positions")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# 全局单例
position_store = PositionStore()
