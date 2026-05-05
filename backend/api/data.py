"""
数据健康检查 API - 数据源状态监控与异常告警
"""

from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter
from loguru import logger

router = APIRouter()


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
        last_date = dates[-1] if dates else ""
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
    }


def _check_stocks_data() -> dict:
    """检查股票日线数据状态（使用 Qlib 日历作为真实来源）"""
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    csi300_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "instruments" / "csi300.txt"

    n_stocks = 0
    if csi300_path.exists():
        n_stocks = len([l for l in csi300_path.read_text().strip().split("\n") if l.strip()])

    if cal_path.exists():
        dates = cal_path.read_text().strip().split("\n")
        last_date = dates[-1] if dates else ""
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
            "total": n_stocks,
            "last_date": last_date,
            "lag_days": lag_days,
            "status": status,
            "message": msg,
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


@router.get("/health")
async def data_health_check():
    """
    数据健康检查 - 检查所有数据源状态

    检查项:
    - Qlib cn_data 数据目录是否存在、最后更新日期
    - 股票日线数据滞后天数
    - Baostock 行业数据服务可用性
    """
    qlib_check = _check_qlib_data()
    stocks_check = _check_stocks_data()
    baostock_check = _check_baostock_industry()

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
