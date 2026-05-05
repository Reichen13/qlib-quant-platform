"""
新闻分析 API

- GET  /api/news/sentiment/{code}    单股新闻情感
- GET  /api/news/daily-brief         每日市场简报
- GET  /api/news/events/{code}       结构化事件
- GET  /api/news/market-sentiment    全市场情感概览
"""

from datetime import datetime
from fastapi import APIRouter, Query, HTTPException
from loguru import logger

from core.news_sentiment import (
    get_news_fetcher,
    get_event_extractor,
    analyze_sentiment,
)

router = APIRouter()


@router.get("/sentiment/{code}")
async def get_stock_news_sentiment(
    code: str,
    days: int = Query(default=7, ge=1, le=30, description="回溯天数"),
):
    """获取单只股票近期新闻 + 情感分析

    Args:
        code: yfinance 格式代码，如 "600519.SS"
        days: 回溯天数
    """
    fetcher = get_news_fetcher()
    news = fetcher.fetch_for_stock(code, days=days)

    # 计算汇总情感
    if news:
        scores = [n.get("sentiment", {}).get("score", 0) for n in news]
        avg_score = sum(scores) / len(scores)
        pos_count = sum(1 for n in news if n.get("sentiment", {}).get("label") == "positive")
        neg_count = sum(1 for n in news if n.get("sentiment", {}).get("label") == "negative")
    else:
        avg_score = 0.0
        pos_count = neg_count = 0

    logger.info(f"新闻情感: {code}, {len(news)} 条, 均分={avg_score:.2f}")

    return {
        "code": code,
        "total": len(news),
        "avg_sentiment_score": round(avg_score, 3),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "neutral_count": len(news) - pos_count - neg_count,
        "news": news,
    }


@router.get("/daily-brief")
async def get_daily_brief():
    """每日市场简报 — 聚合当日重要新闻

    优先使用 LLM 生成摘要（如果已配置），否则返回规则化聚合结果。
    """
    fetcher = get_news_fetcher()
    market_news = fetcher.fetch_market_news(days=1)

    if not market_news:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": "今日暂无重要新闻",
            "sentiment": {"score": 0.0, "label": "neutral"},
            "top_news": [],
            "source": "none",
        }

    # 情感汇总
    scores = [n.get("sentiment", {}).get("score", 0) for n in market_news]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    if avg_score > 0.15:
        market_sentiment = "positive"
    elif avg_score < -0.15:
        market_sentiment = "negative"
    else:
        market_sentiment = "neutral"

    # 尝试 LLM 生成摘要
    summary = _rule_based_summary(market_news, avg_score)
    try:
        from core.llm_client import get_llm_config
        if get_llm_config().is_configured:
            summary = _llm_summary(market_news)
    except Exception:
        pass

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary,
        "sentiment": {
            "score": round(avg_score, 3),
            "label": market_sentiment,
        },
        "top_news": market_news[:10],
        "total": len(market_news),
        "source": "akshare",
    }


def _rule_based_summary(news: list[dict], avg_score: float) -> str:
    """规则化市场摘要"""
    pos = [n for n in news if n.get("sentiment", {}).get("label") == "positive"]
    neg = [n for n in news if n.get("sentiment", {}).get("label") == "negative"]

    parts = [f"今日共获取 {len(news)} 条市场资讯。"]

    if avg_score > 0.3:
        parts.append("市场情绪偏正面，利好消息较多。")
    elif avg_score < -0.3:
        parts.append("市场情绪偏负面，需关注风险。")
    else:
        parts.append("市场情绪中性，多空消息交织。")

    if pos:
        parts.append(f"正面消息主要集中在: {pos[0].get('title', '')[:60]}...")
    if neg:
        parts.append(f"需关注: {neg[0].get('title', '')[:60]}...")

    return "".join(parts)


def _llm_summary(news: list[dict]) -> str:
    """LLM 生成的市场摘要"""
    from core.llm_client import get_llm_client

    client = get_llm_client()
    titles = "\n".join(
        f"- [{n.get('sentiment', {}).get('label', '?')}] {n.get('title', '')}"
        for n in news[:20]
    )

    prompt = (
        f"以下是今日A股市场的重要新闻（已标注情感方向）：\n\n{titles}\n\n"
        f"请用2-3句话总结今日市场的主要驱动因素和情绪方向。"
        f"用中文回答，简洁专业。"
    )

    llm = client.get_quick_llm()
    response = llm.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)


@router.get("/events/{code}")
async def get_stock_events(
    code: str,
    days: int = Query(default=30, ge=1, le=90, description="回溯天数"),
):
    """获取单只股票的结构化事件

    Args:
        code: yfinance 格式代码
        days: 回溯天数
    """
    fetcher = get_news_fetcher()
    news = fetcher.fetch_for_stock(code, days=days)

    extractor = get_event_extractor()
    events = extractor.extract_events(code, news)

    return {
        "code": code,
        "total_news": len(news),
        "events": events,
        "has_llm": extractor.is_available,
    }


@router.get("/market-sentiment")
async def get_market_sentiment():
    """全市场情感概览 — 从近期市场新闻中汇总情感热力数据"""
    fetcher = get_news_fetcher()
    market_news = fetcher.fetch_market_news(days=1)

    if not market_news:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "overall_score": 0.0,
            "overall_label": "neutral",
            "sectors": [],
            "total_news": 0,
        }

    scores = [n.get("sentiment", {}).get("score", 0) for n in market_news]
    avg_score = sum(scores) / len(scores)

    # 按提及行业分类（简单关键词匹配）
    sector_keywords = {
        "半导体": ["半导体", "芯片", "集成电路", "光刻"],
        "新能源": ["新能源", "光伏", "风电", "储能", "锂电"],
        "消费": ["消费", "白酒", "食品", "家电", "零售"],
        "医药": ["医药", "医疗", "创新药", "疫苗", "生物"],
        "金融": ["银行", "券商", "保险", "金融"],
        "地产": ["地产", "房地产", "基建", "建材"],
        "汽车": ["汽车", "新能源车", "整车", "零部件"],
        "互联网": ["互联网", "游戏", "传媒", "软件", "AI"],
    }

    sector_scores = {}
    for sector, keywords in sector_keywords.items():
        sector_news = [
            n for n in market_news
            if any(kw in n.get("title", "") for kw in keywords)
        ]
        if sector_news:
            s_scores = [n.get("sentiment", {}).get("score", 0) for n in sector_news]
            sector_scores[sector] = {
                "score": round(sum(s_scores) / len(s_scores), 3),
                "count": len(sector_news),
            }

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "overall_score": round(avg_score, 3),
        "overall_label": "positive" if avg_score > 0.15 else "negative" if avg_score < -0.15 else "neutral",
        "sectors": [
            {"name": k, **v}
            for k, v in sorted(sector_scores.items(), key=lambda x: -x[1]["count"])
        ],
        "total_news": len(market_news),
    }
