"""外部数据源服务 — 纯 urllib 实现，不依赖 akshare/pandas/mootdx。"""

import json
import logging
import time
import urllib.request

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
    prefixed = []
    for c in codes:
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
    indices = {"000001": "上证指数","399006":"创业板指","399001":"深证成指","000688":"科创50"}
    quotes = _qt_fetch(list(indices.keys()), timeout=5)
    rows = []
    for code, name in indices.items():
        if code in quotes:
            rows.append({"industry": name, "change_pct": round(quotes[code].get("change_pct", 0), 2), "stock_count": 0})
    if rows:
        rows.sort(key=lambda x: x["change_pct"], reverse=True)
        return rows
    return [{"industry": "数据源暂不可用", "change_pct": 0, "stock_count": 0}]


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
