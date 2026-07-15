"""外部数据源服务 — 纯 urllib 实现，不依赖 akshare/pandas/mootdx。"""

import json
import logging
import time
import urllib.request
import struct
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _em_fetch(url: str, timeout: int = 10) -> dict:
    """东财 HTTP GET（urllib 实现，绕过系统代理）"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Referer", "https://data.eastmoney.com/")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _qt_fetch(codes: list, timeout: int = 10) -> dict:
    """腾讯财经行情（不封 IP）"""
    # 指数代码需要正确的前缀映射
    INDEX_PREFIX = {
        "000001": "sh",  # 上证指数
        "000016": "sh",  # 上证50
        "000300": "sh",  # 沪深300
        "000688": "sh",  # 科创50
        "000905": "sh",  # 中证500
        "399001": "sz",  # 深证成指
        "399005": "sz",  # 中小100
        "399006": "sz",  # 创业板指
        "399330": "sz",  # 深证100
    }
    prefixed = []
    for c in codes:
        if c in INDEX_PREFIX:
            prefixed.append(f"{INDEX_PREFIX[c]}{c}")
            continue
        if c.startswith("6"): prefixed.append(f"sh{c}")
        elif c.startswith(("0","3")): prefixed.append(f"sz{c}")
        elif c.startswith("8"): prefixed.append(f"bj{c}")
        else: prefixed.append(c)
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if "=" not in line or chr(34) not in line: continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split(chr(34))[1].split("~")
        if len(vals) < 53: continue
        code = key[2:]
        result[code] = {
            "name": vals[1], "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "volume": float(vals[6]) if vals[6] else 0,
            "amount": float(vals[37]) if vals[37] else 0,
        }
    return result


def fetch_china_pmi() -> dict:
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           "?sortColumns=REPORT_DATE&sortTypes=-1&pageSize=3&pageNumber=1"
           "&reportName=RPT_ECONOMY_PMI"
           "&columns=REPORT_DATE,MAKE_INDEX,NMAKE_INDEX"
           "&source=WEB&client=WEB")
    data = _em_fetch(url, timeout=10)
    rows = data.get("result", {}).get("data", [])
    if rows:
        r = rows[0]
        return {"date": str(r.get("REPORT_DATE",""))[:10],
                "manufacturing_pmi": float(r.get("MAKE_INDEX",0)),
                "non_manufacturing_pmi": float(r.get("NMAKE_INDEX",0))}
    return {}


def fetch_china_m2() -> dict:
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           "?sortColumns=REPORT_DATE&sortTypes=-1&pageSize=24&pageNumber=1"
           "&reportName=RPT_ECONOMY_MONEY_SUPPLY"
           "&columns=REPORT_DATE,M2,M2_YOY"
           "&source=WEB&client=WEB")
    try:
        data = _em_fetch(url, timeout=10)
        rows = (data.get("result") or {}).get("data") or []
        if rows:
            r = rows[0]
            m2_yoy = float(r.get("M2_YOY", 0))
            values = [float(row.get("M2_YOY", 0)) for row in rows if row.get("M2_YOY")]
            trend = "up" if len(values) >= 2 and values[0] > values[1] else "down"
            z = (values[0] - sum(values) / len(values)) / ((sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)) ** 0.5 or 1)
            return {"date": str(r.get("REPORT_DATE",""))[:10], "m2_yoy": m2_yoy,
                    "trend": trend, "z_score": round(z, 2)}
    except Exception:
        pass
    return {}


def fetch_china_shibor() -> dict:
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           "?sortColumns=REPORT_DATE&sortTypes=-1&pageSize=2&pageNumber=1"
           "&reportName=RPT_ECONOMY_CURRENCY_SHIBOR"
           "&columns=REPORT_DATE,ON_RATE,M1_RATE"
           "&source=WEB&client=WEB")
    try:
        data = _em_fetch(url, timeout=10)
        rows = (data.get("result") or {}).get("data") or []
        if rows:
            r = rows[0]
            return {"date": str(r.get("REPORT_DATE",""))[:10],
                    "overnight": float(r.get("ON_RATE",0)),
                    "1m": float(r.get("M1_RATE",0))}
    except Exception:
        pass
    return {}


def fetch_northbound_flow(days: int = 20) -> list:
    url = (f"https://push2his.eastmoney.com/api/qt/kamt.kline/get"
           f"?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54"
           f"&klt=101&lmt={days}&ut=b2884a393a59ad64002292a3e90d46a5")
    data = _em_fetch(url, timeout=10)
    d = data.get("data", {}) or {}
    daily = {}
    for key in ("hk2sh", "hk2sz"):
        for line in d.get(key, []):
            parts = line.split(",")
            if len(parts) >= 2:
                try: daily[parts[0]] = daily.get(parts[0], 0) + float(parts[1])
                except ValueError: pass
    rows = []
    for date_str in sorted(daily):
        rows.append({"date": date_str, "net_flow": round(daily[date_str] / 1e8, 2)})
    return rows


def fetch_industry_ranking() -> list:
    try:
        url = ("https://push2.eastmoney.com/api/qt/clist/get"
               "?pn=1&pz=20&po=1&np=1"
               "&fltt=2&invt=2&fid=f3&fs=m:90+t:2"
               "&fields=f2,f3,f14,f128")
        data = _em_fetch(url, timeout=5)
        rows = []
        for item in data.get("data", {}).get("diff", []):
            rows.append({"industry": item.get("f14",""),
                         "change_pct": round(float(item.get("f3",0)),2),
                         "stock_count": int(item.get("f128",0) or 0)})
        if rows:
            rows.sort(key=lambda x: x["change_pct"], reverse=True)
            return rows
    except Exception:
        pass
    # push2 不可用时，用本地 Qlib 数据计算行业涨跌
    try:
        return fetch_industry_ranking_from_qlib()
    except Exception as e:
        logger.warning(f"Qlib 行业排名也失败: {e}")
    return [{"industry": "行业数据不可用（可能周末或数据缺失）", "change_pct": 0, "stock_count": 0}]


def _load_industry_cache() -> dict:
    """加载或构建 股票代码 → 行业名称 的本地缓存"""
    cache_path = Path.home() / ".qlib" / "cache" / "industry_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # 从 baostock 拉取全量行业分类
    mapping = {}
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == "0":
            rs = bs.query_stock_industry()
            while (rs.error_code == "0") and rs.next():
                row = rs.get_row_data()
                code = row[1].replace(".", "")  # sh.600000 → sh600000
                industry = row[3] if row[3] else "未分类"
                mapping[code] = industry
            bs.logout()
    except Exception as e:
        logger.warning(f"baostock 行业分类拉取失败: {e}")
    if mapping:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False)
    return mapping


def _read_qlib_close_factor(stock_dir: Path) -> tuple | None:
    """读取 Qlib bin 文件的最新两个交易日的 close，返回 (prev_orig, latest_orig) 原始价"""
    try:
        close_bin = stock_dir / "close.day.bin"
        factor_bin = stock_dir / "factor.day.bin"
        if not close_bin.exists():
            return None
        close_data = close_bin.read_bytes()
        factor_data = factor_bin.read_bytes() if factor_bin.exists() else None
        elem_size = 4
        total_days = len(close_data) // elem_size
        if total_days < 2:
            return None
        offset = (total_days - 2) * elem_size
        prev_close = struct.unpack("f", close_data[offset:offset + 4])[0]
        latest_close = struct.unpack("f", close_data[offset + 4:offset + 8])[0]
        prev_factor = 1.0
        latest_factor = 1.0
        if factor_data and len(factor_data) >= total_days * elem_size:
            prev_factor = struct.unpack("f", factor_data[offset:offset + 4])[0]
            latest_factor = struct.unpack("f", factor_data[offset + 4:offset + 8])[0]
        prev_orig = prev_close / prev_factor if prev_factor and prev_factor != 0 else prev_close
        latest_orig = latest_close / latest_factor if latest_factor and latest_factor != 0 else latest_close
        return prev_orig, latest_orig
    except Exception:
        return None


def fetch_industry_ranking_from_qlib() -> list:
    """使用本地 Qlib 数据 + baostock 行业分类计算行业涨跌幅排名"""
    features_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features"
    if not features_dir.exists():
        return [{"industry": "Qlib数据目录不存在", "change_pct": 0, "stock_count": 0}]
    industry_map = _load_industry_cache()
    if not industry_map:
        return [{"industry": "行业缓存为空，需先拉取baostock分类", "change_pct": 0, "stock_count": 0}]
    # 聚合每只股票的最近日涨跌（基于原始价）
    industry_returns = {}  # industry → [returns]
    stock_dirs = [d for d in features_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    skipped = 0
    for d in stock_dirs:
        code = d.name
        industry = industry_map.get(code, "未分类")
        result = _read_qlib_close_factor(d)
        if result is None:
            skipped += 1
            continue
        prev_orig, latest_orig = result
        if prev_orig and prev_orig > 0 and latest_orig and latest_orig > 0:
            ret = (latest_orig - prev_orig) / prev_orig * 100
            if abs(ret) < 50:  # 过滤极端异常值
                if industry not in industry_returns:
                    industry_returns[industry] = []
                industry_returns[industry].append(ret)
    if skipped > 0:
        logger.warning(f"行业排名: {skipped} 只股票无 bin 数据")
    rows = []
    for ind, returns in industry_returns.items():
        if len(returns) < 2:
            continue
        avg_ret = sum(returns) / len(returns)
        rows.append({
            "industry": ind,
            "change_pct": round(avg_ret, 2),
            "stock_count": len(returns),
        })
    rows.sort(key=lambda x: x["change_pct"], reverse=True)
    if not rows:
        return [{"industry": "行业数据不可用（可能周末或数据缺失）", "change_pct": 0, "stock_count": 0}]
    return rows


# ── 手动宏观数据回退机制 ──
def fetch_manual_macro() -> dict:
    from pathlib import Path
    macro_file = Path.home() / ".qlib" / "macro_manual.json"
    if macro_file.exists():
        try:
            with open(macro_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return {}

def save_manual_macro(data: dict):
    from pathlib import Path
    macro_dir = Path.home() / ".qlib"
    macro_dir.mkdir(parents=True, exist_ok=True)
    macro_file = macro_dir / "macro_manual.json"
    with open(macro_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
