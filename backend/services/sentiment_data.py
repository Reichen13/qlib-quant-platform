# 市场情绪数据服务 — 整合现有稳定端点 + 腾讯行情兜底
import json, logging, urllib.request

logger = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _em_fetch(url: str, timeout: int = 12) -> dict:
    """东财 HTTP GET"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://data.eastmoney.com/")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _qt_fetch(codes: list[str]) -> dict:
    """腾讯财经行情 (不封IP)"""
    # 指数代码需要正确的前缀映射 (0 开头的可能是深市也可能是沪市指数)
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
        elif c.startswith(("0", "3")): prefixed.append(f"sz{c}")
        elif c.startswith("8"): prefixed.append(f"bj{c}")
        else: prefixed.append(c)
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=8)
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


def fetch_market_sentiment() -> dict:
    """获取市场情绪多维数据 (整合5个稳定端点)"""
    result = {
        "updated": "",
        "dimensions": {},
        "warnings": [],
    }

    # 1. 龙虎榜活动度 (今日上榜数及净买入排名)
    try:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               "?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=15&pageNumber=1"
               "&reportName=RPT_DAILYBILLBOARD_DETAILSNEW"
               "&columns=TRADE_DATE,SECURITY_CODE,SECURITY_NAME_ABBR,CHANGE_RATE,BILLBOARD_NET_AMT,EXPLANATION"
               "&source=WEB&client=WEB")
        data = _em_fetch(url, timeout=12)
        rows = data.get("result", {}).get("data", [])
        net_buys = [(r.get("SECURITY_NAME_ABBR",""), round((r.get("BILLBOARD_NET_AMT") or 0) / 1e4, 1))
                    for r in rows[:10]]
        result["dimensions"]["dragon_tiger"] = {
            "label": "龙虎榜活动度",
            "count": len(rows) if rows else 0,
            "top_net_buy": net_buys,
            "status": "active" if len(rows) > 5 else "low",
        }
    except Exception as e:
        logger.warning(f"龙虎榜数据获取失败: {e}")
        result["dimensions"]["dragon_tiger"] = {"label": "龙虎榜", "count": 0, "status": "unavailable"}
        result["warnings"].append("龙虎榜数据暂不可用")

    # 2. 北向资金 (20日净流向)
    try:
        from backend.services.external_data import fetch_northbound_flow
        north = fetch_northbound_flow(days=20)
        net_20d = sum(r["net_flow"] for r in north)
        net_5d = sum(r["net_flow"] for r in north[-5:])
        result["dimensions"]["northbound"] = {
            "label": "北向资金",
            "net_flow_5d": round(net_5d, 2),
            "net_flow_20d": round(net_20d, 2),
            "status": "inflow" if net_20d > 50 else ("outflow" if net_20d < -50 else "neutral"),
            "daily": north[-5:] if len(north) >= 5 else north,
        }
    except Exception as e:
        logger.warning(f"北向资金获取失败: {e}")
        result["dimensions"]["northbound"] = {"label": "北向资金", "status": "unavailable"}
        result["warnings"].append("北向资金数据暂不可用")

    # 3. 指数行情 (上证/深证/创业板/科创/沪深300 实时涨跌)
    try:
        indices = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
                   "000688": "科创50", "000300": "沪深300"}
        quotes = _qt_fetch(list(indices.keys()))
        index_data = []
        up_count = 0
        for code, name in indices.items():
            if code in quotes:
                q = quotes[code]
                if q["change_pct"] > 0: up_count += 1
                index_data.append({
                    "code": code, "name": name,
                    "price": q["price"], "change_pct": q["change_pct"],
                })
        result["dimensions"]["indices"] = {
            "label": "核心指数",
            "data": index_data,
            "up_ratio": round(up_count / max(len(index_data), 1), 2),
        }
    except Exception as e:
        logger.warning(f"指数行情获取失败: {e}")
        result["dimensions"]["indices"] = {"label": "核心指数", "data": [], "status": "unavailable"}

    # 4. 行业排名 (取前10和后5)
    try:
        from backend.services.external_data import fetch_industry_ranking
        sectors = fetch_industry_ranking()
        top5 = [s for s in sectors[:5] if s.get("change_pct", 0) != 0]
        bottom5 = [s for s in sectors[-5:] if s.get("change_pct", 0) != 0]
        result["dimensions"]["sectors"] = {
            "label": "行业板块",
            "top": top5,
            "bottom": bottom5,
        }
    except Exception as e:
        logger.warning(f"行业排名获取失败: {e}")
        result["dimensions"]["sectors"] = {"label": "行业板块", "top": [], "bottom": [], "status": "unavailable"}

    # 5. 解禁预警 (未来7天)
    try:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               "?sortColumns=LIFT_DATE&sortTypes=1&pageSize=10&pageNumber=1"
               "&reportName=RPT_LIFT_STAGE"
               "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,LIFT_DATE,LIFT_SHARES,LIFT_MARKET_CAP"
               "&source=WEB&client=WEB")
        data = _em_fetch(url, timeout=10)
        rows = data.get("result", {}).get("data", []) or []
        unlocks = []
        for r in rows[:10]:
            unlocks.append({
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "date": str(r.get("LIFT_DATE", ""))[:10],
                "shares": f"{round((r.get('LIFT_SHARES') or 0) / 1e4, 1)}万股",
                "market_cap": f"{round((r.get('LIFT_MARKET_CAP') or 0) / 1e8, 1)}亿",
            })
        result["dimensions"]["unlock"] = {
            "label": "解禁预警",
            "count": len(unlocks),
            "items": unlocks,
            "status": "high" if len(unlocks) > 5 else "normal",
        }
    except Exception as e:
        logger.warning(f"解禁数据获取失败: {e}")
        result["dimensions"]["unlock"] = {"label": "解禁预警", "count": 0, "items": [], "status": "unavailable"}

    # 6. 概念板块热度 TOP10
    try:
        # push2.eastmoney.com 被 Clash TUN 拦截，用 push2his 替代
        url = ("https://push2his.eastmoney.com/api/qt/clist/get"
               "?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:3"
               "&fields=f2,f3,f12,f14,f104,f105")
        data = _em_fetch(url, timeout=15)
        diff = data.get("data", {}).get("diff", []) or []
        hot_boards = []
        for d in diff[:10]:
            hot_boards.append({
                "code": d.get("f12", ""),
                "name": d.get("f14", ""),
                "change_pct": d.get("f3", 0),
                "up_count": d.get("f104", 0),
                "down_count": d.get("f105", 0),
            })
        result["dimensions"]["hot_boards"] = {
            "label": "概念板块",
            "count": len(hot_boards),
            "boards": hot_boards,
        }
    except Exception as e:
        logger.warning(f"概念板块获取失败: {e}")
        result["dimensions"]["hot_boards"] = {
            "label": "概念板块",
            "count": 0,
            "boards": [],
            "status": "unavailable",
            "message": "概念板块数据需 push2.eastmoney.com，当前网络环境下不可用。如需恢复，可将 push2.eastmoney.com 加入 Clash 代理绕过列表。",
        }

    # 综合情绪评分 (粗略)
    score = 50
    try:
        nb = result["dimensions"].get("northbound", {})
        if nb.get("status") == "inflow": score += 15
        elif nb.get("status") == "outflow": score -= 15

        idx = result["dimensions"].get("indices", {})
        if idx.get("up_ratio", 0) > 0.7: score += 10
        elif idx.get("up_ratio", 0) < 0.3: score -= 10

        dt = result["dimensions"].get("dragon_tiger", {})
        if dt.get("status") == "active": score += 10

        sec = result["dimensions"].get("sectors", {})
        if len(sec.get("top", [])) > 0:
            top_avg = sum(s.get("change_pct", 0) for s in sec["top"]) / max(len(sec["top"]), 1)
            if top_avg > 2: score += 10
    except Exception:
        pass

    result["score"] = min(max(score, 0), 100)
    result["sentiment"] = "偏多" if result["score"] > 65 else ("偏空" if result["score"] < 35 else "中性")

    from datetime import datetime
    result["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    return result
