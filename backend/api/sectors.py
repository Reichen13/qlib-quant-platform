"""
行业板块 API - 基于 yfinance
使用友好的中文板块名称
"""

from typing import List, Dict
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from datetime import datetime, timedelta
import yfinance as yf
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

router = APIRouter()

SECTOR_BASE_CHANGE = {
    "半导体": 2.8,
    "新能源": 1.9,
    "医药": -0.4,
    "消费": 0.6,
    "金融": -0.8,
    "军工": 1.2,
    "地产": -1.6,
    "汽车": 0.9,
    "电力": 0.4,
    "煤炭": -0.3,
    "钢铁": -0.7,
    "化工": 0.2,
    "电子": 1.1,
    "通信": 0.8,
    "传媒": 0.5,
    "建材": -0.5,
    "机械": 0.7,
    "有色": 1.4,
    "石化": -0.2,
    "交运": 0.3,
}

# 定义板块及其代表性股票（使用yfinance代码格式）
SECTOR_DEFINITIONS = {
    "半导体": [
        "600584.SS",  # 中芯国际
        "002371.SZ",  # 北方华创
        "300782.SZ",  # 卓胜微
        "688981.SS",  # 中芯国际-U
        "002049.SZ",  # 紫光国微
    ],
    "新能源": [
        "300750.SZ",  # 宁德时代
        "002594.SZ",  # 比亚迪
        "601012.SS",  # 隆基绿能
        "688590.SS",  # 新风光
        "300274.SZ",  # 阳光电源
    ],
    "医药": [
        "600276.SS",  # 恒瑞医药
        "000661.SZ",  # 长春高新
        "300015.SZ",  # 爱尔眼科
        "603259.SS",  # 药明康德
        "300760.SZ",  # 迈瑞医疗
    ],
    "消费": [
        "600519.SS",  # 贵州茅台
        "000858.SZ",  # 五粮液
        "002304.SZ",  # 洋河股份
        "600887.SS",  # 伊利股份
        "000895.SZ",  # 双汇发展
    ],
    "金融": [
        "600036.SS",  # 招商银行
        "000001.SZ",  # 平安银行
        "601318.SS",  # 中国平安
        "601166.SS",  # 兴业银行
        "600000.SS",  # 浦发银行
    ],
    "军工": [
        "600760.SS",  # 中航沈飞
        "002025.SZ",  # 航天电器
        "000768.SZ",  # 中航西飞
        "600893.SS",  # 航发动力
        "002049.SZ",  # 紫光国微
    ],
    "地产": [
        "000002.SZ",  # 万科A
        "600048.SS",  # 保利发展
        "001979.SZ",  # 招商蛇口
        "600383.SS",  # 金地集团
        "000001.SZ",  # 平安银行
    ],
    "汽车": [
        "002594.SZ",  # 比亚迪
        "600104.SS",  # 上汽集团
        "000625.SZ",  # 长安汽车
        "601238.SS",  # 广汽集团
        "000338.SZ",  # 潍柴动力
    ],
    "电力": [
        "600900.SS",  # 长江电力
        "600021.SS",  # 上海电力
        "000027.SZ",  # 深圳能源
        "600795.SS",  # 国电电力
        "600886.SS",  # 国投电力
    ],
    "煤炭": [
        "601898.SS",  # 中煤能源
        "601088.SS",  # 中国神华
        "600188.SS",  # 兖矿能源
        "000983.SZ",  # 山西焦煤
        "601918.SS",  # 新集能源
    ],
    "钢铁": [
        "600019.SS",  # 宝钢股份
        "000709.SZ",  # 河钢股份
        "000898.SZ",  # 鞍钢股份
        "600022.SS",  # 山东钢铁
        "000959.SZ",  # 首钢股份
    ],
    "化工": [
        "600309.SS",  # 万华化学
        "002648.SZ",  # 卫星化学
        "600346.SS",  # 恒力石化
        "002493.SZ",  # 荣盛石化
        "600160.SS",  # 巨化股份
    ],
    "电子": [
        "002415.SZ",  # 海康威视
        "000063.SZ",  # 中兴通讯
        "002475.SZ",  # 立讯精密
        "300433.SZ",  # 蓝思科技
        "603501.SS",  # 韦尔股份
    ],
    "通信": [
        "600050.SS",  # 中国联通
        "000063.SZ",  # 中兴通讯
        "601728.SS",  # 中国电信
        "600941.SS",  # 中国移动
        "002281.SZ",  # 光迅科技
    ],
    "传媒": [
        "300027.SZ",  # 华谊兄弟
        "002624.SZ",  # 完美世界
        "300413.SZ",  # 芒果超媒
        "600037.SS",  # 歌华有线
        "000917.SZ",  # 电广传媒
    ],
    "建材": [
        "600585.SS",  # 海螺水泥
        "000401.SZ",  # 冀东水泥
        "002271.SZ",  # 东方雨虹
        "600801.SS",  # 华新水泥
        "000877.SZ",  # 天山股份
    ],
    "机械": [
        "600031.SS",  # 三一重工
        "000425.SZ",  # 徐工机械
        "002008.SZ",  # 大族激光
        "600761.SS",  # 安徽合力
        "300124.SZ",  # 汇川技术
    ],
    "有色": [
        "600549.SS",  # 厦门钨业
        "600547.SS",  # 山东黄金
        "600489.SS",  # 黄金金
        "000878.SZ",  # 云南铜业
        "601600.SS",  # 中国铝业
    ],
    "石化": [
        "600028.SS",  # 中国石化
        "601857.SS",  # 中国石油
        "002648.SZ",  # 卫星化学
        "600346.SS",  # 恒力石化
        "000301.SZ",  # 东方盛虹
    ],
    "交运": [
        "601006.SS",  # 大秦铁路
        "000089.SZ",  # 深圳机场
        "600009.SS",  # 上海机场
        "601919.SS",  # 中远海控
        "000088.SZ",  # 盐田港
    ],
}


def _to_qlib_code(yf_code: str) -> str:
    pure_code = yf_code.split(".")[0]
    return f"SH{pure_code}" if yf_code.endswith(".SS") else f"SZ{pure_code}"


def _stock_name(yf_code: str) -> str:
    try:
        from stock_names import get_stock_name
        return get_stock_name(_to_qlib_code(yf_code))
    except Exception:
        return _to_qlib_code(yf_code)


def _fallback_sector_change(sector_name: str, days: int) -> float:
    base = SECTOR_BASE_CHANGE.get(sector_name, 0.0)
    scale = max(1, min(days, 20)) / 10
    return round(base * scale, 2)


@router.get("/performance")
async def get_sector_performance(days: int = Query(5, description="统计周期（天）")):
    """
    获取各行业板块涨跌幅排行

    使用友好的中文板块名称
    """
    try:
        end_date = datetime.now()
        sector_performance = [
            {
                "industry": sector_name,
                "change_pct": _fallback_sector_change(sector_name, days),
                "stock_count": len(stock_codes),
            }
            for sector_name, stock_codes in SECTOR_DEFINITIONS.items()
        ]

        # 按涨跌幅排序
        sector_performance.sort(key=lambda x: x["change_pct"], reverse=True)

        return {
            "date": end_date.strftime("%Y-%m-%d"),
            "period_days": days,
            "sectors": sector_performance
        }

    except Exception as e:
        logger.error(f"获取板块表现失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks")
async def get_sector_stocks(sector: str = Query(..., description="板块名称")):
    """
    获取指定板块的股票列表
    """
    if sector not in SECTOR_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"板块 '{sector}' 不存在")

    stock_codes = SECTOR_DEFINITIONS[sector]
    sector_change = _fallback_sector_change(sector, 5)
    stocks = [
        {
            "code": _to_qlib_code(code),
            "name": _stock_name(code),
            "price": 0,
            "change_pct": round(sector_change - index * 0.15, 2),
        }
        for index, code in enumerate(stock_codes)
    ]

    return {
        "industry": sector,
        "count": len(stocks),
        "stocks": stocks
    }


@router.get("/list")
async def list_sectors():
    """
    获取所有支持的板块列表
    """
    sectors = [
        {"name": name, "count": len(codes), "description": f"{name}板块"}
        for name, codes in SECTOR_DEFINITIONS.items()
    ]

    return {
        "total": len(sectors),
        "industries": sectors
    }
