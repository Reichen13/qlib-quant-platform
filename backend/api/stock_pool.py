"""
智能股票池 API

- GET    /api/stock-pool/list        列表
- POST   /api/stock-pool/create      创建
- GET    /api/stock-pool/{id}        详情
- POST   /api/stock-pool/{id}/refresh 刷新
- DELETE /api/stock-pool/{id}        删除
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from loguru import logger

from core.stock_pool import (
    _get_db,
    _init_db,
    PoolDefinition,
    get_engine,
)

router = APIRouter()


@router.get("/list")
async def list_pools():
    """获取已保存的股票池列表"""
    conn = _get_db()
    pools = conn.execute(
        "SELECT id, name, config_json, created_at, updated_at FROM pools ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()

    return {
        "total": len(pools),
        "pools": [
            {
                "id": p["id"],
                "name": p["name"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
            }
            for p in pools
        ],
    }


@router.post("/create")
async def create_pool(definition: PoolDefinition):
    """创建新股票池"""
    pool_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    config_json = json.dumps(definition.model_dump(), ensure_ascii=False)

    conn = _get_db()
    conn.execute(
        "INSERT INTO pools (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (pool_id, definition.name, config_json, now, now),
    )
    conn.commit()
    conn.close()

    logger.info(f"股票池已创建: {definition.name} ({pool_id})")

    return {
        "id": pool_id,
        "name": definition.name,
        "created_at": now,
    }


@router.get("/{pool_id}")
async def get_pool(pool_id: str):
    """获取股票池详情"""
    conn = _get_db()
    pool = conn.execute("SELECT * FROM pools WHERE id = ?", (pool_id,)).fetchone()
    if not pool:
        conn.close()
        raise HTTPException(status_code=404, detail="股票池不存在")

    # 最新历史
    history = conn.execute(
        "SELECT * FROM pool_history WHERE pool_id = ? ORDER BY date DESC LIMIT 1",
        (pool_id,),
    ).fetchone()

    conn.close()

    result = {
        "id": pool["id"],
        "name": pool["name"],
        "config": json.loads(pool["config_json"]),
        "created_at": pool["created_at"],
        "updated_at": pool["updated_at"],
        "latest_constituents": (
            json.loads(history["constituents_json"]) if history else []
        ),
        "latest_refresh": history["date"] if history else None,
    }
    return result


@router.post("/{pool_id}/refresh")
async def refresh_pool(pool_id: str, allow_untrusted_data: bool = False):
    """刷新股票池筛选。数据尾部复权不可信时默认拒绝，避免噪声选股。"""
    try:
        from core.data_trust import require_data_trusted

        require_data_trusted(action="stock_pool_refresh", allow_untrusted=allow_untrusted_data)
        engine = get_engine()
        result = engine.refresh_pool(pool_id)
        logger.info(f"股票池已刷新: {pool_id}, {len(result['constituents'])} 只")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{pool_id}")
async def delete_pool(pool_id: str):
    """删除股票池"""
    conn = _get_db()
    conn.execute("DELETE FROM pool_history WHERE pool_id = ?", (pool_id,))
    conn.execute("DELETE FROM pools WHERE id = ?", (pool_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "id": pool_id}
