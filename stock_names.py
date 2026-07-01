"""
股票代码到名称的映射
包含 CSI300 主要成分股和常用 ETF
"""

import pandas as pd
import yfinance as yf

# 缓存已查询的股票名称
_NAME_CACHE = {}

# 股票名称映射表 (代码 -> 名称)
STOCK_NAMES = {
    # 金融板块
    "SH600000": "浦发银行", "SH600016": "民生银行", "SH600036": "招商银行",
    "SH601166": "兴业银行", "SH601288": "农业银行", "SH601318": "中国平安",
    "SH601328": "交通银行", "SH601398": "工商银行", "SH601601": "中国太保",
    "SH601939": "建设银行", "SH601988": "中国银行", "SH600030": "中信证券",
    "SH600999": "招商证券", "SH601688": "华泰证券", "SH600958": "东方证券",
    "SH600837": "海通证券", "SH601211": "国泰君安", "SH000001": "平安银行",

    # 科技板块
    "SZ000063": "中兴通讯", "SZ000725": "京东方A", "SZ002049": "同方股份",
    "SZ002415": "海康威视", "SZ002475": "立讯精密", "SZ300014": "亿纬锂能",
    "SZ300037": "新宙邦", "SZ300122": "智飞生物", "SZ300124": "汇川技术",
    "SZ300142": "沃森生物", "SZ300274": "阳光电源", "SZ300750": "宁德时代",
    "SZ300760": "迈瑞医疗", "SZ300999": "金龙鱼", "SH600584": "长电科技",
    "SH688012": "中微公司", "SH688111": "金山办公", "SH688396": "华润微",
    "SH688981": "中芯国际", "SH688008": "澜起科技", "SH688047": "龙芯中科",
    "SH688126": "沪硅产业", "SH688169": "石头科技", "SH688183": "生益科技",

    # 医药板块
    "SH600085": "同仁堂", "SH600196": "复星医药", "SH600276": "恒瑞医药",
    "SH600436": "片仔癀", "SH600521": "华海药业", "SH603259": "药明康德",
    "SH603288": "海天味业", "SZ000538": "云南白药", "SZ000661": "长春高新",
    "SZ000858": "五粮液", "SZ002007": "华兰生物", "SZ002821": "凯莱英",
    "SZ300015": "爱尔眼科", "SZ300347": "泰格医药",

    # 消费板块
    "SH600519": "贵州茅台", "SH600887": "伊利股份", "SH600809": "山西汾酒",
    "SH600132": "重庆啤酒", "SH600779": "水井坊", "SH605499": "东鹏饮料",
    "SZ000568": "泸州老窖", "SZ000895": "双汇发展", "SZ002304": "洋河股份",
    "SZ002352": "顺丰控股", "SZ002572": "索菲亚", "SZ002714": "牧原股份",

    # 新能源板块
    "SZ002129": "中环股份", "SZ002271": "东方雨虹", "SZ002460": "赣锋锂业",
    "SZ002594": "比亚迪", "SZ002812": "恩捷股份", "SZ300063": "中科创达",
    "SZ300450": "先导智能", "SZ300763": "锦浪科技", "SH600089": "特变电工",
    "SH601012": "隆基绿能", "SH601877": "正泰电器", "SH603806": "福斯特",

    # 半导体板块
    "SH600667": "太极实业", "SH603986": "兆易创新", "SZ002371": "北方华创",
    "SZ002384": "扬杰科技", "SZ002459": "晶澳科技",

    # 军工板块
    "SH600009": "上海机场", "SH600039": "四川路桥", "SH600893": "航发动力",
    "SH600118": "中国卫星", "SH600150": "中国船舶", "SH600316": "洪都航空",
    "SH600343": "航天动力", "SH600372": "中航电子", "SH600760": "中航沈飞",
    "SH600855": "航天长峰", "SZ002013": "中航机电", "SZ002025": "航天电器",
    "SZ002179": "中航光电", "SZ002389": "航天彩虹",

    # 有色板块
    "SH600111": "北方稀土", "SH600489": "中金黄金", "SH600547": "山东黄金",
    "SH600549": "厦门钨业", "SH600588": "用友网络", "SH601600": "中国铝业",
    "SH601899": "紫金矿业", "SH603993": "洛阳钼业", "SZ000060": "中金岭南",
    "SZ000830": "鲁西化工", "SZ000878": "云南铜业", "SZ002466": "天齐锂业",

    # ETF
    "SH510300": "沪深300ETF", "SH512880": "证券ETF", "SH512010": "医药ETF",
    "SH515030": "新能源车ETF", "SH512660": "军工ETF", "SH512400": "有色金属ETF",
    "SZ159995": "芯片ETF", "SH515880": "通信ETF",

    # 其他常用股票
    "SZ000001": "平安银行", "SZ000002": "万科A", "SZ000069": "华侨城A",
    "SZ000333": "美的集团", "SZ001979": "招商蛇口", "SZ002146": "荣盛发展",
    "SZ300059": "东方财富", "SH000300": "沪深300指数", "SH600048": "保利发展",
    "SH600383": "金地集团", "SH600606": "绿地控股", "SH600649": "城投控股",
    "SH600675": "中华企业", "SH600708": "光明地产", "SH600104": "上汽集团",
    "SH600031": "三一重工", "SH600309": "万华化学", "SZ000651": "格力电器",
    "SH600690": "海尔智家", "SH601888": "中国中免",
}

# 信息透明度评级 (基于分析师覆盖度和市值)
# 高透明度: 分析师覆盖>10, 大市值
# 中透明度: 分析师覆盖3-10, 中市值
# 低透明度: 分析师覆盖<3, 小市值
TRANSPARENCY_RATING = {
    # 高透明度 (大盘蓝筹)
    "HIGH": {
        "SH600519": "贵州茅台", "SH600036": "招商银行", "SH601398": "工商银行",
        "SH601318": "中国平安", "SH600030": "中信证券", "SZ000858": "五粮液",
        "SZ000333": "美的集团", "SZ002594": "比亚迪", "SZ300750": "宁德时代",
        "SH600276": "恒瑞医药", "SZ300760": "迈瑞医疗", "SH601288": "农业银行",
        "SH601939": "建设银行", "SH600887": "伊利股份", "SZ000538": "云南白药",
        "SH688981": "中芯国际", "SZ002415": "海康威视", "SH600196": "复星医药",
        "SZ300015": "爱尔眼科", "SH601988": "中国银行", "SZ300124": "汇川技术",
        "SZ002475": "立讯精密", "SH601328": "交通银行", "SZ000001": "平安银行",
        "SH601166": "兴业银行", "SH600000": "浦发银行", "SZ002304": "洋河股份",
        "SH603259": "药明康德", "SZ300122": "智飞生物", "SZ300347": "泰格医药",
        "SZ300142": "沃森生物", "SZ300274": "阳光电源", "SH601012": "隆基绿能",
        "SH601899": "紫金矿业", "SZ000661": "长春高新", "SH600809": "山西汾酒",
        "SH600547": "山东黄金", "SZ002460": "赣锋锂业", "SZ000895": "双汇发展",
        "SH601888": "中国中免", "SH600309": "万华化学", "SH600104": "上汽集团",
    },
    # 低透明度 (小盘、新兴行业)
    "LOW": {
        "SZ002821": "凯莱英", "SZ002007": "华兰生物", "SH600436": "片仔癀",
        "SH600521": "华海药业", "SH600085": "同仁堂", "SZ002146": "荣盛发展",
        "SH600708": "光明地产", "SH600675": "中华企业", "SH600383": "金地集团",
        "SH600606": "绿地控股", "SZ000656": "金科股份", "SZ002572": "索菲亚",
        "SH600779": "水井坊", "SZ002839": "张家界", "SH605499": "东鹏饮料",
        "SZ300999": "金龙鱼", "SZ300037": "新宙邦", "SZ300450": "先导智能",
        "SZ002459": "晶澳科技", "SH688012": "中微公司", "SH688396": "华润微",
        "SH688111": "金山办公", "SH688047": "龙芯中科", "SH688169": "石头科技",
        "SH688008": "澜起科技", "SH688126": "沪硅产业", "SH688183": "生益科技",
        "SH600118": "中国卫星", "SH600316": "洪都航空", "SH600150": "中国船舶",
        "SH600893": "航发动力", "SZ002025": "航天电器", "SZ002179": "中航光电",
        "SZ002389": "航天彩虹", "SZ002013": "中航机电",
    },
}


def get_stock_name(code: str) -> str:
    """获取股票名称，如果找不到则返回代码"""
    if not code:
        return "未知"

    code_upper = str(code).upper().strip()

    # 检查缓存
    if code_upper in _NAME_CACHE:
        return _NAME_CACHE[code_upper]

    # 1. 直接匹配
    if code_upper in STOCK_NAMES:
        _NAME_CACHE[code_upper] = STOCK_NAMES[code_upper]
        return STOCK_NAMES[code_upper]

    # 2. 去掉前缀后匹配
    pure_code = code_upper.replace("SH", "").replace("SZ", "")

    # 先尝试精确匹配去掉前缀的代码
    if pure_code in STOCK_NAMES:
        _NAME_CACHE[code_upper] = STOCK_NAMES[pure_code]
        return STOCK_NAMES[pure_code]

    # 3. 遍历所有股票代码，找到匹配的
    for stock_code, name in STOCK_NAMES.items():
        stock_pure = stock_code.replace("SH", "").replace("SZ", "")
        if stock_pure == pure_code:
            _NAME_CACHE[code_upper] = name
            return name

    # 4. akshare 全市场中文名兜底（首次 miss 时懒加载一次，之后纯内存查）
    auto_name = _lookup_auto_name(code_upper)
    if auto_name:
        _NAME_CACHE[code_upper] = auto_name
        return auto_name

    # 5. 根据代码前缀推断市场。不要在热路径调用 yfinance，避免接口被外部网络拖慢。
    if pure_code.startswith(("6", "51", "50")):
        market = "沪市"
    elif pure_code.startswith(("0", "3", "15", "16")):
        market = "深市"
    else:
        market = "未知"

    result = f"{code_upper}({market})"
    _NAME_CACHE[code_upper] = result
    return result


def get_transparency_level(code: str) -> str:
    """
    获取股票信息透明度评级

    返回:
        "HIGH" - 高透明度 (大盘蓝筹，分析师覆盖多)
        "MEDIUM" - 中透明度 (默认)
        "LOW" - 低透明度 (小盘新兴，量化交易聚集)
    """
    code_upper = code.upper().strip()
    if code_upper in TRANSPARENCY_RATING["HIGH"]:
        return "HIGH"
    if code_upper in TRANSPARENCY_RATING["LOW"]:
        return "LOW"
    return "MEDIUM"


def get_transparency_name(level: str) -> str:
    """获取透明度级别的中文名称"""
    return {"HIGH": "高透明度", "MEDIUM": "中透明度", "LOW": "低透明度"}.get(level, "未知")


def add_stock_names_to_df(df: pd.DataFrame, code_col: str = "代码") -> pd.DataFrame:
    """
    为 DataFrame 添加股票名称列

    Args:
        df: 原始数据框
        code_col: 股票代码列名

    Returns:
        添加了"名称"列的 DataFrame
    """
    if code_col in df.columns:
        df["名称"] = df[code_col].apply(get_stock_name)
    return df


def add_transparency_to_df(df: pd.DataFrame, code_col: str = "代码") -> pd.DataFrame:
    """
    为 DataFrame 添加透明度评级列

    Args:
        df: 原始数据框
        code_col: 股票代码列名

    Returns:
        添加了"透明度"列的 DataFrame
    """
    if code_col in df.columns:
        df["透明度"] = df[code_col].apply(lambda x: get_transparency_name(get_transparency_level(x)))
        df["透明度级别"] = df[code_col].apply(get_transparency_level)
    return df


# ── akshare 全市场股票中文名懒加载（首次 miss 时触发一次）──
_AUTO_NAMES = None
_AUTO_LOADED = False


def _load_auto_names() -> dict:
    """从 akshare 加载全市场 A 股中文名映射。失败返回空 dict。"""
    global _AUTO_NAMES
    try:
        import akshare as ak
        # stock_info_a_code_name 返回 code/name 两列，覆盖全市场 A 股
        df = ak.stock_info_a_code_name()
        mapping = {}
        for _, row in df.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip()
            if not code or not name:
                continue
            # 还原成 Qlib 格式前缀
            if code.startswith(("60", "68", "51", "50", "56", "58")):
                qlib_code = "SH" + code
            elif code.startswith(("00", "30", "15", "16")):
                qlib_code = "SZ" + code
            elif code.startswith(("43", "83", "87", "92", "88")):
                qlib_code = "BJ" + code
            else:
                qlib_code = code
            mapping[qlib_code] = name
        return mapping
    except Exception:
        return {}


def _lookup_auto_name(code_upper: str) -> str:
    """懒加载全市场名表后查名字，找不到返回空串。"""
    global _AUTO_NAMES, _AUTO_LOADED
    if not _AUTO_LOADED:
        _AUTO_NAMES = _load_auto_names()
        _AUTO_LOADED = True
    if _AUTO_NAMES:
        return _AUTO_NAMES.get(code_upper, "")
    return ""
