"""
新闻获取 + 情感分析 + 事件提取

- NewsFetcher: 多源新闻获取（akshare 主源），去重，15分钟缓存
- SentimentAnalyzer: 规则化中文金融情感词典（无 LLM 依赖）
- EventExtractor: LLM 结构化事件提取（需要 LLM 配置）
"""

import hashlib
import re
import time
from datetime import datetime, date, timedelta
from typing import Optional

from loguru import logger


# ── 中文金融情感词典 ──
_POSITIVE_WORDS = {
    "上涨", "增长", "利好", "突破", "盈利", "净利润", "扭亏", "大幅增长",
    "涨停", "分红", "回购", "中标", "合作", "签约", "订单", "扩产",
    "增持", "买入", "跑赢", "超预期", "创新高", "业绩预增", "扭亏为盈",
    "毛利率提升", "营收增长", "产能释放", "技术突破", "政策支持",
    "赛道景气", "需求旺盛", "供不应求", "量价齐升", "估值修复",
    "底部", "反弹", "反转", "放量", "资金流入", "北向资金",
}
_NEGATIVE_WORDS = {
    "下跌", "利空", "风险", "暴跌", "亏损", "减持", "跌停", "下滑",
    "大幅下降", "净亏损", "退市", "警示函", "问询", "监管函", "立案",
    "调查", "诉讼", "违约", "商誉", "减值", "债务", "逾期", "冻结",
    "质押", "爆仓", "停牌", "终止", "取消", "放弃", "解散", "破产",
    "卖出", "跑输", "低于预期", "业绩预警", "预亏", "毛利率下降",
    "营收下滑", "产能过剩", "需求疲软", "去库存", "杀估值", "泡沫",
    "破位", "资金流出", "主力出逃", "踩踏", "恐慌",
}

# 程度副词/否定词带来的极性翻转
_NEGATION_WORDS = {"不", "无", "未", "非", "否", "莫", "勿", "休", "别"}
_DOWNTONER_WORDS = {"略有", "小幅", "轻微", "微", "略", "稍"}


def _tokenize(text: str) -> list[str]:
    """简单中文分词：按标点和空格切分，提取 2-4 字词和短语"""
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 按标点切分
    segments = re.split(r"[，。！？、；：\s\n\r\"\'（）《》【】…—\-/\\,\.!\?;:()\[\]{}]+", text)
    tokens = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # 提取 2-4 字滑动窗口
        for win in [4, 3, 2]:
            for i in range(len(seg) - win + 1):
                tokens.append(seg[i:i + win])
        # 也保留单字（用于否定词检测）
        for ch in seg:
            tokens.append(ch)
    return tokens


def analyze_sentiment(text: str) -> dict:
    """基于规则词典的中文金融情感分析

    Args:
        text: 新闻标题或正文

    Returns:
        {"score": float (-1~1), "label": str, "confidence": float (0~1)}
    """
    tokens = _tokenize(text)
    pos_count = sum(1 for t in tokens if t in _POSITIVE_WORDS)
    neg_count = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
    negation_count = sum(1 for t in tokens if t in _NEGATION_WORDS)
    downtoner_count = sum(1 for t in tokens if t in _DOWNTONER_WORDS)

    total = pos_count + neg_count
    if total == 0:
        return {"score": 0.0, "label": "neutral", "confidence": 0.0}

    # 基础极性得分
    raw_score = (pos_count - neg_count) / max(total, 1)

    # 否定词翻转
    if negation_count > 0:
        raw_score *= -0.7

    # 程度副词弱化
    if downtoner_count > 0:
        raw_score *= 0.7

    score = max(-1.0, min(1.0, raw_score))
    confidence = min(1.0, total / 6)  # 6个以上情感词 = 满分

    if score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"

    return {"score": round(score, 3), "label": label, "confidence": round(confidence, 3)}


# ── 新闻获取 ──

class NewsFetcher:
    """多源新闻获取，按股票代码过滤，去重，15分钟 TTL 缓存"""

    def __init__(self):
        self._cache: dict = {}
        self._cache_ttl = 900  # 15 分钟

    def _cache_key(self, code: str, days: int) -> str:
        return f"{code}:{days}"

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return (time.time() - self._cache[key]["ts"]) < self._cache_ttl

    def _dedup(self, items: list[dict]) -> list[dict]:
        """按标题相似度去重（完全匹配或摘要哈希）"""
        seen = set()
        result = []
        for item in items:
            title_hash = hashlib.md5(
                item.get("title", "")[:80].encode()
            ).hexdigest()
            if title_hash not in seen:
                seen.add(title_hash)
                result.append(item)
        return result

    def fetch_for_stock(self, code: str, days: int = 7) -> list[dict]:
        """获取单只股票相关新闻

        Args:
            code: 股票代码（yfinance 格式，如 "600519.SS"）
            days: 回溯天数

        Returns:
            [{"title", "source", "time", "url", "sentiment"}]
        """
        cache_key = self._cache_key(code, days)
        if self._is_cache_valid(cache_key):
            logger.debug(f"[cache hit] news:{code}")
            return self._cache[cache_key]["data"]

        all_news = []

        # 尝试 akshare 东方财富新闻
        try:
            import akshare as ak
            # 提取纯数字代码
            code_num = code.replace(".SS", "").replace(".SZ", "")
            df = ak.stock_news_em(symbol=code_num)
            if df is not None and not df.empty:
                for _, row in df.head(30).iterrows():
                    all_news.append({
                        "title": str(row.get("标题", "")),
                        "source": "东方财富",
                        "time": str(row.get("发布时间", "")),
                        "url": str(row.get("新闻链接", "")),
                    })
        except Exception as e:
            logger.debug(f"akshare stock_news_em 失败 ({code}): {e}")

        # 备源：akshare 新浪财经（按关键词搜索）
        if not all_news:
            try:
                import akshare as ak
                code_num = code.replace(".SS", "").replace(".SZ", "")
                # 使用股票简称作为关键词
                keyword = code_num  # fallback to code
                df = ak.stock_info_a_code_name()
                if df is not None and not df.empty:
                    match = df[df["code"] == code_num]
                    if not match.empty:
                        keyword = str(match.iloc[0]["name"])
                df = ak.news_stock_notice(symbol=keyword)
                if df is not None and not df.empty:
                    for _, row in df.head(20).iterrows():
                        all_news.append({
                            "title": str(row.get("标题", row.get("title", ""))),
                            "source": "新浪财经",
                            "time": str(row.get("发布时间", row.get("time", ""))),
                            "url": str(row.get("链接", row.get("url", ""))),
                        })
            except Exception as e:
                logger.debug(f"备源新浪新闻失败 ({code}): {e}")

        # 对每条新闻做情感分析
        for item in all_news:
            item["sentiment"] = analyze_sentiment(item["title"])

        # 去重
        all_news = self._dedup(all_news)

        # 写入缓存
        self._cache[cache_key] = {"ts": time.time(), "data": all_news}

        return all_news

    def fetch_market_news(self, days: int = 1) -> list[dict]:
        """获取全市场新闻（用于每日简报）"""
        cache_key = f"market:{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]["data"]

        all_news = []

        # akshare 财联社电报
        try:
            import akshare as ak
            df = ak.stock_telegraph_cls()
            if df is not None and not df.empty:
                for _, row in df.head(50).iterrows():
                    all_news.append({
                        "title": str(row.get("标题", row.get("title", ""))),
                        "source": "财联社",
                        "time": str(row.get("时间", row.get("time", ""))),
                        "url": "",
                    })
        except Exception as e:
            logger.debug(f"财联社电报获取失败: {e}")

        # 备源：东方财富要闻
        if not all_news:
            try:
                import akshare as ak
                df = ak.stock_info_global_em()
                if df is not None and not df.empty:
                    for _, row in df.head(30).iterrows():
                        all_news.append({
                            "title": str(row.get("标题", row.get("title", ""))),
                            "source": "东方财富",
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "url": "",
                        })
            except Exception as e:
                logger.debug(f"东方财富要闻获取失败: {e}")

        for item in all_news:
            item["sentiment"] = analyze_sentiment(item.get("title", ""))

        all_news = self._dedup(all_news)
        self._cache[cache_key] = {"ts": time.time(), "data": all_news}

        return all_news


# 模块级单例
_fetcher: Optional[NewsFetcher] = None


def get_news_fetcher() -> NewsFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = NewsFetcher()
    return _fetcher


# ── LLM 事件提取（可选，需要 LLM 配置）──

class EventExtractor:
    """LLM 驱动的结构化事件提取"""

    EVENT_TYPES = [
        "业绩预告", "并购重组", "政策影响", "行业动态",
        "分红送转", "风险提示", "股东增减持", "重大合同",
    ]

    def __init__(self):
        self._client = None

    @property
    def is_available(self) -> bool:
        try:
            from core.llm_client import get_llm_config
            return get_llm_config().is_configured
        except Exception:
            return False

    def extract_events(self, code: str, news_items: list[dict]) -> list[dict]:
        """从新闻列表中提取结构化事件

        Args:
            code: 股票代码
            news_items: 新闻列表

        Returns:
            [{"type": str, "summary": str, "impact": str, "date": str}]
        """
        if not news_items:
            return []

        if not self.is_available:
            return self._rule_based_extract(news_items)

        try:
            from core.llm_client import get_llm_client
            client = get_llm_client()

            titles = "\n".join(
                f"- [{n.get('time', '?')}] {n.get('title', '')}"
                for n in news_items[:15]
            )

            prompt = (
                f"以下是股票 {code} 近期的新闻列表：\n\n{titles}\n\n"
                f"请从中提取重要的结构化事件。事件类型包括：{', '.join(self.EVENT_TYPES)}\n"
                f"对于每个事件，判断其影响方向（positive/negative/neutral）。\n"
                f"只关注有实质影响的事件，忽略日常行情评论。\n\n"
                f"返回 JSON 数组："
                f'[{{"type": "事件类型", "summary": "一句话摘要", '
                f'"impact": "positive/negative/neutral", "date": "日期"}}]'
            )

            # 自由文本调用（不强制 structured output）
            llm = client.get_quick_llm()
            response = llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)

            import json
            json_match = re.search(r"\[[\s\S]*\]", text)
            if json_match:
                events = json.loads(json_match.group(0))
                return events[:10]
        except Exception as e:
            logger.warning(f"LLM 事件提取失败，降级为规则提取: {e}")

        return self._rule_based_extract(news_items)

    def _rule_based_extract(self, news_items: list[dict]) -> list[dict]:
        """规则化事件提取（无 LLM 依赖的降级）"""
        patterns = {
            "业绩预告": ["业绩", "净利润", "营收", "预告", "快报", "年报", "季报", "中报"],
            "并购重组": ["并购", "重组", "收购", "注入", "整合", "合并"],
            "分红送转": ["分红", "送转", "派息", "高送转", "转增"],
            "股东增减持": ["增持", "减持", "举牌", "回购"],
            "重大合同": ["中标", "签约", "订单", "合同", "协议"],
            "风险提示": ["退市", "ST", "警示", "问询", "监管", "立案", "诉讼"],
        }

        events = []
        for item in news_items:
            title = item.get("title", "")
            for event_type, keywords in patterns.items():
                if any(kw in title for kw in keywords):
                    impact = item.get("sentiment", {}).get("label", "neutral")
                    events.append({
                        "type": event_type,
                        "summary": title[:100],
                        "impact": impact,
                        "date": item.get("time", "")[:10],
                    })
                    break

        return events[:10]


# 模块级单例
_extractor: Optional[EventExtractor] = None


def get_event_extractor() -> EventExtractor:
    global _extractor
    if _extractor is None:
        _extractor = EventExtractor()
    return _extractor
