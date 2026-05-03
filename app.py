"""Qlib 分析看板 - Streamlit 界面 v3

数据源：yfinance（WSL2 下 akshare 直连失败，改用 yfinance）
启动：
    cd /home/jason/projects/qlib-workspace
    ./venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import os
import multiprocessing

# ── 修复 Qlib 多进程与 Streamlit 冲突 ──
# 设置多进程启动方式为 forkserver，避免 broken pipe 错误
try:
    multiprocessing.set_start_method('forkserver', force=True)
except RuntimeError:
    # 已经设置过，忽略
    pass

# 限制 OpenMP 线程数
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import pathlib
from datetime import timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

# 导入股票名称映射
from stock_names import (
    get_stock_name, get_transparency_level, get_transparency_name,
    add_stock_names_to_df, add_transparency_to_df
)
# 导入散户因子模块
from retail_factors import (
    RetailFactorCollector, calc_position_size, calc_portfolio_stop_loss,
    calc_transaction_cost_adjustment, estimate_realistic_return,
    calc_tail_risk_metric, calc_retail_sentiment
)

# ── 页面配置 ──
st.set_page_config(
    page_title="Qlib A股量化分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 自定义样式 ──
st.markdown("""
<style>
.metric-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}
.good { color: #22c55e; }
.bad  { color: #ef4444; }
.warn { color: #eab308; }
</style>
""", unsafe_allow_html=True)


# ── Qlib 初始化 ──
# 用 cache_resource 保证进程内只初始化一次，避免 QlibRecorder 重复激活报错。
# 日历范围/最新日期改用 get_calendar_range() 直接读文件，不依赖 Qlib 内部缓存。
@st.cache_resource
def init_qlib(data_dir: str):
    try:
        import qlib
        from qlib.config import REG_CN
        qlib.init(provider_uri=data_dir, region=REG_CN)
        return True, None
    except Exception as e:
        return False, str(e)


def get_calendar_range(data_dir: str) -> tuple:
    """直接读文件，绕过 Qlib 内部缓存，获取真实日期范围"""
    import pathlib
    cal_path = pathlib.Path(data_dir) / "calendars" / "day.txt"
    if not cal_path.exists():
        return None, None
    with open(cal_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None, None
    return pd.Timestamp(lines[0]).date(), pd.Timestamp(lines[-1]).date()


# ── 代码转换：本地格式 → Yahoo Finance 格式 ──
def _to_yf_code(code: str) -> str:
    """把各种格式的代码统一转为 Yahoo Finance 格式

    输入支持：510300 / SH510300 / sh510300 / 600519
    输出：510300.SS / 600519.SS / 000001.SZ 等
    """
    # 去掉 SH/SZ 前缀
    pure = code.upper()
    if pure.startswith(("SH", "SZ")):
        pure = pure[2:]
    pure = pure.split(".")[0]  # 去掉已有后缀

    # 判断市场
    if pure.startswith(("6", "51", "50")):
        return f"{pure}.SS"
    elif pure.startswith(("0", "3", "15", "16")):
        return f"{pure}.SZ"
    else:
        return f"{pure}.SS"  # 默认上交所


# ── 数据工具函数（yfinance）──
@st.cache_data(ttl=300)
def get_stock_data_ak(code: str, start: str, end: str) -> pd.DataFrame:
    """用 yfinance 拉取行情数据（WSL2 下 akshare 直连失败）"""
    import yfinance as yf

    yf_code = _to_yf_code(code)
    try:
        t = yf.Ticker(yf_code)
        df = t.history(start=start, end=end, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        df.index = df.index.tz_localize(None)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df["amount"] = df["close"] * df["volume"]
        # 计算日涨跌幅
        df["pct_chg"] = df["close"].pct_change() * 100
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume", "amount", "pct_chg"]].dropna(subset=["close"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def get_qlib_data(instruments: list, fields: list, start: str, end: str):
    """从 Qlib 数据库读取数据"""
    try:
        from qlib.data import D
        return D.features(instruments, fields, start_time=start, end_time=end)
    except Exception as e:
        return pd.DataFrame()


def calc_ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def calc_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    return dif, dea, dif - dea


# ── 边栏 ──
st.sidebar.title("📊 Qlib 量化分析")
st.sidebar.markdown("---")

# 数据源选择
data_source = st.sidebar.radio(
    "数据源",
    ["yfinance（最新，至今）", "Qlib 本地（~2020）"],
    index=0,
)

QLIB_DIR_OLD = str(os.path.expanduser("~/.qlib/qlib_data/cn_data"))
QLIB_DIR_NEW = str(os.path.expanduser("~/.qlib/qlib_data/cn_data_akshare"))

if data_source == "Qlib 本地（~2020）":  # noqa
    qlib_ok, qlib_err = init_qlib(QLIB_DIR_OLD)
    if qlib_ok:
        st.sidebar.success("Qlib 已连接（数据至2020年）")
    else:
        st.sidebar.error(f"Qlib 连接失败: {qlib_err}")

# 页面导航
page = st.sidebar.radio(
    "功能模块",
    ["🏠 首页", "🔥 主题热点", "📈 行情分析", "🔬 因子分析", "⚡ 模型回测",
     "📉 均值回归", "🔗 配对交易", "🔄 ETF轮动信号", "🎯 ETF全量筛选", "📥 数据管理"],
)

st.sidebar.markdown("---")
st.sidebar.caption("数据来源: yfinance（实时）+ Qlib（历史）")

# ═══════════════════════════════════════════════════════
# 页面：首页
# ═══════════════════════════════════════════════════════
if page == "🏠 首页":
    st.title("📊 Qlib A股量化分析平台")
    st.markdown("基于 **Microsoft Qlib** + **yfinance** 的个人量化研究工具")

    # 快速状态
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        import pathlib
        old_dir = pathlib.Path(QLIB_DIR_OLD)
        stocks_old = len(list(old_dir.glob("features/*/close.day.bin"))) if old_dir.exists() else 0
        _ds, _de = get_calendar_range(QLIB_DIR_OLD)
        _de_str = str(_de) if _de else "2020-09"
        st.metric("Qlib历史数据", f"{stocks_old} 只", f"截止{_de_str}")

    with col2:
        new_dir = pathlib.Path(QLIB_DIR_NEW)
        stocks_new = len(list(new_dir.glob("features/*/close.day.bin"))) if new_dir.exists() else 0
        st.metric("yfinance数据", f"{stocks_new} 只", "2015至今" if stocks_new > 0 else "未收集")

    with col3:
        # 获取今日大盘
        try:
            df_hs300 = get_stock_data_ak("SH510300", "2024-01-01",
                                          pd.Timestamp.now().strftime("%Y-%m-%d"))
            if not df_hs300.empty:
                latest = df_hs300.iloc[-1]
                pct = df_hs300["pct_chg"].iloc[-1] if "pct_chg" in df_hs300.columns else 0
                st.metric("沪深300ETF", f"{latest['close']:.3f}",
                          f"{pct:+.2f}%" if pct else "")
            else:
                st.metric("沪深300ETF", "获取中...", "")
        except:
            st.metric("沪深300ETF", "--", "")

    with col4:
        st.metric("Qlib版本", "0.9.7", "Alpha158就绪")

    st.markdown("---")

    # 功能说明
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 功能模块")
        st.markdown("""
| 模块 | 功能 |
|------|------|
| 📈 行情分析 | K线图、技术指标（MA/RSI/MACD）|
| 🔬 因子分析 | Alpha158因子值、IC分析 |
| ⚡ 模型回测 | LightGBM训练、Sharpe/IC/回撤 |
| 🔄 ETF轮动 | 8个行业ETF预测收益排名 |
| 📥 数据管理 | akshare增量更新数据 |
""")

    with col2:
        st.subheader("🚀 快速开始")
        st.code("""
# 1. 查看行情 → 左侧选"行情分析"，输入代码
# 2. 跑回测  → 左侧选"模型回测"，点击训练
# 3. ETF信号 → 左侧选"ETF轮动信号"
# 4. 更新数据 → 左侧选"数据管理"

# 或命令行：
cd /home/jason/projects/qlib-workspace
./venv/bin/python data_collector.py --action update
""", language="bash")

    # ── 多策略组合框架 ──
    st.markdown("---")
    st.subheader("💼 多策略组合框架")

    # 策略分配
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.markdown("**策略资金分配**")

        # 使用 session_state 保持分配比例
        if "factor_alloc" not in st.session_state:
            st.session_state.factor_alloc = 60
            st.session_state.theme_alloc = 30
            st.session_state.etf_alloc = 10

        # 滑块调整分配
        factor = st.slider(
            "因子策略 (CSI300)", 0, 100, st.session_state.factor_alloc, 5,
            help="基于Alpha158因子的稳健收益策略"
        )
        theme = st.slider(
            "主题轮动", 0, 100, st.session_state.theme_alloc, 5,
            help="捕捉热点板块的爆发性机会"
        )
        etf = st.slider(
            "ETF配置", 0, 100, st.session_state.etf_alloc, 5,
            help="大类资产配置与风险控制"
        )

        # 更新 session_state
        st.session_state.factor_alloc = factor
        st.session_state.theme_alloc = theme
        st.session_state.etf_alloc = etf

        total = factor + theme + etf
        if total != 100:
            st.warning(f"⚠️ 当前总和: {total}%，建议调整为100%")
        else:
            st.success(f"✅ 资金分配: 因子{factor}% + 主题{theme}% + ETF{etf}%")

    with col2:
        st.markdown("**策略特点**")
        st.info("""
        **因子策略**
        - 稳健Alpha
        - 价值/质量
        - 长期持有
        """)

    with col3:
        st.markdown("**当前状态**")
        if total == 100:
            # 假设总资金100万
            capital = st.number_input("总资金(万)", 10, 1000, 100, key="total_capital")
            st.metric("因子配置", f"{capital * factor / 100:.1f}万")
            st.metric("主题配置", f"{capital * theme / 100:.1f}万")
            st.metric("ETF配置", f"{capital * etf / 100:.1f}万")

    # 策略说明
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        ### 📊 因子策略 ({}%)
        - **标的**: CSI300成分股
        - **选股**: Alpha158因子 + LightGBM
        - **调仓**: 周度
        - **特点**: 稳健、低换手
        - **操作**: → ⚡ 模型回测
        """.format(factor))

    with col2:
        st.markdown("""
        ### 🔥 主题轮动 ({}%)
        - **标的**: 热点概念板块
        - **选股**: 涨幅 + 资金流入
        - **调仓**: 灵活
        - **特点**: 高弹性、捕捉热点
        - **操作**: → 🔥 主题热点
        """.format(theme))

    with col3:
        st.markdown("""
        ### 🔄 ETF配置 ({}%)
        - **标的**: 行业/宽基ETF
        - **选股**: 技术指标轮动
        - **调仓**: 月度
        - **特点**: 风险分散
        - **操作**: → 🔄 ETF轮动信号
        """.format(etf))

    # 今日ETF行情概览
    st.subheader("📊 今日行业ETF行情")
    etfs = {
        "沪深300ETF": "510300", "证券ETF": "512880", "医药ETF": "512010",
        "新能源车": "515030", "军工ETF": "512660", "有色金属": "512400",
        "芯片ETF": "159995", "通信ETF": "515880",
    }
    rows = []
    end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    progress = st.progress(0)
    for i, (name, code) in enumerate(etfs.items()):
        prefix = "SH" if code.startswith("5") else "SZ"
        df = get_stock_data_ak(f"{prefix}{code}", start_date, end_date)
        if not df.empty and len(df) >= 2:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            pct = (latest["close"] / prev["close"] - 1) * 100
            rows.append({
                "名称": name, "代码": code,
                "最新价": f"{latest['close']:.3f}",
                "涨跌幅": f"{pct:+.2f}%",
                "5日动量": f"{(df['close'].iloc[-1]/df['close'].iloc[-5]-1)*100:+.2f}%" if len(df) >= 5 else "--",
                "成交量": f"{latest.get('volume', 0)/10000:.0f}万手",
            })
        progress.progress((i + 1) / len(etfs))

    if rows:
        df_show = pd.DataFrame(rows)
        # 添加名称列
        df_show["名称"] = df_show["代码"].apply(lambda x: x)  # ETF名称已在行中
        # 重新排列列顺序，名称放在代码后面
        cols = df_show.columns.tolist()
        if "名称" in cols:
            code_idx = cols.index("代码")
            cols.insert(code_idx + 1, cols.pop(cols.index("名称")))
            df_show = df_show[cols]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
    progress.empty()

    # ── 大盘趋势状态 (200日均线) ──
    st.markdown("---")
    st.subheader("📈 大盘趋势状态 (MA200)")

    col1, col2, col3, col4 = st.columns(4)

    # 获取沪深300长期数据
    try:
        df_trend = get_stock_data_ak("SH510300", "2023-01-01", pd.Timestamp.now().strftime("%Y-%m-%d"))
        if not df_trend.empty and len(df_trend) >= 200:
            close = df_trend["close"]
            ma200 = calc_ma(close, 200).iloc[-1]
            ma60 = calc_ma(close, 60).iloc[-1]
            current_price = close.iloc[-1]

            # 趋势判断
            above_ma200 = current_price > ma200
            above_ma60 = current_price > ma60
            ma60_above_ma200 = ma60 > ma200

            # 趋势状态
            if above_ma200 and ma60_above_ma200:
                trend_status = "🟢 强势上升趋势"
                trend_color = "good"
                position建议 = "可满仓操作"
            elif above_ma200 and not ma60_above_ma200:
                trend_status = "🟡 震荡整理"
                trend_color = "warn"
                position建议 = "控制仓位5-6成"
            elif not above_ma200 and ma60_above_ma200:
                trend_status = "🟡 可能企稳"
                trend_color = "warn"
                position建议 = "观望为主，轻仓试探"
            else:
                trend_status = "🔴 下降趋势"
                trend_color = "bad"
                position建议 = "空仓或极低仓位"

            with col1:
                st.metric("当前价格", f"{current_price:.3f}")
            with col2:
                st.metric("MA200", f"{ma200:.3f}", "上方" if above_ma200 else "下方")
            with col3:
                st.metric("MA60", f"{ma60:.3f}", "上方" if above_ma60 else "下方")
            with col4:
                st.markdown(f"**趋势状态**\n\n<span class='{trend_color}'>{trend_status}</span>",
                          unsafe_allow_html=True)

            # 仓位建议
            st.info(f"💡 **仓位建议**: {position建议}")

            # 趋势图
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_trend.index[-252:],  # 显示近一年
                y=close.iloc[-252:],
                name="沪深300",
                line=dict(color="#8b5cf6", width=2)
            ))
            fig.add_trace(go.Scatter(
                x=df_trend.index[-252:],
                y=calc_ma(close, 200).iloc[-252:],
                name="MA200",
                line=dict(color="#ef4444", width=1.5, dash="dash")
            ))
            fig.add_trace(go.Scatter(
                x=df_trend.index[-252:],
                y=calc_ma(close, 60).iloc[-252:],
                name="MA60",
                line=dict(color="#22c55e", width=1.5, dash="dash")
            ))
            fig.update_layout(
                title="沪深300趋势图",
                template="plotly_dark",
                height=300,
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("数据不足，无法计算MA200")
    except Exception as e:
        st.warning(f"趋势数据获取失败: {e}")

    # ── 策略信号快速汇总 ──
    st.markdown("---")
    st.subheader("📋 本周策略信号汇总")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        ### 各策略状态

        | 策略 | 状态 | 操作建议 |
        |------|------|----------|
        | 📉 均值回归 | 扫描超买超卖 | 点击左侧查看详情 |
        | 🔗 配对交易 | 寻找协整机会 | 点击左侧查看详情 |
        | ⚡ 模型回测 | LightGBM预测 | 点击左侧查看操作建议 |
        | 🔥 主题热点 | 板块轮动监控 | 点击左侧查看热点板块 |
        | 🔄 ETF轮动 | 行业ETF评分 | 点击左侧查看轮动信号 |
        """)

    with col2:
        st.markdown("""
        ### 快速导航

        **选股流程**：
        1. 查看 📉 均值回归 - 发现超卖机会
        2. 查看 🔥 主题热点 - 确认热点板块
        3. 查看 ⚡ 模型回测 - 获取因子评分

        **风控检查**：
        - 确认大盘趋势状态（上方）
        - 趋势不好时降低仓位
        - 设置止损位 -8%
        """)

    # 策略冲突提示
    st.info("""
    💡 **多策略使用提示**：
    - 当多个策略同时给出买入信号时，置信度更高
    - 当策略信号冲突时，优先参考大盘趋势状态
    - 下降趋势中，只关注均值回归的超卖机会
    """)


# ═══════════════════════════════════════════════════════
# 页面：主题热点
# ═══════════════════════════════════════════════════════
elif page == "🔥 主题热点":
    st.title("🔥 主题热点监控")
    st.caption("基于统一股票池 (CSI300) + yfinance 数据，与因子分析保持一致")

    # 导入统一股票池配置
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from stock_universe import (
        CSI300_SECTORS, yf_code_to_qlib, qlib_code_to_yf,
        get_stock_sector, get_csi300_stocks
    )

    # 显示数据状态
    col1, col2, col3 = st.columns(3)
    with col1:
        import pathlib
        old_cal = pathlib.Path(QLIB_DIR_OLD) / "calendars" / "day.txt"
        if old_cal.exists():
            with open(old_cal) as f:
                lines = f.readlines()
                latest_date = lines[-1].strip() if lines else "未知"
            st.metric("Qlib 数据日期", latest_date)
        else:
            st.metric("Qlib 数据日期", "未知")

    with col2:
        total_stocks = sum(len(v) for v in CSI300_SECTORS.values())
        st.metric("覆盖股票", f"{total_stocks}只")

    with col3:
        st.metric("覆盖板块", f"{len(CSI300_SECTORS)}个")

    st.markdown("---")

    # 参数设置
    col1, col2, col3 = st.columns(3)
    with col1:
        lookback = st.selectbox("统计周期", [5, 10, 20], index=1)
    with col2:
        show_factor_score = st.checkbox("显示因子评分", value=True,
                                        help="需要先运行模型回测生成因子评分")
    with col3:
        auto_refresh = st.checkbox("自动刷新", value=False)

    # 数据更新提示
    col1, col2 = st.columns(2)
    with col1:
        # 先检查数据是否需要更新
        import subprocess
        try:
            check_result = subprocess.run(
                ["./venv/bin/python", "update_cn_data.py", "--check"],
                cwd=pathlib.Path(__file__).parent,
                capture_output=True,
                text=True,
                timeout=60
            )
            # 解析最新日期
            latest_date = None
            for line in check_result.stdout.split('\n'):
                if '最新=' in line and '2026' in line:
                    parts = line.split('最新=')
                    if len(parts) > 1:
                        latest_date = parts[1].split(',')[0].strip()
                        break
        except:
            latest_date = None

        # 显示数据状态
        if latest_date:
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            if latest_date >= today:
                st.success(f"✅ 数据已是最新 ({latest_date})，无需更新")
            else:
                st.info(f"📊 数据日期: {latest_date}，今天: {today}")

        if st.button("🔄 更新 Qlib 数据", help="用 yfinance 最新数据更新 Qlib 数据库"):
            # 如果数据已是最新的，提示用户
            if latest_date and latest_date >= pd.Timestamp.now().strftime("%Y-%m-%d"):
                st.info("✅ 数据已经是最新的，无需更新！")
            else:
                with st.spinner("正在更新数据...（约需5-10分钟）"):
                    try:
                        # 使用较小的样本数进行快速更新
                        result = subprocess.run(
                            ["./venv/bin/python", "update_cn_data.py", "--max", "500"],
                            cwd=pathlib.Path(__file__).parent,
                            capture_output=True,
                            text=True,
                            timeout=1800  # 30分钟
                        )
                        if result.returncode == 0:
                            st.success("✅ 数据更新完成！请刷新页面查看最新数据。")
                            st.cache_data.clear()
                        else:
                            st.error(f"❌ 更新失败: {result.stderr[-200:] if len(result.stderr) > 200 else result.stderr}")
                    except subprocess.TimeoutExpired:
                        st.warning("⏰ 更新超时，请稍后在命令行手动运行")
                    except Exception as e:
                        st.error(f"更新出错: {e}")

    with col2:
        if st.button("📋 查看数据状态", help="查看 Qlib 数据库状态"):
            import subprocess
            try:
                result = subprocess.run(
                    ["./venv/bin/python", "update_cn_data.py", "--check"],
                    cwd=pathlib.Path(__file__).parent,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                st.code(result.stdout)
            except Exception as e:
                st.error(f"检查失败: {e}")

    st.markdown("---")

    # 分析板块涨跌幅
    if st.button("🔍 分析板块涨跌幅", type="primary") or auto_refresh:
        with st.spinner("正在计算板块涨跌幅..."):
            try:
                import yfinance as yf
                end_date = pd.Timestamp.now()
                start_date = end_date - pd.Timedelta(days=lookback + 10)

                results = []

                for sector, codes in CSI300_SECTORS.items():
                    sector_data = []

                    for code in codes[:15]:  # 每个板块取前15只
                        yf_code = qlib_code_to_yf(code)
                        try:
                            ticker = yf.Ticker(yf_code)
                            df = ticker.history(start=start_date, end=end_date, auto_adjust=False)

                            if not df.empty and len(df) >= lookback:
                                start_idx = -lookback - 1 if len(df) > lookback else 0
                                start_price = df['Close'].iloc[start_idx]
                                end_price = df['Close'].iloc[-1]
                                pct_change = (end_price - start_price) / start_price * 100

                                sector_data.append({
                                    "代码": code,
                                    "涨跌幅%": pct_change,
                                    "最新价": end_price,
                                })
                        except:
                            continue

                    if sector_data:
                        avg_change = sum(d["涨跌幅%"] for d in sector_data) / len(sector_data)
                        results.append({
                            "板块": sector,
                            "平均涨跌幅%": avg_change,
                            "成分股数": len(sector_data),
                            "成分股": sector_data,
                        })

                # 排序
                results.sort(key=lambda x: x["平均涨跌幅%"], reverse=True)

                if results:
                    # 显示板块排行
                    st.subheader("📊 行业板块涨跌幅排行")

                    # 柱状图
                    fig_data = pd.DataFrame([
                        {"板块": r["板块"], "涨跌幅%": r["平均涨跌幅%"]}
                        for r in results
                    ])

                    fig = px.bar(
                        fig_data,
                        x="涨跌幅%",
                        y="板块",
                        orientation="h",
                        color="涨跌幅%",
                        color_continuous_scale="RdYlGn_r",
                        title=f"近{lookback}日板块涨跌幅 (统一股票池: CSI300)",
                        height=400,
                    )
                    fig.update_layout(
                        template="plotly_dark",
                        yaxis={"categoryorder": "total ascending"},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # 详细表格
                    for r in results:
                        with st.expander(
                            f"{'🟢' if r['平均涨跌幅%'] > 0 else '🔴'} "
                            f"{r['板块']} ({r['平均涨跌幅%']:+.2f}%) - "
                            f"{r['成分股数']}只成分股"
                        ):
                            stocks_df = pd.DataFrame(r["成分股"])
                            stocks_df = stocks_df.sort_values("涨跌幅%", ascending=False)
                            stocks_df["收益"] = stocks_df["涨跌幅%"].apply(
                                lambda x: f"{x:+.2f}%"
                            )

                            # 添加名称列
                            stocks_df["名称"] = stocks_df["代码"].apply(get_stock_name)

                            # 添加透明度列
                            stocks_df["透明度"] = stocks_df["代码"].apply(
                                lambda x: get_transparency_name(get_transparency_level(x))
                            )

                            # 如果开启因子评分显示，尝试获取因子数据
                            if show_factor_score:
                                # 这里可以尝试从 session_state 获取之前的因子评分
                                if "factor_scores" in st.session_state:
                                    factor_scores = st.session_state.factor_scores
                                    stocks_df["因子评分"] = stocks_df["代码"].apply(
                                        lambda x: f"{factor_scores.get(x.upper(), 0):.4f}"
                                    )

                            display_cols = ["代码", "名称", "透明度", "最新价", "收益"]
                            if show_factor_score and "因子评分" in stocks_df.columns:
                                display_cols.append("因子评分")

                            st.dataframe(
                                stocks_df[display_cols],
                                use_container_width=True,
                                hide_index=True,
                            )

                    # 操作建议
                    st.markdown("---")
                    st.subheader("💡 操作建议")

                    top_sector = results[0]
                    if top_sector["平均涨跌幅%"] > 3:
                        st.success(f"""
                        🔥 **{top_sector['板块']}** 表现强势 (+{top_sector['平均涨跌幅%']:.2f}%)

                        **建议**:
                        - 可关注该板块回调后的介入机会
                        - 重点跟踪板块龙头股
                        - 结合因子分析优选个股
                        - 设置止损位 -8%
                        """)
                    elif top_sector["平均涨跌幅%"] > 0:
                        st.info(f"""
                        📈 **{top_sector['板块']}** 相对强势 (+{top_sector['平均涨跌幅%']:.2f}%)

                        **建议**: 谨慎参与，等待更明确的信号
                        """)
                    else:
                        st.warning(f"""
                        📉 所有板块近期表现较弱，建议观望

                        当前最强: {top_sector['板块']} ({top_sector['平均涨跌幅%']:+.2f}%)
                        """)

                    # 与因子分析关联的提示
                    if show_factor_score:
                        st.info("""
                        💡 **提示**: 要查看个股的因子评分，请先到 "🔬 因子分析" 或 "⚡ 模型回测" 运行模型，
                        然后返回这里即可看到因子评分。
                        """)

                else:
                    st.error("未能获取板块数据，请检查网络连接")

            except Exception as e:
                st.error(f"分析失败: {e}")
                import traceback
                with st.expander("查看错误详情"):
                    st.code(traceback.format_exc())
    # 使用说明
    with st.expander("💡 使用说明"):
        st.markdown("""
        ### 如何使用主题热点监控？

        1. **看热点**：关注涨幅靠前的行业板块，这些都是当前资金追逐的方向

        2. **找龙头**：点击板块展开，查看成分股涨跌幅

        3. **结合因子**：对于热点板块中的股票，可以切换到"⚡ 模型回测"查看因子评分

        4. **风险提示**：
           - 板块轮动快，不要追高
           - 建议等待回调后再介入
           - 设置止损位（-10%）

        ### 策略建议

        | 情况 | 操作 |
        |------|------|
        | 板块涨幅 > 5% | 关注，等待回调 |
        | 板块回调后再次启动 | 介入龙头股 |
        | 热点持续 > 3天 | 可能是趋势，可参与 |
        | 所有板块下跌 | 观望，空仓等待 |
        """)


# ═══════════════════════════════════════════════════════
# 页面：行情分析
# ═══════════════════════════════════════════════════════
elif page == "📈 行情分析":
    st.title("📈 行情分析")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        code_input = st.text_input("股票/ETF代码", value="510300",
                                   help="输入6位代码，如 510300（沪深300ETF）或 600519（茅台）")
    with col2:
        period = st.selectbox("周期", ["近6个月", "近1年", "近3年", "近5年", "自定义"])
    with col3:
        indicators = st.multiselect("技术指标", ["MA5", "MA20", "MA60", "布林带", "RSI", "MACD"],
                                    default=["MA5", "MA20"])

    # 日期范围
    now = pd.Timestamp.now()
    period_map = {"近6个月": 180, "近1年": 365, "近3年": 1095, "近5年": 1825}
    if period == "自定义":
        c1, c2 = st.columns(2)
        start_date = c1.date_input("开始日期", value=(now - pd.Timedelta(days=365)).date()).strftime("%Y-%m-%d")
        end_date = c2.date_input("结束日期", value=now.date()).strftime("%Y-%m-%d")
    else:
        days = period_map.get(period, 365)
        start_date = (now - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

    if st.button("查询", type="primary"):
        pure = code_input.strip().zfill(6)
        prefix = "SH" if pure.startswith(("51", "50", "60")) else "SZ"
        full_code = f"{prefix}{pure}"

        with st.spinner(f"拉取 {full_code} 数据..."):
            df = get_stock_data_ak(full_code, start_date, end_date)

        if df.empty:
            st.error(f"未找到 {pure} 的数据，请检查代码")
        else:
            # 计算技术指标
            close = df["close"]
            if "MA5" in indicators:   df["MA5"]  = calc_ma(close, 5)
            if "MA20" in indicators:  df["MA20"] = calc_ma(close, 20)
            if "MA60" in indicators:  df["MA60"] = calc_ma(close, 60)
            if "布林带" in indicators:
                df["BB_mid"] = calc_ma(close, 20)
                std = close.rolling(20).std()
                df["BB_upper"] = df["BB_mid"] + 2 * std
                df["BB_lower"] = df["BB_mid"] - 2 * std
            if "RSI" in indicators:   df["RSI"]  = calc_rsi(close)
            if "MACD" in indicators:
                df["DIF"], df["DEA"], df["MACD_hist"] = calc_macd(close)

            # 指标摘要
            latest = df.iloc[-1]
            prev   = df.iloc[-2] if len(df) > 1 else latest
            pct_1d = (latest["close"] / prev["close"] - 1) * 100
            pct_5d = (latest["close"] / df.iloc[-5]["close"] - 1) * 100 if len(df) >= 5 else 0
            pct_20d = (latest["close"] / df.iloc[-20]["close"] - 1) * 100 if len(df) >= 20 else 0

            cols = st.columns(5)
            cols[0].metric("最新价", f"{latest['close']:.3f}")
            cols[1].metric("1日涨跌", f"{pct_1d:+.2f}%", delta_color="normal")
            cols[2].metric("5日", f"{pct_5d:+.2f}%", delta_color="normal")
            cols[3].metric("20日", f"{pct_20d:+.2f}%", delta_color="normal")
            cols[4].metric("RSI(14)", f"{df['RSI'].iloc[-1]:.1f}" if "RSI" in df.columns else "--")

            # K线主图
            rows_count = 2 if ("RSI" in indicators or "MACD" in indicators) else 1
            row_heights = [0.65, 0.35] if rows_count == 2 else [1.0]
            specs = [[{"secondary_y": False}]] * rows_count
            fig = make_subplots(rows=rows_count, cols=1, shared_xaxes=True,
                                row_heights=row_heights, specs=specs,
                                vertical_spacing=0.03)

            # K线
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                name="K线",
                increasing_line_color="#ef4444",
                decreasing_line_color="#22c55e",
            ), row=1, col=1)

            # 均线
            colors = {"MA5": "#3b82f6", "MA20": "#f97316", "MA60": "#a855f7"}
            for ma in ["MA5", "MA20", "MA60"]:
                if ma in df.columns:
                    fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma,
                                             line=dict(color=colors[ma], width=1.2)),
                                  row=1, col=1)

            # 布林带
            if "布林带" in indicators and "BB_upper" in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df["BB_upper"], name="BB上",
                                         line=dict(color="#64748b", width=1, dash="dash")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df["BB_lower"], name="BB下",
                                         line=dict(color="#64748b", width=1, dash="dash"),
                                         fill="tonexty", fillcolor="rgba(100,116,139,0.05)"), row=1, col=1)

            # 副图：RSI
            if "RSI" in indicators and "RSI" in df.columns and rows_count >= 2:
                fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                                         line=dict(color="#8b5cf6", width=1.5)), row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=2, col=1)

            # 副图：MACD
            if "MACD" in indicators and "MACD_hist" in df.columns and rows_count >= 2:
                colors_macd = ["#ef4444" if v >= 0 else "#22c55e" for v in df["MACD_hist"]]
                fig.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], name="MACD柱",
                                     marker_color=colors_macd), row=2, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df["DIF"], name="DIF",
                                         line=dict(color="#3b82f6", width=1)), row=2, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df["DEA"], name="DEA",
                                         line=dict(color="#f97316", width=1)), row=2, col=1)

            fig.update_layout(
                height=600, template="plotly_dark",
                xaxis_rangeslider_visible=False,
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
            )
            fig.update_xaxes(gridcolor="#1e293b")
            fig.update_yaxes(gridcolor="#1e293b")
            st.plotly_chart(fig, use_container_width=True)

            # 数据表
            with st.expander("📋 原始数据"):
                st.dataframe(df.tail(30).round(4), use_container_width=True)


# ═══════════════════════════════════════════════════════
# 页面：因子分析
# ═══════════════════════════════════════════════════════
elif page == "🔬 因子分析":
    st.title("🔬 Alpha158 因子分析")

    if data_source != "Qlib 本地（~2020）":
        st.warning("因子分析需要切换到 **Qlib 本地（~2020）** 数据源")
        st.stop()

    qlib_ok, qlib_err = init_qlib(QLIB_DIR_OLD)
    if not qlib_ok:
        st.error(f"Qlib 未初始化: {qlib_err}")
        st.stop()

    # 获取数据范围
    DATA_START, DATA_END = get_calendar_range(QLIB_DIR_OLD)
    if DATA_START is None:
        DATA_START = pd.Timestamp("2005-01-01").date()
        DATA_END = pd.Timestamp("2020-09-25").date()

    st.markdown("基于 Qlib Alpha158，对 CSI300 因子做截面分析")

    col1, col2 = st.columns(2)
    with col1:
        # 默认使用最近1年数据（当前日期-1年，确保有足够数据计算IC）
        default_end = DATA_END - timedelta(days=10)
        default_start = default_end - timedelta(days=365)
        factor_start = st.date_input("开始日期", value=default_start, min_value=DATA_START, max_value=DATA_END)
        factor_end   = st.date_input("结束日期", value=default_end, min_value=DATA_START, max_value=DATA_END)
    with col2:
        forward_days = st.selectbox("预测周期（IC计算）", [1, 3, 5, 10, 20], index=2)

    if st.button("计算因子分析", type="primary"):
        with st.spinner("计算 Alpha158 因子，约30-60秒..."):
            try:
                from qlib.utils import init_instance_by_config
                from qlib.data import D

                handler = init_instance_by_config({
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": str(factor_start),
                        "end_time": str(factor_end),
                        "fit_start_time": str(factor_start),
                        "fit_end_time": str(factor_end),
                        "instruments": "csi300",
                    },
                })

                df_feat = handler.fetch(col_set="feature")
                df_label = handler.fetch(col_set="label")

                st.success(f"因子矩阵: {df_feat.shape[0]:,} 行 × {df_feat.shape[1]} 个因子")

                # IC 计算
                st.subheader("📊 因子 IC 分析")
                label_col = df_label.columns[0]
                ics = {}
                for col in df_feat.columns[:30]:  # 前30个因子
                    try:
                        ic = df_feat[col].corr(df_label[label_col], method="spearman")
                        if not np.isnan(ic):
                            ics[col] = ic
                    except:
                        pass

                ic_df = pd.DataFrame.from_dict(ics, orient="index", columns=["IC"])
                ic_df = ic_df.sort_values("IC", ascending=False)

                fig_ic = px.bar(ic_df, x=ic_df.index, y="IC",
                                color="IC", color_continuous_scale="RdYlGn",
                                color_continuous_midpoint=0,
                                title="因子 Rank IC（正=看涨，负=看跌）")
                fig_ic.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig_ic, use_container_width=True)

                # 因子分布
                st.subheader("📈 因子截面分布（最近一天）")
                latest_factors = df_feat.groupby(level="datetime").last()
                if not latest_factors.empty:
                    top_factor = ic_df.index[0] if not ic_df.empty else df_feat.columns[0]
                    fig_dist = px.histogram(
                        latest_factors[top_factor].dropna(),
                        title=f"{top_factor} 截面分布",
                        template="plotly_dark", nbins=50,
                    )
                    st.plotly_chart(fig_dist, use_container_width=True)

            except Exception as e:
                st.error(f"因子计算失败: {e}")
                import traceback
                st.code(traceback.format_exc())


# ═══════════════════════════════════════════════════════
# 页面：模型回测
# ═══════════════════════════════════════════════════════
elif page == "⚡ 模型回测":
    st.title("⚡ LightGBM + Alpha158 回测")

    # 不强制切换数据源，直接使用官方 Qlib 数据
    qlib_ok, qlib_err = init_qlib(QLIB_DIR_OLD)
    if not qlib_ok:
        st.error(f"Qlib 数据未找到: {qlib_err}")
        st.info(f"请确认数据目录存在: {QLIB_DIR_OLD}")
        st.stop()

    # 直接读文件获取真实日期范围（绕过 Qlib 内部缓存）
    DATA_START, DATA_END = get_calendar_range(QLIB_DIR_OLD)
    if DATA_START is None:
        DATA_START = pd.Timestamp("2005-01-01").date()
        DATA_END   = pd.Timestamp("2020-09-25").date()

    st.info(f"📅 数据范围：**{DATA_START}** ～ **{DATA_END}**")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**训练集**")
        train_start = st.date_input("开始", pd.Timestamp("2008-01-01").date(),
                                    min_value=DATA_START, max_value=DATA_END, key="tr_s")
        train_end   = st.date_input("结束", pd.Timestamp("2016-12-31").date(),
                                    min_value=DATA_START, max_value=DATA_END, key="tr_e")
    with col2:
        st.markdown("**测试集**（验证集自动取两者之间）")
        test_start  = st.date_input("开始", pd.Timestamp("2019-01-01").date(),
                                    min_value=DATA_START, max_value=DATA_END, key="te_s")
        test_end    = st.date_input("结束", DATA_END,
                                    min_value=DATA_START, max_value=DATA_END, key="te_e")

    # 校验日期逻辑
    date_ok = True
    if train_end <= train_start:
        st.error("训练结束日期必须晚于开始日期")
        date_ok = False
    if test_start <= train_end:
        st.error("测试开始日期必须晚于训练结束日期（中间留出验证集）")
        date_ok = False
    if test_end <= test_start:
        st.error("测试结束日期必须晚于开始日期")
        date_ok = False
    if test_end > DATA_END:
        st.warning(f"测试结束日期超出数据范围，自动截至 {DATA_END}")
        test_end = DATA_END

    # ⚠️ 避免回测边界bug：结束日期提前5天（防止访问 calendar[index+1] 越界）
    from datetime import timedelta
    backtest_end_safe = test_end - timedelta(days=5)
    if backtest_end_safe <= test_start:
        backtest_end_safe = test_start + timedelta(days=30)  # 保证至少有30天回测期
    st.info(f"📅 回测范围：**{test_start}** ～ **{backtest_end_safe}** （提前5天避免框架边界bug）")

    col1, col2 = st.columns(2)
    topk = col1.slider("持仓股数", 5, 15, 7, step=1, help="个人投资者建议5-8只")
    n_drop = col2.slider("每次换手数", 1, 3, 1, step=1, help="每次调仓换掉的股票数")

    # ── 新增：风险控制参数 ──
    st.markdown("---")
    st.subheader("🛡️ 风险控制设置")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        max_position_pct = st.slider("单票最大仓位", 1, 5, 2, step=1,
                                     help="单只股票最大仓位百分比（基于论文尾部风险控制建议）") / 100
    with col2:
        stop_loss_pct = st.slider("止损位", -5, -15, -8, step=1,
                                  help="单只股票止损百分比") / 100
    with col3:
        use_tail_risk_control = st.checkbox("启用尾部风险控制", value=True,
                                            help="根据市场波动率动态调整仓位")
    with col4:
        target_volatility = st.slider("目标波动率", 10, 25, 16, step=1,
                                      help="组合目标年化波动率（%）") / 100

    # ── 新增：交易成本设置 ──
    st.markdown("---")
    st.subheader("💰 交易成本设置")

    col1, col2, col3 = st.columns(3)
    with col1:
        buy_cost = st.slider("买入成本", 0.01, 0.2, 0.05, step=0.01,
                            help="买入交易成本（%）") / 100
    with col2:
        sell_cost = st.slider("卖出成本", 0.05, 0.3, 0.15, step=0.01,
                             help="卖出交易成本（%）") / 100
    with col3:
        estimate_realistic = st.checkbox("估算实盘收益", value=True,
                                        help="基于论文，按回测收益的50-70%估算实盘收益")

    include_cost = st.checkbox("在回测中包含交易成本", value=True)

    if st.button("🚀 开始训练 & 回测", type="primary", disabled=not date_ok):
        with st.spinner("训练 LightGBM + 回测中，约2-5分钟..."):
            try:
                from qlib.utils import init_instance_by_config
                from qlib.contrib.evaluate import backtest_daily, risk_analysis
                from qlib.contrib.strategy import TopkDropoutStrategy
                import qlib
                from qlib.constant import REG_CN

                # ── 设置 Qlib 单线程模式，避免多进程冲突 ──
                qlib.config.N_PROC = 1
                os.environ['NUMBA_NUM_THREADS'] = '1'
                os.environ['QLIB_NO_MULTI_PROCESS'] = '1'

                # valid 段取 train_end ~ test_start
                valid_start = str(train_end)
                valid_end   = str(test_start)

                dataset = init_instance_by_config({
                    "class": "DatasetH",
                    "module_path": "qlib.data.dataset",
                    "kwargs": {
                        "handler": {
                            "class": "Alpha158",
                            "module_path": "qlib.contrib.data.handler",
                            "kwargs": {
                                "start_time": str(train_start),
                                "end_time":   str(test_end),
                                "fit_start_time": str(train_start),
                                "fit_end_time":   str(train_end),
                                "instruments": "csi300",
                            },
                        },
                        "segments": {
                            "train": (str(train_start), str(train_end)),
                            "valid": (valid_start,      valid_end),
                            "test":  (str(test_start),  str(test_end)),
                        },
                    },
                })

                model = init_instance_by_config({
                    "class": "LGBModel",
                    "module_path": "qlib.contrib.model.gbdt",
                    "kwargs": {
                        "loss": "mse", "colsample_bytree": 0.8879,
                        "learning_rate": 0.2, "subsample": 0.8789,
                        "lambda_l1": 205.6999, "lambda_l2": 580.9768,
                        "max_depth": 8, "num_leaves": 210, "num_threads": 1,  # 单线程避免冲突
                    }
                })
                model.fit(dataset)
                pred = model.predict(dataset)

                # 回测
                exchange_kwargs = {
                    "codes": "csi300", "freq": "day",
                    "limit_threshold": 0.095, "deal_price": "close",
                }
                if include_cost:
                    exchange_kwargs.update({
                        "open_cost": buy_cost, "close_cost": sell_cost, "min_cost": 5
                    })

                strategy = TopkDropoutStrategy(topk=topk, n_drop=n_drop, signal=pred)
                report, _ = backtest_daily(
                    start_time=str(test_start), end_time=str(backtest_end_safe),
                    strategy=strategy,
                    executor={"class": "SimulatorExecutor",
                              "module_path": "qlib.backtest.executor",
                              "kwargs": {"time_per_step": "day",
                                         "generate_portfolio_metrics": True}},
                    account=1_000_000, benchmark="SH000300",
                    exchange_kwargs=exchange_kwargs,
                )

                # ── 指标展示 ──
                r = report["return"]
                bench = report["bench"]
                ex = r - bench

                ann_r = r.mean() * 252
                ann_std = r.std() * np.sqrt(252)
                sharpe = ann_r / ann_std if ann_std > 0 else 0
                cum = (1 + r).cumprod()
                dd = (cum / cum.cummax() - 1).min()
                wr = (r > 0).mean()
                calmar = ann_r / abs(dd) if dd != 0 else 0
                ann_ex = ex.mean() * 252
                ex_std = ex.std() * np.sqrt(252)
                ir = ann_ex / ex_std if ex_std > 0 else 0

                st.success("回测完成！")
                cols = st.columns(6)
                cols[0].metric("Sharpe", f"{sharpe:.3f}",
                               delta="好" if sharpe > 1 else "差", delta_color="normal")
                cols[1].metric("年化收益", f"{ann_r:.1%}")
                cols[2].metric("最大回撤", f"{dd:.1%}")
                cols[3].metric("胜率", f"{wr:.1%}")
                cols[4].metric("Calmar", f"{calmar:.2f}")
                cols[5].metric("信息比率", f"{ir:.3f}")

                # ── 新增：实盘收益估算 ──
                if estimate_realistic:
                    realistic_ann_r = estimate_realistic_return(
                        ann_r,
                        cost_adjustment=(buy_cost + sell_cost) * 0.5,
                        slippage=0.002
                    )
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("📊 实盘估算年化", f"{realistic_ann_r:.1%}",
                               delta=f"约{realistic_ann_r/ann_r:.0%}回测" if ann_r > 0 else "")
                    col2.info(f"💡 回测收益×60% - 交易成本 - 滑点")
                    col3.warning("⚠️ 基于论文：24%回测→实盘约5-8%")

                # 净值曲线
                cum_bench = (1 + bench).cumprod()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=cum.index, y=cum, name="策略",
                                         line=dict(color="#8b5cf6", width=2)))
                fig.add_trace(go.Scatter(x=cum_bench.index, y=cum_bench, name="沪深300",
                                         line=dict(color="#64748b", width=1.5, dash="dash")))
                fig.update_layout(title="策略净值 vs 基准", template="plotly_dark",
                                  height=400, yaxis_title="净值",
                                  plot_bgcolor="#0f172a", paper_bgcolor="#0f172a")
                st.plotly_chart(fig, use_container_width=True)

                # 回撤图
                drawdown = (cum / cum.cummax() - 1)
                fig_dd = go.Figure(go.Scatter(x=drawdown.index, y=drawdown,
                                               fill="tozeroy", line=dict(color="#ef4444", width=1),
                                               name="回撤"))
                fig_dd.update_layout(title="资金曲线回撤", template="plotly_dark",
                                     height=250, yaxis_tickformat=".1%",
                                     plot_bgcolor="#0f172a", paper_bgcolor="#0f172a")
                st.plotly_chart(fig_dd, use_container_width=True)

                # ── 本周操作建议 ──
                st.markdown("---")
                st.subheader("📋 本周操作建议")

                # 获取最新预测结果
                try:
                    # pred 是一个 Series，索引是 (datetime, instrument)，值是 score
                    # 需要 reset_index() 将索引转为列
                    pred_df = pred.reset_index()
                    pred_df.columns = ['日期', '代码', '预测得分']

                    # 获取最新日期的预测
                    latest_date = pred_df['日期'].max()
                    latest_pred = pred_df[pred_df['日期'] == latest_date].copy()
                    latest_pred = latest_pred.sort_values('预测得分', ascending=False)

                    # 获取股票名称映射
                    stock_names = {}
                    try:
                        from qlib.data import D
                        instruments = D.instruments(market="csi300")
                        for code in instruments:
                            # 简单的代码到名称映射
                            stock_names[code.upper()] = code
                    except:
                        pass

                    # 格式化代码
                    def format_code(code):
                        if isinstance(code, str):
                            return code.upper()
                        return str(code).upper()

                    latest_pred['代码'] = latest_pred['代码'].apply(format_code)

                    # 建议买入 (Top K)
                    k = st.session_state.get('topk', topk)
                    buy_stocks = latest_pred.head(k)

                    # 建议卖出/避开 (Bottom K)
                    sell_stocks = latest_pred.tail(k)

                    # 资金分配（考虑风险控制）
                    total_capital = st.session_state.get('total_capital', 100) * 10000  # 万转元
                    factor_alloc = st.session_state.get('factor_alloc', 60) / 100
                    factor_capital = total_capital * factor_alloc

                    # 根据风险等级动态调整单票仓位
                    base_per_stock = factor_capital / k if k > 0 else 0

                    # 显示建议
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"### 📥 建议买入 (Top {k})")

                        # 计算风险调整后的仓位
                        buy_data = []
                        for _, row in buy_stocks.iterrows():
                            code = row['代码']
                            score = row['预测得分']
                            # 简单的收益预测转换
                            pred_return = (score * 100) if abs(score) < 1 else (score / 10)

                            # 获取透明度
                            trans_level = get_transparency_level(code)
                            trans_name = get_transparency_name(trans_level)
                            stock_name = get_stock_name(code)

                            # 根据透明度调整仓位（低透明度高风险，降低仓位）
                            position_multiplier = 1.0
                            if trans_level == "LOW":
                                position_multiplier = 0.7  # 低透明度降低30%仓位
                            elif trans_level == "HIGH":
                                position_multiplier = 1.2  # 高透明度增加20%仓位

                            adjusted_position = base_per_stock * position_multiplier * max_position_pct / 0.02

                            buy_data.append({
                                "代码": code,
                                "名称": stock_name,
                                "透明度": trans_name,
                                "预测得分": f"{score:.4f}",
                                "预测收益": f"{pred_return:+.2f}%",
                                "建议仓位": f"{adjusted_position/10000:.1f}万" if adjusted_position > 0 else f"{base_per_stock/10000:.1f}万",
                            })

                        st.caption(f"基础每只配置约 {base_per_stock/10000:.1f}万元（已根据透明度动态调整）")
                        st.dataframe(
                            pd.DataFrame(buy_data),
                            use_container_width=True,
                            hide_index=True,
                        )

                    with col2:
                        st.markdown(f"### 📤 建议避开/卖出 (Bottom {k})")
                        st.caption("预测得分较低，建议回避或减仓")

                        sell_data = []
                        for _, row in sell_stocks.iterrows():
                            code = row['代码']
                            score = row['预测得分']
                            pred_return = (score * 100) if abs(score) < 1 else (score / 10)

                            # 获取透明度
                            trans_level = get_transparency_level(code)
                            trans_name = get_transparency_name(trans_level)
                            stock_name = get_stock_name(code)

                            sell_data.append({
                                "代码": code,
                                "名称": stock_name,
                                "透明度": trans_name,
                                "预测得分": f"{score:.4f}",
                                "预测收益": f"{pred_return:+.2f}%",
                            })

                        st.dataframe(
                            pd.DataFrame(sell_data),
                            use_container_width=True,
                            hide_index=True,
                        )

                    # 操作建议总结
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("预测日期", f"{latest_date.strftime('%Y-%m-%d')}")

                    with col2:
                        st.metric("资金分配", f"{factor_capital/10000:.1f}万元")

                    with col3:
                        avg_return = buy_stocks['预测得分'].mean() * 100
                        st.metric("平均预期收益", f"{avg_return:+.2f}%")

                    # 操作提示
                    st.info("""
                    💡 **操作建议**:
                    - 建议在周一开盘后执行调仓
                    - 可以分批买入，不必一次性买入全部
                    - 设置止损位: -10%
                    - 设置止盈位: +20% 或 信号转弱时
                    - 每周复盘，根据最新信号调整持仓
                    """)

                except Exception as rec_err:
                    st.warning(f"操作建议生成失败: {rec_err}")

            except Exception as e:
                st.error(f"回测失败: {e}")
                import traceback
                st.code(traceback.format_exc())


# ═══════════════════════════════════════════════════════
# 页面：ETF 轮动信号
# ═══════════════════════════════════════════════════════
elif page == "🔄 ETF轮动信号":
    st.title("🔄 行业ETF轮动信号")
    st.markdown("基于 akshare 实时数据 + 技术因子，对8个行业ETF打分排名")

    ETFS = {
        "沪深300ETF": "SH510300", "证券ETF": "SH512880", "医药ETF": "SH512010",
        "新能源车ETF": "SH515030", "军工ETF": "SH512660", "有色金属ETF": "SH512400",
        "芯片ETF": "SZ159995",   "通信ETF": "SH515880",
    }

    col1, col2 = st.columns(2)
    lookback = col1.slider("回测天数", 60, 365, 120)
    forward  = col2.selectbox("预测周期", [3, 5, 10], index=1)

    if st.button("🔍 计算ETF轮动信号", type="primary"):
        end_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=lookback+30)).strftime("%Y-%m-%d")

        results = []
        bar = st.progress(0)

        for i, (name, code) in enumerate(ETFS.items()):
            with st.spinner(f"计算 {name}..."):
                df = get_stock_data_ak(code, start_date, end_date)

            if df.empty or len(df) < 30:
                bar.progress((i+1)/len(ETFS))
                continue

            close = df["close"]

            # 技术因子
            ma5   = calc_ma(close, 5).iloc[-1]
            ma20  = calc_ma(close, 20).iloc[-1]
            ma60  = calc_ma(close, 60).iloc[-1] if len(df) >= 60 else close.mean()
            rsi   = calc_rsi(close).iloc[-1]
            dif, dea, hist = calc_macd(close)
            mom5  = (close.iloc[-1] / close.iloc[-5] - 1) * 100 if len(df) >= 5 else 0
            mom20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(df) >= 20 else 0

            # 趋势得分
            trend_score = 0
            if close.iloc[-1] > ma5:   trend_score += 0.2
            if close.iloc[-1] > ma20:  trend_score += 0.3
            if close.iloc[-1] > ma60:  trend_score += 0.2
            if ma5 > ma20:             trend_score += 0.15
            if hist.iloc[-1] > 0:      trend_score += 0.15

            # 超买超卖修正（避免追高）
            rsi_score = 0
            if rsi < 30:   rsi_score = 0.3   # 超卖，看多
            elif rsi < 50: rsi_score = 0.15
            elif rsi < 70: rsi_score = 0
            else:          rsi_score = -0.2  # 超买，谨慎

            # 综合分（0-1）
            final = trend_score * 0.7 + rsi_score * 0.3

            # 简单预测：用最近 forward 天的历史模式估算
            if len(df) >= forward + 20:
                fwd_rets = close.pct_change(forward).shift(-forward).dropna()
                cur_rsi = calc_rsi(close).iloc[-1]
                # 类似 RSI 水平时的历史平均收益
                mask = (calc_rsi(close).dropna() - cur_rsi).abs() < 10
                hist_avg = fwd_rets[mask.reindex(fwd_rets.index, fill_value=False)].mean() * 100
                pred_ret = hist_avg if not np.isnan(hist_avg) else mom5 * 0.3
            else:
                pred_ret = mom5 * 0.3

            results.append({
                "ETF名称": name, "代码": code[2:],
                "最新价": round(close.iloc[-1], 3),
                "综合评分": round(final, 3),
                "预测收益%": round(pred_ret, 2),
                "5日动量%": round(mom5, 2),
                "20日动量%": round(mom20, 2),
                "RSI": round(rsi, 1),
                "MA趋势": "↑多头" if close.iloc[-1] > ma20 else "↓空头",
                "信号": "买入" if final > 0.55 else ("观望" if final > 0.35 else "回避"),
            })
            bar.progress((i+1)/len(ETFS))

        bar.empty()

        if not results:
            st.error("无法获取数据")
        else:
            df_res = pd.DataFrame(results).sort_values("综合评分", ascending=False)

            # 颜色标记
            def color_signal(val):
                if val == "买入":  return "color: #22c55e; font-weight: bold"
                if val == "回避":  return "color: #ef4444; font-weight: bold"
                return "color: #eab308"

            st.dataframe(
                df_res.style.applymap(color_signal, subset=["信号"]),
                use_container_width=True, hide_index=True,
            )

            # 雷达图
            st.subheader("📊 ETF多维度雷达图")
            fig_radar = go.Figure()
            categories = ["综合评分", "5日动量%", "20日动量%", "RSI比率"]

            for _, row in df_res.head(5).iterrows():
                values = [
                    row["综合评分"],
                    max(min(row["5日动量%"] / 10 + 0.5, 1), 0),
                    max(min(row["20日动量%"] / 20 + 0.5, 1), 0),
                    max(min((100 - row["RSI"]) / 100, 1), 0),
                ]
                fig_radar.add_trace(go.Scatterpolar(
                    r=values + [values[0]],
                    theta=categories + [categories[0]],
                    name=row["ETF名称"],
                    fill="toself", opacity=0.4,
                ))

            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                template="plotly_dark", height=450,
                title="前5 ETF多维度对比",
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # 动量柱图
            fig_mom = px.bar(df_res, x="ETF名称", y="20日动量%",
                             color="信号",
                             color_discrete_map={"买入": "#22c55e", "观望": "#eab308", "回避": "#ef4444"},
                             title="20日动量对比",
                             template="plotly_dark")
            st.plotly_chart(fig_mom, use_container_width=True)


# ═══════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════
# 页面：ETF 全量筛选
# ═══════════════════════════════════════════════════════
elif page == "🎯 ETF全量筛选":
    st.title("🎯 ETF 全量筛选")
    st.markdown("从 **300+ 只** A股主要ETF中，按动量、夏普、相对强度自动评分排名，找到当前最强ETF。")

    from etf_screener import CORE_ETFS, FULL_ETFS, fetch_etf, calc_metrics, score_etf

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pool_choice = st.radio("ETF池", ["核心50只（快速）", "全量300+只（完整）"])
    with col2:
        lookback = st.selectbox("回看周期", [63, 126, 252, 504], index=2,
                                format_func=lambda x: f"{x}天（{x//21}个月）")
    with col3:
        top_n = st.slider("显示前N名", 10, 50, 20)
    with col4:
        req_delay = st.slider("请求间隔(秒)", 0.1, 1.0, 0.25, step=0.05)

    st.markdown("---")

    if st.button("▶️ 开始筛选", type="primary"):
        import warnings
        warnings.filterwarnings("ignore")

        etf_pool = CORE_ETFS if "50" in pool_choice else FULL_ETFS
        end_dt   = pd.Timestamp.now().strftime("%Y-%m-%d")
        start_dt = (pd.Timestamp.now() - pd.Timedelta(days=lookback + 10)).strftime("%Y-%m-%d")

        st.info(f"正在筛选 {len(etf_pool)} 只ETF，数据区间 {start_dt} ~ {end_dt}")
        prog  = st.progress(0)
        stats = st.empty()

        # 基准
        bench = fetch_etf("510300.SS", start_dt, end_dt)

        results = []
        fail    = 0

        for idx, (code, name) in enumerate(etf_pool.items()):
            price = fetch_etf(code, start_dt, end_dt)
            if not price.empty:
                m = calc_metrics(price, bench)
                if m:
                    m["code"]  = code
                    m["name"]  = name
                    m["score"] = score_etf(m)
                    results.append(m)
                else:
                    fail += 1
            else:
                fail += 1

            prog.progress((idx + 1) / len(etf_pool))
            if (idx + 1) % 5 == 0:
                stats.text(f"已处理 {idx+1}/{len(etf_pool)}  有效:{len(results)}  失败:{fail}")
            time.sleep(req_delay)

        prog.progress(1.0)
        stats.empty()

        if not results:
            st.error("无有效数据，请检查网络连接")
        else:
            df_res = pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)
            df_res.index += 1

            st.success(f"筛选完成：{len(results)} 只有效 / {fail} 只无数据")
            st.markdown(f"### TOP {top_n} ETF 排名")

            # 格式化显示
            display_cols = {
                "code":        "代码",
                "name":        "名称",
                "score":       "综合评分",
                "ret_1m":      "近1月涨幅",
                "ret_3m":      "近3月涨幅",
                "ret_6m":      "近6月涨幅",
                "sharpe":      "夏普比率",
                "max_dd":      "最大回撤",
                "ann_vol":     "年化波动",
                "rel_strength":"相对沪深300",
                "above_ma20":  "站上MA20%",
            }

            df_show = df_res.head(top_n)[list(display_cols.keys())].copy()
            df_show.columns = list(display_cols.values())

            for pct_col in ["近1月涨幅", "近3月涨幅", "近6月涨幅", "最大回撤", "年化波动", "相对沪深300", "站上MA20%"]:
                if pct_col in df_show.columns:
                    df_show[pct_col] = df_show[pct_col].apply(
                        lambda x: f"{x:.1%}" if pd.notna(x) else "N/A"
                    )

            st.dataframe(df_show, use_container_width=True)

            # TOP 10 评分柱状图
            st.markdown("#### 综合评分 TOP 10")
            top10 = df_res.head(10)
            fig = px.bar(
                top10,
                x="name", y="score",
                color="score",
                color_continuous_scale="RdYlGn",
                labels={"name": "ETF", "score": "综合评分"},
                text="score",
            )
            fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            fig.update_layout(
                template="plotly_dark", height=400,
                xaxis_tickangle=-30, showlegend=False,
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            # 动量热力图
            st.markdown("#### 多周期动量热力图（TOP 20）")
            top20 = df_res.head(min(20, len(df_res)))
            heat_data = top20[["name", "ret_1m", "ret_3m", "ret_6m"]].set_index("name")
            heat_data.columns = ["1月", "3月", "6月"]
            fig2 = px.imshow(
                heat_data.T * 100,
                color_continuous_scale="RdYlGn",
                text_auto=".1f",
                labels={"color": "涨幅(%)"},
                zmin=-20, zmax=30,
            )
            fig2.update_layout(template="plotly_dark", height=250)
            st.plotly_chart(fig2, use_container_width=True)

            # 下载
            csv = df_res.to_csv(index=True, encoding="utf-8-sig")
            st.download_button(
                label="⬇️ 下载完整排名CSV",
                data=csv.encode("utf-8-sig"),
                file_name=f"etf_rank_{end_dt}.csv",
                mime="text/csv",
            )

    st.markdown("---")
    st.markdown("#### 评分算法说明")
    st.markdown("""
| 指标 | 权重 | 说明 |
|------|------|------|
| 近1月动量 | 高 | 短期趋势最重要 |
| 近3月动量 | 中 | 中期趋势 |
| 近6月动量 | 低 | 长期方向 |
| 夏普比率 | 中 | 风险调整后收益 |
| Calmar比率 | 低 | 回撤控制 |
| 站上MA20比例 | 中 | 趋势稳定性 |
| 相对沪深300超额 | 高 | 相对强度 |

> 策略逻辑：优选**近期动量强、风险低、跑赢大盘**的ETF，适合用于ETF轮动策略。
""")


# ═══════════════════════════════════════════════════════
# 页面：数据管理
# ═══════════════════════════════════════════════════════
elif page == "📥 数据管理":
    st.title("📥 数据管理")

    # 当前数据状态
    st.subheader("📊 当前数据状态")
    import pathlib

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Qlib 官方数据（Yahoo Finance，截止2020）**")
        old_dir = pathlib.Path(QLIB_DIR_OLD)
        if old_dir.exists():
            stocks = list(old_dir.glob("features/*/close.day.bin"))
            cal = old_dir / "calendars" / "day.txt"
            last_date = open(cal).readlines()[-1].strip() if cal.exists() else "未知"
            st.success(f"✅ {len(stocks)} 只股票  |  最新: {last_date}")
        else:
            st.error("❌ 未找到")

    with col2:
        st.markdown("**yfinance 数据（新，2015至今）**")
        new_dir = pathlib.Path(QLIB_DIR_NEW)
        if new_dir.exists():
            stocks_new = list(new_dir.glob("features/*/close.day.bin"))
            cal_new = new_dir / "calendars" / "day.txt"
            if cal_new.exists():
                lines = open(cal_new).readlines()
                last_new = lines[-1].strip() if lines else "未知"
                first_new = lines[0].strip() if lines else "未知"
            else:
                last_new = first_new = "未知"
            st.success(f"✅ {len(stocks_new)} 只  |  {first_new} ~ {last_new}")
        else:
            st.warning("⚠️ 尚未收集，点击下方按钮开始")

    st.markdown("---")

    # 数据收集
    st.subheader("📥 更新 yfinance 数据")
    st.caption("数据来源：Yahoo Finance，覆盖 ETF + 部分个股，2015 至今")

    col1, col2 = st.columns(2)
    mode = col1.radio("模式", ["增量更新（近40天，推荐）", "全量收集（2015至今）"])
    if "增量" in mode:
        start_str = (pd.Timestamp.now() - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
        col2.info(f"起始日期：{start_str}")
    else:
        start_input = col2.date_input("起始日期", value=pd.Timestamp("2015-01-01").date())
        start_str = str(start_input)

    if st.button("▶️ 开始更新", type="primary"):
        from data_collector import (
            run_update, BROAD_ETFS, SECTOR_ETFS, CSI300_SAMPLE,
            fetch_yfinance, save_to_qlib, update_calendar,
            update_instruments, QLIB_DATA_DIR, _get_trading_calendar
        )

        progress_bar = st.progress(0)
        status_text = st.empty()
        end_str = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        data_dir = QLIB_DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)

        all_targets = {**BROAD_ETFS, **SECTOR_ETFS, **CSI300_SAMPLE}
        total = len(all_targets)
        success = 0
        all_dates = set()

        # 先建立日历
        status_text.text("建立交易日历...")
        ref_df = fetch_yfinance("510300.SS", start_str, end_str)
        if not ref_df.empty:
            calendar = update_calendar(data_dir, set(ref_df.index.tolist()))
        else:
            calendar = _get_trading_calendar(data_dir)

        for i, (qlib_code, yf_code) in enumerate(all_targets.items()):
            status_text.text(f"[{i+1}/{total}] {qlib_code} ({yf_code})...")
            df = fetch_yfinance(yf_code, start_str, end_str)
            if not df.empty:
                all_dates.update(df.index.tolist())
                ok = save_to_qlib(qlib_code, df, data_dir, calendar)
                if ok:
                    success += 1
            progress_bar.progress((i + 1) / total)
            time.sleep(0.3)

        if all_dates:
            calendar = update_calendar(data_dir, all_dates)
        update_instruments(data_dir, "etf",
                           list(BROAD_ETFS.keys()) + list(SECTOR_ETFS.keys()),
                           "2010-01-01", end_str)
        all_codes = [f.parent.name.upper()
                     for f in data_dir.glob("features/*/close.day.bin")]
        update_instruments(data_dir, "all", all_codes, "2005-01-01", end_str)

        status_text.text(f"✅ 完成！{success}/{total} 只成功")
        progress_bar.progress(1.0)
        latest = max(all_dates).strftime("%Y-%m-%d") if all_dates else "未知"
        st.success(f"数据已更新至 {latest}，共 {success} 只")
        st.cache_data.clear()

    st.markdown("---")

    # ── 新增：全部 A 股增量更新 ──
    st.subheader("🔄 全部 A 股增量更新")
    st.caption("更新 Qlib 官方 cn_data 的全部 3800+ 只股票到今天")

    # 检查当前最新日期
    old_cal = pathlib.Path(QLIB_DIR_OLD) / "calendars" / "day.txt"
    current_end = "未知"
    if old_cal.exists():
        lines = open(old_cal).readlines()
        current_end = lines[-1].strip() if lines else "未知"

    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    days_behind = (pd.Timestamp.now() - pd.Timestamp(current_end)).days if current_end != "未知" else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("数据最新日期", current_end)
    col2.metric("今天", today)
    col3.metric("滞后天数", f"{days_behind} 天",
                delta="需要更新" if days_behind > 2 else "数据较新",
                delta_color="inverse" if days_behind > 2 else "normal")

    if days_behind > 2:
        st.info(f"💡 数据已滞后 {days_behind} 天，建议点击下方按钮更新")

    st.markdown("---")

    col1, col2 = st.columns([2, 1])
    max_stocks = col2.slider("测试上限只数", 100, 5000, 500, step=100,
                              help="全部约3800只，建议先用500只测试，确认OK后改大")

    if st.button("🚀 开始更新 A 股数据", type="primary"):
        import subprocess

        st.warning("⏳ 更新已启动，预计需要 10-30 分钟，请勿关闭页面...")

        # 显示实时输出
        output_container = st.container()
        status_text = st.empty()

        end_str = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        cmd = [
            "./venv/bin/python", "update_cn_data.py",
            "--start", "2020-09-26",
            "--end", end_str,
            "--max", str(max_stocks)
        ]

        status_text.code(f"$ {' '.join(cmd)}", language="bash")

        # 执行更新
        result = subprocess.run(
            cmd,
            cwd=pathlib.Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )

        # 显示输出
        with output_container:
            if result.stdout:
                st.subheader("📋 执行日志")
                st.code(result.stdout, language="text")
            if result.stderr:
                st.error("⚠️ 错误信息")
                st.code(result.stderr, language="text")

        if result.returncode == 0:
            st.success("✅ 更新完成！请刷新页面查看最新数据。")
            st.cache_data.clear()
            if st.button("🔄 刷新页面"):
                st.rerun()
        else:
            st.error(f"❌ 更新失败，退出码: {result.returncode}")

    st.markdown("---")
    st.subheader("⚙️ 命令行操作")
    st.code("""
# 增量更新（只更新最近40天，约2分钟）
cd /home/jason/projects/qlib-workspace
./venv/bin/python data_collector.py --action update

# 检查数据状态
./venv/bin/python data_collector.py --action check

# 全量收集（2015至今，约5-10分钟）
./venv/bin/python data_collector.py --action init --start 2015-01-01
""", language="bash")


# ═══════════════════════════════════════════════════════
# 页面：均值回归策略
# ═══════════════════════════════════════════════════════
elif page == "📉 均值回归":
    st.title("📉 均值回归策略")
    st.caption("基于 RSI + 布林带的反向交易策略，捕捉超买超卖机会")

    # 导入统一股票池
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from stock_universe import CSI300_SECTORS, qlib_code_to_yf
    from strategy_signals import create_mean_reversion_signal, SignalConsolidator

    # 参数设置
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rsi_oversold = st.slider("RSI 超卖阈值", 20, 35, 30)
        rsi_overbought = st.slider("RSI 超买阈值", 65, 85, 70)
    with col2:
        bb_period = st.selectbox("布林带周期", [10, 20, 30], index=1)
        bb_std = st.selectbox("布林带标准差", [1.5, 2.0, 2.5], index=1)
    with col3:
        lookback = st.selectbox("回看天数", [60, 120, 252], index=0)
        top_n = st.slider("显示TOP N", 5, 30, 15)
    with col4:
        min_signal_strength = st.slider("最小信号强度", 0.3, 1.0, 0.5, step=0.1)

    st.markdown("---")

    # 分析按钮
    if st.button("🔍 扫描超买超卖股票", type="primary"):
        with st.spinner("正在扫描 CSI300 股票池..."):
            end_date = pd.Timestamp.now()
            start_date = end_date - pd.Timedelta(days=lookback + 50)

            results = []
            consolidator = SignalConsolidator()

            progress = st.progress(0)
            total_sectors = len(CSI300_SECTORS)
            current = 0

            for sector, codes in CSI300_SECTORS.items():
                current += 1
                sector_stocks = codes[:20]  # 每个板块取前20只

                for code in sector_stocks:
                    yf_code = qlib_code_to_yf(code)
                    try:
                        df = get_stock_data_ak(code, start_date.strftime("%Y-%m-%d"),
                                              end_date.strftime("%Y-%m-%d"))

                        if df.empty or len(df) < bb_period + 10:
                            continue

                        close = df["close"]

                        # 计算RSI
                        rsi = calc_rsi(close, 14).iloc[-1]

                        # 计算布林带
                        bb_mid = calc_ma(close, bb_period)
                        bb_std_val = close.rolling(bb_period).std()
                        bb_upper = bb_mid + bb_std * bb_std_val
                        bb_lower = bb_mid - bb_std * bb_std_val

                        # 布林带位置 (0-1)
                        current_bb_upper = bb_upper.iloc[-1]
                        current_bb_lower = bb_lower.iloc[-1]
                        bb_position = (close.iloc[-1] - current_bb_lower) / (current_bb_upper - current_bb_lower)
                        bb_position = max(0, min(1, bb_position))

                        # 判断信号
                        oversold = rsi < rsi_oversold or bb_position < 0.1
                        overbought = rsi > rsi_overbought or bb_position > 0.9

                        if oversold or overbought:
                            signal_type = "买入" if oversold else "卖出"
                            signal_strength = abs(rsi - 50) / 50 if oversold else abs(rsi - 50) / 50
                            signal_strength = max(signal_strength, abs(bb_position - 0.5) * 2)

                            results.append({
                                "代码": code,
                                "板块": sector,
                                "最新价": close.iloc[-1],
                                "RSI": rsi,
                                "布林带位置": f"{bb_position:.1%}",
                                "信号": signal_type,
                                "强度": signal_strength,
                            })

                            # 创建信号
                            sig = create_mean_reversion_signal(
                                code=code,
                                name=code,
                                rsi=rsi,
                                bb_position=bb_position,
                                price=close.iloc[-1]
                            )
                            consolidator.add_signal(sig)

                    except Exception as e:
                        continue

                progress.progress(current / total_sectors)

            progress.empty()

            if results:
                # 按信号强度排序
                results.sort(key=lambda x: x["强度"], reverse=True)

                # 添加股票名称和透明度
                for r in results:
                    r["名称"] = get_stock_name(r["代码"])
                    r["透明度"] = get_transparency_name(get_transparency_level(r["代码"]))

                # 显示买入信号
                st.subheader("📥 超卖买入机会")
                buy_signals = [r for r in results if r["信号"] == "买入"]
                if buy_signals:
                    buy_df = pd.DataFrame(buy_signals[:top_n])
                    buy_df["强度"] = buy_df["强度"].apply(lambda x: f"{x:.2f}")
                    buy_df["RSI"] = buy_df["RSI"].apply(lambda x: f"{x:.1f}")
                    st.dataframe(buy_df[["代码", "名称", "透明度", "板块", "最新价", "RSI", "布林带位置", "强度"]],
                                use_container_width=True, hide_index=True)
                else:
                    st.info("暂无超卖信号")

                # 显示卖出信号
                st.subheader("📤 超买卖出机会")
                sell_signals = [r for r in results if r["信号"] == "卖出"]
                if sell_signals:
                    sell_df = pd.DataFrame(sell_signals[:top_n])
                    sell_df["强度"] = sell_df["强度"].apply(lambda x: f"{x:.2f}")
                    sell_df["RSI"] = sell_df["RSI"].apply(lambda x: f"{x:.1f}")
                    st.dataframe(sell_df[["代码", "名称", "透明度", "板块", "最新价", "RSI", "布林带位置", "强度"]],
                                use_container_width=True, hide_index=True)
                else:
                    st.info("暂无超买信号")

                # 统计摘要
                st.markdown("---")
                col1, col2, col3 = st.columns(3)
                col1.metric("扫描股票", f"{len(set(r['代码'] for r in results))} 只")
                col2.metric("买入信号", f"{len(buy_signals)} 个")
                col3.metric("卖出信号", f"{len(sell_signals)} 个")

            else:
                st.warning("未发现符合条件的信号，请调整参数后重试")

    # 使用说明
    with st.expander("💡 使用说明"):
        st.markdown("""
        ### 策略原理

        **均值回归**认为价格涨多了会跌，跌多了会涨。

        ### 信号规则

        | 条件 | 信号 |
        |------|------|
        | RSI < 30 或 价格 < 布林带下轨 | 超卖，买入机会 |
        | RSI > 70 或 价格 > 布林带上轨 | 超买，卖出机会 |

        ### 操作建议

        - 信号强度 > 0.7：强烈建议关注
        - 信号强度 0.5-0.7：中等机会
        - 信号强度 < 0.5：弱信号，观望
        - 建议止损位: -8%
        - 建议止盈位: 信号消失时平仓
        """)


# ═══════════════════════════════════════════════════════
# 页面：配对交易
# ═══════════════════════════════════════════════════════
elif page == "🔗 配对交易":
    st.title("🔗 配对交易策略")
    st.caption("基于统计套利的配对交易，寻找协整关系的股票对")

    # 导入模块
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from pair_trading import (
        get_default_pairs, calc_correlation, check_cointegration,
        calc_spread, calc_zscore, generate_pair_signal, PairSignal
    )

    # 参数设置
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_correlation = st.slider("最小相关性", 0.5, 0.95, 0.75, step=0.05)
    with col2:
        entry_threshold = st.slider("入场阈值 (Z-score)", 1.5, 3.0, 2.0, step=0.5)
    with col3:
        exit_threshold = st.slider("出场阈值 (Z-score)", 0.3, 1.0, 0.5, step=0.1)
    with col4:
        lookback_days = st.selectbox("回看周期", [20, 40, 60], index=2)

    st.markdown("---")

    # 选择板块
    default_pairs = get_default_pairs()
    sectors = list(default_pairs.keys())
    selected_sector = st.selectbox("选择行业板块", sectors)

    if selected_sector:
        sector_pairs = default_pairs[selected_sector]

        st.subheader(f"📊 {selected_sector} 板块 - 配对分析")

        results = []

        for code1, code2 in sector_pairs:
            try:
                # 获取数据
                end_date = pd.Timestamp.now()
                start_date = end_date - pd.Timedelta(days=lookback_days + 50)

                df1 = get_stock_data_ak(code1, start_date.strftime("%Y-%m-%d"),
                                        end_date.strftime("%Y-%m-%d"))
                df2 = get_stock_data_ak(code2, start_date.strftime("%Y-%m-%d"),
                                        end_date.strftime("%Y-%m-%d"))

                if df1.empty or df2.empty:
                    continue

                # 添加代码列
                df1['code'] = code1
                df2['code'] = code2

                # 生成信号
                signal = generate_pair_signal(
                    df1, df2,
                    entry_threshold=entry_threshold,
                    exit_threshold=exit_threshold,
                    lookback=lookback_days
                )

                # 过滤相关性
                if signal.correlation >= min_correlation:
                    results.append(signal)

            except Exception as e:
                continue

        if results:
            # 显示结果表格
            display_data = []
            for r in results:
                signal_text = {
                    'long_spread': '做多价差 (做多1/做空2)',
                    'short_spread': '做空价差 (做空1/做多2)',
                    'close': '平仓',
                    'hold': '观望'
                }.get(r.signal, r.signal)

                # 添加股票名称
                name1 = get_stock_name(r.stock1)
                name2 = get_stock_name(r.stock2)
                pair_with_names = f"{r.stock1}({name1}) / {r.stock2}({name2})"

                display_data.append({
                    "配对": pair_with_names,
                    "相关系数": f"{r.correlation:.3f}",
                    "Z-score": f"{r.zscore:.2f}",
                    "信号": signal_text,
                    "置信度": f"{r.confidence:.0%}",
                })

            df_display = pd.DataFrame(display_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # 价差图表
            st.subheader("📈 价差走势")

            # 选择要显示的配对
            if len(results) > 0:
                selected_pair = st.selectbox(
                    "选择配对查看详情",
                    options=[r.pair for r in results],
                    format_func=lambda x: next((r.pair for r in results if r.pair == x), x)
                )

                if selected_pair:
                    selected_signal = next((r for r in results if r.pair == selected_pair), None)
                    if selected_signal:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("相关系数", f"{selected_signal.correlation:.3f}")
                        col2.metric("Z-score", f"{selected_signal.zscore:.2f}")
                        col3.metric("信号", {
                            'long_spread': '📥 做多价差',
                            'short_spread': '📤 做空价差',
                            'close': '⚠️ 平仓',
                            'hold': '⏸️ 观望'
                        }.get(selected_signal.signal, selected_signal.signal))

                        # 绘制价差图（需要重新计算历史数据）
                        try:
                            code1, code2 = selected_signal.stock1, selected_signal.stock2
                            end_date = pd.Timestamp.now()
                            start_date = end_date - pd.Timedelta(days=lookback_days + 50)

                            df1_hist = get_stock_data_ak(code1, start_date.strftime("%Y-%m-%d"),
                                                        end_date.strftime("%Y-%m-%d"))
                            df2_hist = get_stock_data_ak(code2, start_date.strftime("%Y-%m-%d"),
                                                        end_date.strftime("%Y-%m-%d"))

                            if not df1_hist.empty and not df2_hist.empty:
                                spread = calc_spread(df1_hist, df2_hist)
                                zscore_hist = calc_zscore(spread, window=lookback_days)

                                fig = go.Figure()
                                fig.add_trace(go.Scatter(
                                    x=zscore_hist.index,
                                    y=zscore_hist.values,
                                    name='Z-score',
                                    line=dict(color='#8b5cf6', width=2)
                                ))
                                fig.add_hline(y=entry_threshold, line_dash="dash",
                                             line_color="red", opacity=0.5)
                                fig.add_hline(y=-entry_threshold, line_dash="dash",
                                             line_color="green", opacity=0.5)
                                fig.add_hline(y=0, line_dash="solid",
                                             line_color="gray", opacity=0.3)
                                fig.update_layout(
                                    title=f"{selected_pair} 价差 Z-score 走势",
                                    template="plotly_dark",
                                    height=400,
                                    xaxis_title="日期",
                                    yaxis_title="Z-score"
                                )
                                st.plotly_chart(fig, use_container_width=True)
                        except Exception as e:
                            st.warning(f"无法绘制图表: {e}")

            # 操作建议
            st.markdown("---")
            st.subheader("💡 操作建议")

            active_signals = [r for r in results if r.signal in ['long_spread', 'short_spread']]

            if active_signals:
                for sig in active_signals:
                    direction = "做多价差" if sig.signal == 'long_spread' else "做空价差"
                    action = f"买入 {sig.stock1}，卖出 {sig.stock2}" if sig.signal == 'long_spread' else f"卖出 {sig.stock1}，买入 {sig.stock2}"
                    st.info(f"""
                    **{sig.pair}** - {direction}
                    - 操作: {action}
                    - Z-score: {sig.zscore:.2f}
                    - 置信度: {sig.confidence:.0%}
                    - 相关性: {sig.correlation:.3f}
                    """)
            else:
                st.info("当前没有符合条件的交易信号，请等待价差偏离入场阈值。")

        else:
            st.warning(f"{selected_sector} 板块未找到符合条件的配对（相关性 >= {min_correlation}）")

    # 使用说明
    with st.expander("💡 配对交易说明"):
        st.markdown("""
        ### 策略原理

        **配对交易**利用两只高相关性股票之间的价差回归特性进行交易。

        ### 交易规则

        | Z-score | 信号 |
        |---------|------|
        | > 2.0 | 价差过高，做空价差 |
        | < -2.0 | 价差过低，做多价差 |
        | < 0.5 | 价差回归，平仓 |

        ### 风险提示

        - 相关性可能突然下降
        - 价差可能持续扩大（不回归）
        - 需要同时管理两个头寸
        - 建议设置止损: Z-score > 3.0
        """)
