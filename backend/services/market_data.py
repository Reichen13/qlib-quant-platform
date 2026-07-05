"""市场数据服务 — 概念板块、资金流向、龙虎榜。纯 urllib 实现，源自 a-stock-data Skill。"""

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def _em_fetch(url, params=None, timeout=15):
    """东财 HTTP GET（绕过代理）"""
    if params:
        import urllib.parse
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://quote.eastmoney.com/")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ── 1. 概念板块归属（东财 slist, spt=3）──
def fetch_concept_boards(code: str) -> dict:
    """个股所属板块/概念归属（行业+概念+地域混合，含BK码+涨跌幅+龙头股）"""
    market_code = 1 if code.startswith("6") else 0
    secid = f"{market_code}.{code}"
    params = {"fltt": "2", "invt": "2", "secid": secid,
              "spt": "3", "pi": "0", "pz": "200", "po": "1",
              "fields": "f12,f14,f3,f128"}
    try:
        r = _em_fetch("https://push2.eastmoney.com/api/qt/slist/get", params=params)
        d = r.get("data", {}) or {}
        diff = d.get("diff") or {}
        items = diff.values() if isinstance(diff, dict) else diff
        boards = []
        for it in items:
            boards.append({
                "name": it.get("f14", ""),
                "code": it.get("f12", ""),
                "change_pct": it.get("f3", ""),
                "lead_stock": it.get("f128", ""),
            })
        return {"total": len(boards), "boards": boards,
                "concept_tags": [b["name"] for b in boards]}
    except Exception as e:
        logger.warning(f"概念板块请求失败 {code}: {e}")
        return {"total": 0, "boards": [], "concept_tags": []}

# ── 2. 个股资金流向（东财 push2 分钟级）──
def fetch_stock_fund_flow(code: str, days: int = 5) -> dict:
    """个股资金流向（日级：主力/超大单/大单/中单/小单净流入）"""
    market_code = 1 if code.startswith("6") else 0
    secid = f"{market_code}.{code}"
    params = {"lmt": str(days), "klt": "101", "secid": secid,
              "fields1": "f1,f2,f3,f7",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"}
    try:
        r = _em_fetch("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", params=params)
        d = r.get("data", {}) or {}
        klines = d.get("klines", [])
        if not klines:
            return {"code": code, "records": [], "summary": {"主力净流入": 0}}
        records = []
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 7:
                try:
                    records.append({
                        "date": parts[0],
                        "主力净流入": round(float(parts[1]) / 1e4, 1) if parts[1] != "-" else 0,
                        "超大单净流入": round(float(parts[5]) / 1e4, 1) if parts[5] != "-" else 0,
                        "大单净流入": round(float(parts[6]) / 1e4, 1) if parts[6] != "-" else 0,
                    })
                except (ValueError, IndexError):
                    pass
        total_main = sum(r["主力净流入"] for r in records)
        return {"code": code, "records": records,
                "summary": {"主力净流入": round(total_main, 1), "记录天数": len(records)}}
    except Exception as e:
        logger.warning(f"资金流向请求失败 {code}: {e}")
        return {"code": code, "records": [], "summary": {"主力净流入": 0}}

# ── 3. 龙虎榜（东财 datacenter RPT_DAILYBILLBOARD_DETAILSNEW）──
def fetch_dragon_tiger(code: str = "", page_size: int = 20) -> dict:
    """
    龙虎榜数据。
    若指定 code 则查该股历史记录；否则查全市场最近上榜。
    push2/push2ex 在本机不可用（代理阻断），改用东财 datacenter。
    """
    filter_str = ""
    if code:
        filter_str = f"(SECURITY_CODE=\"{code}\")"
    params = {"sortColumns": "TRADE_DATE", "sortTypes": "-1",
              "pageSize": str(page_size), "pageNumber": "1",
              "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
              "columns": "TRADE_DATE,SECURITY_CODE,SECURITY_NAME_ABBR,CLOSE_PRICE,CHANGE_RATE,BILLBOARD_NET_AMT,EXPLANATION,ACCUM_AMOUNT",
              "source": "WEB", "client": "WEB"}
    if filter_str:
        params["filter"] = filter_str
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    try:
        r = _em_fetch(url, params=params, timeout=15)
        data = r.get("result", {}) or {}
        rows = data.get("data", [])
        records = []
        for row in rows:
            records.append({
                "date": str(row.get("TRADE_DATE", ""))[:10],
                "code": row.get("SECURITY_CODE", ""),
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "price": row.get("CLOSE_PRICE", ""),
                "change_pct": row.get("CHANGE_RATE", ""),
                "net_buy_amt": round((row.get("BILLBOARD_NET_AMT") or 0) / 1e4, 1),
                "reason": row.get("EXPLANATION", ""),
                "amount": round((row.get("ACCUM_AMOUNT") or 0) / 1e4, 1),
            })
        return {"code": code or "全市场", "count": len(records), "records": records}
    except Exception as e:
        logger.warning(f"龙虎榜请求失败: {e}")
        return {"code": code or "全市场", "count": 0, "records": []}
