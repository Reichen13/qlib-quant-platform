# Qlib 量化平台 — 第五轮全面审查报告

**审查日期**: 2026-05-06  
**审查范围**: 全部 20 个 API 模块 + 8 个核心模块 + 18 个前端页面 + Docker 部署

---

## 总评: 74/100

| 维度 | 得分 | 满分 | 说明 |
|------|------|------|------|
| 核心量化功能 | 18 | 20 | factors/backtest/risk/portfolio 实现扎实 |
| 数据真实性 | 13 | 20 | 7 处 stub/假数据，3 处 mock fallback |
| AI/LLM 集成 | 10 | 20 | 架构完整但依赖 env vars，无用户自主配置 |
| 前端完整度 | 15 | 15 | 18 个页面，全部可用，响应式 |
| 工程质量 | 8 | 10 | 代码规范、路由清晰、TypeScript 严格 |
| 部署运维 | 5 | 10 | Docker 可用但构建慢，无 CI/CD，无用户系统 |
| 文档/测试 | 5 | 5 | 12 个单元测试 + 审查文档 |

---

## 一、做得好的（保持）

### 核心量化引擎 (factors + backtest)
- Alpha158 因子分析：IC/ICIR/rank IC、行业中性化、层次聚类降维、IC 衰减、分位数收益
- Qlib 回测：LightGBM/XGBoost、Brinson 归因、交易成本模型、A 股约束检测、统计显著性检验
- 异步任务 + 前端 3 秒轮询

### 风控 + 组合优化
- VaR/CVaR/波动率锥、Kelly 仓位、6 个 A 股历史压力场景
- 4 种优化方法 (max_sharpe/min_variance/risk_parity/equal_weight)
- Ledoit-Wolf 协方差收缩 + James-Stein 收益收缩

### 前端
- 18 个页面全部可用，响应式设计
- React Query 缓存策略合理
- shadcn/ui 组件规范

---

## 二、需要修复的

### CRITICAL — Stub/假数据（共 7 处）

| # | 文件 | 问题 | 影响 |
|---|------|------|------|
| 1 | `core/stock_pool.py` | 三层漏斗全是 stubs，用假股票代码 | 股票池功能完全不可用 |
| 2 | `core/dl_models.py` | `start_training()` 立即返回 "completed" | DL 训练是假的 |
| 3 | `core/multi_agent.py` | 4 个工具函数返回占位文本 | 智能体辩论用假数据分析 |
| 4 | `api/dl_models.py` | 训练端点直接返回完成状态 | 同上 |
| 5 | `api/index.py:318` | `_fallback_index_performance()` 生成合成数据 | 误导用户 |
| 6 | `api/pair.py` | `_mock_spread_data()` + 硬编码相关系数 0.7 | 误导用户 |
| 7 | `api/mean_reversion.py` | `generate_mock_signals()` 12 条假信号 | 误导用户 |

### HIGH — 架构问题（共 4 处）

| # | 问题 | 说明 |
|---|------|------|
| 8 | **LLM 无法由用户自主配置** | 详见下方专项分析 |
| 9 | 智能体辩论报告存内存 | 服务重启丢失 |
| 10 | 板块定义三处重复 | `hot.py` + `sectors.py` + `sector_definitions.py` 各有一套 |
| 11 | joblib 补丁三处重复 | `main.py` + `factors.py` + `backtest.py` 各自复制了一份 |

### MEDIUM — 性能/可靠性（共 5 处）

| # | 问题 |
|---|------|
| 12 | `financials.py` rank 端点串行查询 100 只股票 |
| 13 | `industry.py` performance 串行查询 |
| 14 | ETF 列表仅 20 只（硬编码） |
| 15 | ETF 成交量计算错误 (`len(prices)` 代替真实成交量) |
| 16 | 回测结果仅存内存（重启丢失） |

---

## 三、LLM 用户自主配置 — 专项分析

### 当前状态

```
环境变量 (服务器级)
  ↓
core/llm_client.py (全局单例，所有人共享同一个 key)
  ↓
api/ai_strategy.py / api/agent_debate.py / api/news_analysis.py
```

**问题**：
- 只有服务器管理员能配置 LLM
- 所有用户共享同一个 API key（费用/隐私/滥用风险）
- 无法在网页上输入自己的 DeepSeek/OpenAI key
- 没有 LLM key 时，AI 策略/智能体辩论/新闻分析全部不可用

### 需要的架构

```
用户在前端设置页输入自己的 API key
  ↓ (存入 localStorage + 每次请求带 X-LLM-Key header)
  ↓
后端读取 X-LLM-Key → 按请求创建 LLMClient 实例
  ↓
api/ai_strategy.py / api/agent_debate.py / api/news_analysis.py
```

---

## 四、评分调整建议

修复以下项目后的预期分数：

| 修复项 | 当前 → 修复后 |
|--------|-------------|
| LLM 用户自主配置 | +8 |
| Stub 数据标记/替换 (7 处) | +6 |
| 板块/补丁去重 (4 处) | +3 |
| 智能体辩论持久化 | +2 |
| 性能问题 (串行查询) | +2 |
| **合计** | **74 → 95** |

---

## 五、实施建议

### 第一优先：LLM 用户自主配置（1-2 天）
这是用户最关心的问题，也是让 AI 功能可用的前提。

### 第二优先：Stub 消除（1 天）
给所有 stub 加明确的 UI 标识（"预览模式"/"需要 Qlib 环境"），避免误导用户。

### 第三优先：去重 + 持久化（0.5 天）
板块定义统一、joblib 补丁统一、智能体报告存 SQLite。
