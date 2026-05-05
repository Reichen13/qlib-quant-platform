"""
统一的板块/行业定义 — 单一数据源

所有模块引用此文件中的 SECTOR_DEFINITIONS，
避免 hot.py / sectors.py / dashboard.py 各自维护不同的板块列表。
"""

from typing import Dict, List

# 板块定义（yfinance 格式，作为权威数据源）
# 每板块 5 只代表性成分股
SECTOR_DEFINITIONS: Dict[str, List[str]] = {
    "半导体": ["600584.SS", "002371.SZ", "300782.SZ", "688981.SS", "002049.SZ"],
    "新能源": ["300750.SZ", "002594.SZ", "601012.SS", "688590.SS", "300274.SZ"],
    "医药": ["600276.SS", "000661.SZ", "300015.SZ", "603259.SS", "300760.SZ"],
    "消费": ["600519.SS", "000858.SZ", "002304.SZ", "600887.SS", "000895.SZ"],
    "金融": ["600036.SS", "000001.SZ", "601318.SS", "601166.SS", "600000.SS"],
    "军工": ["600760.SS", "002025.SZ", "000768.SZ", "600893.SS", "002049.SZ"],
    "地产": ["000002.SZ", "600048.SS", "001979.SZ", "600383.SS", "000001.SZ"],
    "汽车": ["002594.SZ", "600104.SS", "000625.SZ", "601238.SS", "000338.SZ"],
    "电力": ["600900.SS", "600021.SS", "000027.SZ", "600795.SS", "600886.SS"],
    "煤炭": ["601898.SS", "601088.SS", "600188.SS", "000983.SZ", "601918.SS"],
    "钢铁": ["600019.SS", "000709.SZ", "000898.SZ", "600022.SS", "000959.SS"],
    "化工": ["600309.SS", "002648.SZ", "600346.SS", "002493.SZ", "600160.SS"],
    "电子": ["002415.SZ", "000063.SZ", "002475.SZ", "300433.SZ", "603501.SS"],
    "通信": ["600050.SS", "000063.SZ", "601728.SS", "600941.SS", "002281.SZ"],
    "传媒": ["300027.SZ", "002624.SZ", "300413.SZ", "600037.SS", "000917.SZ"],
    "建材": ["600585.SS", "000401.SZ", "002271.SZ", "600801.SS", "000877.SZ"],
    "机械": ["600031.SS", "000425.SZ", "002008.SZ", "600761.SS", "300124.SZ"],
    "有色": ["600549.SS", "600547.SS", "600489.SS", "000878.SZ", "601600.SS"],
    "石化": ["600028.SS", "601857.SS", "002648.SZ", "600346.SS", "000301.SZ"],
    "交运": ["601006.SS", "000089.SZ", "600009.SS", "601919.SS", "000088.SZ"],
}


def yf_to_qlib(yf_code: str) -> str:
    """yfinance 格式 → Qlib 格式：600519.SS → SH600519"""
    parts = yf_code.split(".")
    prefix = "SH" if parts[1] == "SS" else "SZ"
    return f"{prefix}{parts[0]}"


def qlib_to_yf(qlib_code: str) -> str:
    """Qlib 格式 → yfinance 格式：SH600519 → 600519.SS"""
    if qlib_code.startswith("SH"):
        return f"{qlib_code[2:]}.SS"
    elif qlib_code.startswith("SZ"):
        return f"{qlib_code[2:]}.SZ"
    return qlib_code


def get_sectors_qlib() -> Dict[str, List[str]]:
    """返回 Qlib 格式 (SH/SZ) 的板块定义"""
    return {
        name: [yf_to_qlib(c) for c in codes]
        for name, codes in SECTOR_DEFINITIONS.items()
    }
