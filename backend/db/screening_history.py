"""
Screening history store - Stage 5
SQLite-backed persistence for post-close screening recommendations.
Stores top-N buyable stocks per run for rolling performance validation.
"""
import sqlite3
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".qlib" / "screening_history.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screening_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL UNIQUE,
            top_buyable_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            win_rate_verified REAL,
            avg_t5_return REAL,
            verified_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_run(run_date: str, buyable_top5: list[dict]) -> int:
    """Save top-5 buyable stocks from a screening run. Returns row id."""
    init_db()
    conn = _get_db()
    top_json = json.dumps(buyable_top5, ensure_ascii=False)
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO screening_history (run_date, top_buyable_json, created_at) VALUES (?, ?, ?)",
        (run_date, top_json, now),
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return row_id


def get_recent_runs(limit: int = 20) -> list[dict]:
    """Get the most recent screening runs (newest first)."""
    init_db()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM screening_history ORDER BY run_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_n_runs(n: int = 3, min_age_days: int = 5) -> list[dict]:
    """Get last N runs that are at least min_age_days old (for verified T+N returns)."""
    init_db()
    conn = _get_db()
    cutoff = (date.today().isoformat())
    rows = conn.execute(
        "SELECT * FROM screening_history WHERE run_date <= ? ORDER BY run_date DESC LIMIT ?",
        (cutoff, n),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_verification(run_date: str, win_rate: float, avg_t5_return: float):
    """Update verified win rate and T+5 return for a historical run."""
    init_db()
    conn = _get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE screening_history SET win_rate_verified=?, avg_t5_return=?, verified_at=? WHERE run_date=?",
        (round(win_rate, 4), round(avg_t5_return, 4), now, run_date),
    )
    conn.commit()
    conn.close()
