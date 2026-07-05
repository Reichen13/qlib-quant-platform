"""
Qlib 量化平台 - FastAPI 后端
提供 REST API 供前端调用
"""

import os
import sys
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import uvicorn

os.environ.setdefault('MLFLOW_ALLOW_FILE_STORE', 'true')

# 添加路径以导入项目模块
project_root = str(Path(__file__).parent.parent)
backend_dir = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# ── 日志配置 ──
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)

# ── Qlib 初始化状态 ──
qlib_initialized = False
qlib_init_error = None


def init_qlib():
    """初始化 Qlib"""
    global qlib_initialized, qlib_init_error
    try:
        import qlib
        from qlib.config import REG_CN

        # 修复 Qlib 0.9.6 与 joblib 1.5+ 的兼容性问题
        from core.compat import fix_parallel_ext
        fix_parallel_ext()

        data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
        if not data_dir.exists():
            raise FileNotFoundError(f"Qlib 数据目录不存在: {data_dir}")
        # 防护：绝不加载旧备份目录（全量重建后旧 cn_data 改名为备份，
        # 其中的旧口径 bin 是被污染的，“有历史但错的”比“没历史”更危险）
        if "cn_data_backup" in data_dir.name:
            raise RuntimeError(
                f"拒绝加载旧备份目录: {data_dir}；"
                f"请确认 provider_uri 指向当前 cn_data 而非备份"
            )

        qlib.init(provider_uri=str(data_dir), region=REG_CN)
        qlib_initialized = True
        logger.info(f"Qlib 初始化成功，数据目录: {data_dir}")
        return True
    except Exception as e:
        qlib_init_error = str(e)
        logger.error(f"Qlib 初始化失败: {e}")
        return False


def _preload_industry_mapping_background():
    """后台预热行业映射，避免 Baostock 网络请求阻塞服务启动。"""
    def worker():
        try:
            from qlib.data import D
            instruments = D.instruments("csi300")
            codes = D.list_instruments(instruments, as_list=True)
            from core.factor_utils import load_industry_mapping
            load_industry_mapping(codes)
            logger.info(f"✅ 行业映射后台预加载完成: {len(codes)} 只 CSI300 成分股")
        except Exception as e:
            logger.warning(f"⚠️ 行业映射后台预加载跳过（非致命）: {e}")

    thread = threading.Thread(
        target=worker,
        name="industry-mapping-preload",
        daemon=True,
    )
    thread.start()
    logger.info("行业映射预加载已转入后台，不阻塞服务启动")




# ── 应用生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的处理"""
    # 启动时初始化 Qlib
    logger.info("🚀 FastAPI 服务启动中...")
    init_qlib()

    # 导入路由
    from api import (
        stocks, hot, quote, factors, backtest, etf,
        pair, mean_reversion, financials, industry, index, sectors, risk, portfolio,
        macro, data, dashboard, news_analysis, ai_strategy, agent_debate,
        dl_models, stock_pool, llm_config, screening, trade_plan, system, positions,
    )

    app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
    app.include_router(hot.router, prefix="/api/hot", tags=["hot"])
    app.include_router(quote.router, prefix="/api/quote", tags=["quote"])
    app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
    app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
    app.include_router(etf.router, prefix="/api/etf", tags=["etf"])
    app.include_router(pair.router, prefix="/api/pair", tags=["pair"])
    app.include_router(mean_reversion.router, prefix="/api/mean-reversion", tags=["mean-reversion"])
    app.include_router(financials.router, prefix="/api/financials", tags=["financials"])
    app.include_router(industry.router, prefix="/api/industry", tags=["industry"])
    app.include_router(index.router, prefix="/api/index", tags=["index"])
    app.include_router(sectors.router, prefix="/api/sectors", tags=["sectors"])
    app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
    app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
    app.include_router(macro.router, prefix="/api/macro", tags=["macro"])
    app.include_router(data.router, prefix="/api/data", tags=["data"])
    app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(news_analysis.router, prefix="/api/news", tags=["news"])
    app.include_router(ai_strategy.router, prefix="/api/ai-strategy", tags=["ai-strategy"])
    app.include_router(agent_debate.router, prefix="/api/agent", tags=["agent"])
    app.include_router(dl_models.router, prefix="/api/dl-models", tags=["dl-models"])
    app.include_router(stock_pool.router, prefix="/api/stock-pool", tags=["stock-pool"])
    app.include_router(screening.router, prefix="/api/screening", tags=["screening"])
    app.include_router(trade_plan.router, prefix="/api/trade-plan", tags=["trade-plan"])
    app.include_router(llm_config.router, tags=["llm"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])

    logger.info("✅ 所有路由已注册")

    # ── 初始化数据库 ──
    try:
        from db.task_store import task_store
        task_store.init_db()
        interrupted_count = backtest.mark_interrupted_backtest_tasks()
        if interrupted_count:
            logger.warning(f"已标记 {interrupted_count} 个中断的回测任务，请重新提交")
    except Exception as e:
        logger.warning(f"⚠️ 数据库初始化跳过（非致命）: {e}")

    # ── 预加载行业映射（后台执行，避免 Baostock 慢请求阻塞健康检查）──
    _preload_industry_mapping_background()

    yield

    # 关闭时清理
    logger.info("🛑 FastAPI 服务关闭")


# ── 创建 FastAPI 应用 ──
app = FastAPI(
    title="Qlib 量化平台 API",
    description="A股量化分析平台后端接口",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Docker 部署时通过 Nginx 代理，需要允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 根路由 ──
@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": "Qlib 量化平台 API",
        "version": "1.0.0",
        "status": "running",
        "qlib_initialized": qlib_initialized,
        "qlib_error": qlib_init_error,
        "timestamp": datetime.now().isoformat(),
    }


# ── 健康检查 ──
@app.get("/health")
async def health():
    """健康检查端点"""
    return {
        "status": "healthy" if qlib_initialized else "degraded",
        "qlib": "initialized" if qlib_initialized else "not_initialized",
        "timestamp": datetime.now().isoformat(),
    }


# ── 全局异常处理 ──
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(f"未捕获的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "内部服务器错误",
            "message": str(exc) if os.getenv("DEBUG") else "请联系管理员",
        }
    )


# ── 启动服务 ──
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
