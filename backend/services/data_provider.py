"""
统一数据提供者
整合 yfinance 和 Baostock 数据源
"""

from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
from loguru import logger


class DataProvider:
    """统一数据提供者 - 整合多个数据源"""

    def __init__(self):
        self._bs_client = None
        self._tdx_provider = None

    def _get_tdx_provider(self):
        if self._tdx_provider is None:
            try:
                from services.tdx_mcp_provider import TdxMcpProvider
                provider = TdxMcpProvider.from_env()
                self._tdx_provider = provider if provider.can_fetch_stock_list else False
            except Exception as e:
                logger.warning(f"TDX MCP 初始化失败: {e}")
                self._tdx_provider = False
        return self._tdx_provider or None

    def _get_bs_client(self):
        """获取 Baostock 客户端（懒加载）"""
        if self._bs_client is None:
            try:
                import baostock as bs
                lg = bs.login()
                if lg.error_code == '0':
                    self._bs_client = bs
                    logger.info("Baostock 连接成功")
                else:
                    logger.warning(f"Baostock 登录失败: {lg.error_msg}")
            except ImportError:
                logger.warning("baostock 未安装")
            except Exception as e:
                logger.warning(f"Baostock 初始化失败: {e}")
        return self._bs_client

    # ==================== 股票行情数据 ====================

    def get_stock_quote(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        获取股票行情数据
        优先使用 Baostock，失败时回退到 Qlib
        """
        # 转换代码格式：SH600000 -> sh.600000
        bs_code = self._to_baostock_code(code)

        try:
            bs = self._get_bs_client()
            if bs:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,code,open,high,low,close,volume,amount,pctChg,peTTM,pbMRQ",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="2"  # 前复权
                )

                if rs.error_code == '0':
                    data_list = []
                    while (rs.error_code == '0') & rs.next():
                        data_list.append(rs.get_row_data())

                    if data_list:
                        df = pd.DataFrame(data_list, columns=rs.fields)
                        # 转换数据类型
                        df['date'] = pd.to_datetime(df['date'])
                        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        for col in ['pctChg', 'peTTM', 'pbMRQ']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        return df

        except Exception as e:
            logger.warning(f"Baostock 获取行情失败 {code}: {e}")

        # 回退到 Qlib
        return self._get_qlib_quote(code, start_date, end_date)

    def _get_qlib_quote(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """从 Qlib 获取行情数据"""
        try:
            import qlib
            from qlib.data import D

            qlib_code = code.replace("SH", "").replace("SZ", "")
            df = D.features(
                [qlib_code],
                ["$open", "$high", "$low", "$close", "$volume", "$amount"],
                start_time=start_date,
                end_time=end_date
            )

            if not df.empty:
                df = df.reset_index()
                df.columns = ['date', 'field', 'value']
                df = df.pivot(index='date', columns='field', values='value')
                df = df.reset_index()
                df['code'] = code
                df['date'] = pd.to_datetime(df['date'])
                return df

        except Exception as e:
            logger.warning(f"Qlib 获取行情失败 {code}: {e}")

        return None

    # ==================== 财务数据 ====================

    def get_profit_data(self, code: str, year: int, quarter: int) -> Optional[Dict]:
        """
        获取盈利能力数据
        返回：ROE、销售净利率、销售毛利率、净利润、EPS等
        """
        bs = self._get_bs_client()
        if not bs:
            return None

        bs_code = self._to_baostock_code(code)

        try:
            rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
            if rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                return {
                    "code": row[0],
                    "pubDate": row[1],
                    "statDate": row[2],
                    "roeAvg": float(row[3]) if row[3] else None,
                    "npMargin": float(row[4]) if row[4] else None,
                    "gpMargin": float(row[5]) if row[5] else None,
                    "netProfit": float(row[6]) if row[6] else None,
                    "epsTTM": float(row[7]) if row[7] else None,
                    "MBRevenue": float(row[8]) if row[8] else None,
                }
        except Exception as e:
            logger.warning(f"获取盈利数据失败 {code}: {e}")

        return None

    def get_growth_data(self, code: str, year: int, quarter: int) -> Optional[Dict]:
        """获取成长能力数据"""
        bs = self._get_bs_client()
        if not bs:
            return None

        bs_code = self._to_baostock_code(code)

        try:
            rs = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
            if rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                return {
                    "code": row[0],
                    "YOYNI": float(row[3]) if row[3] else None,  # 净利润同比增长率
                    "YOYEPSBasic": float(row[4]) if row[4] else None,  # EPS同比增长率
                    "YOPYNI": float(row[5]) if row[5] else None,  # 归母净利润同比增长率
                }
        except Exception as e:
            logger.warning(f"获取成长数据失败 {code}: {e}")

        return None

    def get_operation_data(self, code: str, year: int, quarter: int) -> Optional[Dict]:
        """获取营运能力数据"""
        bs = self._get_bs_client()
        if not bs:
            return None

        bs_code = self._to_baostock_code(code)

        try:
            rs = bs.query_operation_data(code=bs_code, year=year, quarter=quarter)
            if rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                return {
                    "code": row[0],
                    "NRTurnRatio": float(row[3]) if row[3] else None,  # 应收账款周转率
                    "INVTurnRatio": float(row[5]) if row[5] else None,  # 存货周转率
                    "AssetTurnRatio": float(row[7]) if row[7] else None,  # 总资产周转率
                }
        except Exception as e:
            logger.warning(f"获取营运数据失败 {code}: {e}")

        return None

    def get_dupont_data(self, code: str, year: int, quarter: int) -> Optional[Dict]:
        """
        获取杜邦指数数据
        返回：ROE分解（杜邦三因子）
        """
        bs = self._get_bs_client()
        if not bs:
            return None

        bs_code = self._to_baostock_code(code)

        try:
            rs = bs.query_dupont_data(code=bs_code, year=year, quarter=quarter)
            if rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                return {
                    "code": row[0],
                    "dupontROE": float(row[3]) if row[3] else None,  # ROE
                    "dupontAssetStoEquity": float(row[4]) if row[4] else None,  # 权益乘数
                    "dupontAssetTurn": float(row[5]) if row[5] else None,  # 总资产周转率
                    "dupontPnitoni": float(row[6]) if row[6] else None,  # 归母净利润占比
                }
        except Exception as e:
            logger.warning(f"获取杜邦数据失败 {code}: {e}")

        return None

    def get_financial_summary(self, code: str) -> Optional[Dict]:
        """
        获取财务数据汇总
        整合盈利能力、成长能力、营运能力、杜邦指数
        """
        # 获取最近季度数据
        today = datetime.now()
        year = today.year
        quarter = (today.month - 1) // 3 + 1
        if quarter > 4:
            quarter = 4
        elif quarter == 0:
            quarter = 4
            year -= 1

        profit = self.get_profit_data(code, year, quarter)
        growth = self.get_growth_data(code, year, quarter)
        operation = self.get_operation_data(code, year, quarter)
        dupont = self.get_dupont_data(code, year, quarter)

        return {
            "code": code,
            "year": year,
            "quarter": quarter,
            "profit": profit,
            "growth": growth,
            "operation": operation,
            "dupont": dupont,
        }

    # ==================== 行业分类 ====================

    def get_industry(self, code: str) -> Optional[Dict]:
        """
        获取股票行业分类
        支持申万行业分类和证监会行业分类
        """
        bs = self._get_bs_client()
        if not bs:
            return None

        bs_code = self._to_baostock_code(code)

        try:
            # 获取证监会行业分类
            rs = bs.query_stock_industry(code=bs_code)
            if rs.error_code == '0' and rs.next():
                row = rs.get_row_data()
                return {
                    "code": row[1],
                    "name": row[2],
                    "industry": row[3],
                    "classification": row[4],
                }
        except Exception as e:
            logger.warning(f"获取行业分类失败 {code}: {e}")

        return None

    def get_industry_stocks(self, industry: str) -> List[str]:
        """
        获取指定行业的所有股票
        """
        bs = self._get_bs_client()
        if not bs:
            return []

        try:
            rs = bs.query_stock_industry()
            stocks = []
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                if row[3] == industry:  # 行业匹配
                    stocks.append(row[1])  # code
            return stocks
        except Exception as e:
            logger.warning(f"获取行业股票失败: {e}")

        return []

    # ==================== 指数成分股 ====================

    def get_index_stocks(self, index: str = "hs300") -> List[Dict]:
        """
        获取指数成分股
        index: hs300 (沪深300), sz50 (上证50), zz500 (中证500)
        """
        bs = self._get_bs_client()
        if not bs:
            return []

        try:
            if index == "hs300":
                rs = bs.query_hs300_stocks()
            elif index == "sz50":
                rs = bs.query_sz50_stocks()
            elif index == "zz500":
                rs = bs.query_zz500_stocks()
            else:
                logger.warning(f"不支持的指数: {index}")
                return []

            stocks = []
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                stocks.append({
                    "code": row[1],  # sh.600000
                    "name": row[2],  # 股票名称
                })
            return stocks

        except Exception as e:
            logger.warning(f"获取指数成分股失败 {index}: {e}")

        return []

    # ==================== 股票列表 ====================

    @staticmethod
    def _latest_qlib_trade_date() -> Optional[str]:
        """Return latest local Qlib calendar date not after today."""
        cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
        if not cal_path.exists():
            return None
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            dates = [line.strip() for line in cal_path.read_text().splitlines() if line.strip()]
            for trade_date in reversed(dates):
                if trade_date <= today:
                    return trade_date
        except Exception as e:
            logger.debug(f"读取 Qlib 交易日历失败: {e}")
        return None

    @staticmethod
    def _stock_query_dates(date: str | None) -> List[str]:
        if date:
            return [date]

        candidates: list[str] = []
        qlib_date = DataProvider._latest_qlib_trade_date()
        if qlib_date:
            candidates.append(qlib_date)

        today = datetime.now()
        for offset in range(0, 10):
            day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            if day not in candidates:
                candidates.append(day)
        return candidates

    def get_all_stocks(self, date: str = None) -> List[Dict]:
        """
        获取所有股票列表
        """
        tdx = self._get_tdx_provider()
        if tdx:
            stocks = tdx.get_all_stocks()
            if stocks:
                logger.info(f"从 TDX MCP 获取全市场股票列表: {len(stocks)} 只")
                return stocks

        bs = self._get_bs_client()
        if not bs:
            return self._get_all_stocks_from_qlib_features()

        for query_date in self._stock_query_dates(date):
            try:
                rs = bs.query_all_stock(day=query_date)
                stocks = []
                while (rs.error_code == '0') & rs.next():
                    row = rs.get_row_data()
                    # 只返回沪深 A 股，排除指数和基金；科创/创业板在上层筛选配置里决定是否排除
                    if row[0].startswith("sh.6") or row[0].startswith("sz.0") or row[0].startswith("sz.3"):
                        stocks.append({
                            "code": row[0],  # sh.600000
                            "code_name": row[2],  # 股票名称
                            "trade_status": row[1],  # 交易状态
                            "date": query_date,
                        })
                if stocks:
                    if query_date != date:
                        logger.info(f"获取全市场股票列表成功: {query_date}, {len(stocks)} 只")
                    return stocks
            except Exception as e:
                logger.warning(f"获取股票列表失败 {query_date}: {e}")

        return self._get_all_stocks_from_qlib_features()

    @staticmethod
    def _get_all_stocks_from_qlib_features() -> List[Dict]:
        """Use local Qlib feature directories as a true offline stock universe fallback."""
        features_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features"
        if not features_dir.exists():
            return []

        stocks = []
        for stock_dir in sorted(features_dir.iterdir()):
            if not stock_dir.is_dir():
                continue
            raw = stock_dir.name.lower()
            if raw.startswith("sh6"):
                code = f"sh.{raw[2:8]}"
            elif raw.startswith("sz0") or raw.startswith("sz3"):
                code = f"sz.{raw[2:8]}"
            else:
                continue
            stocks.append({
                "code": code,
                "code_name": code.replace(".", "").upper(),
                "trade_status": "1",
                "source": "qlib_features",
            })
        if stocks:
            logger.info(f"从 Qlib 本地行情目录加载股票范围: {len(stocks)} 只")
        return stocks

    # ==================== 辅助方法 ====================

    @staticmethod
    def _to_baostock_code(code: str) -> str:
        """转换代码格式：SH600000 -> sh.600000"""
        code = code.upper().strip()
        if code.startswith("SH"):
            return code.replace("SH", "sh.").replace("SZ", "sz.")
        elif code.startswith("SZ"):
            return code.replace("SZ", "sz.")
        elif code.startswith("sh.") or code.startswith("sz."):
            return code
        else:
            # 默认格式化为上海代码
            if code[0] == '6':
                return f"sh.{code}"
            else:
                return f"sz.{code}"

    @staticmethod
    def _from_baostock_code(code: str) -> str:
        """转换代码格式：sh.600000 -> SH600000"""
        if "." in code:
            market, symbol = code.split(".")
            return f"{market.upper()}{symbol}"
        return code

    def close(self):
        """关闭连接"""
        if self._bs_client:
            try:
                self._bs_client.logout()
                self._bs_client = None
                logger.info("Baostock 连接已关闭")
            except:
                pass


# 全局单例
_provider_instance = None


def get_provider() -> DataProvider:
    """获取数据提供者单例"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = DataProvider()
    return _provider_instance
