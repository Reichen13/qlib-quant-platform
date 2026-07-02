# PROJECT_STATE.md

> 记录时间：2026-06-30  
> 范围：当前工作区 + 线上容器（已同步到 origin/main HEAD 427eebf）  
> 状态：本地工作区干净（仅剩无关的 .codex/ 目录）；2026-06-25 ~ 06-30 这一轮改动（盘后选股工作流、AI 策略模板/回测、宏观适配器、行业分类 Baostock→akshare、AI 策略 NL 生成 LLM 修复、数据更新链路）已全部提交并 push 到 origin/main，线上容器后端源码与本地 MD5 一致。数据已补齐到 06-29，lag=0，覆盖率约 93.9%，股票池 4484 只。两个硬阻塞（服务器管理 Key / LLM Key）均已解除并验证。
- 数据更新链路（data.py / update_cn_data.py / 前端数据管理页）已于 2026-06-30 完成专项核对：44 项纯逻辑测试全过，`docs/data-update-deploy-checklist.md` 已补强为可照做的最小上线包（含改动核对表 + 5 步专项验收）。

## 1. 当前整体进度

- 项目已经从“能展示”推进到“多数核心链路可真实跑通”的阶段。
- 已较稳定的模块：
  - 数据健康检查 / 数据更新任务
  - 行情分析 / K 线 / 技术指标
  - 主题热点
  - 配对交易
  - 智能体辩论的数据输入通道
  - 页面状态持久化
  - 部署验证脚本与说明文档
- 仍处于收尾和补齐阶段：
  - 全市场股票池补全到 4000+ 口径
  - ETF / 指数 / 部分风控和组合优化的真实数据闭环
  - 线上部署同步与最终验收
  - 性能、缓存、长任务体验继续优化

## 2. 重要设计决策记录

| 日期 | 决策 | 简要理由 |
|---|---|---|
| 2026-06-20 | 取消模拟数据兜底，缺数据就空值或提示 | 避免假结果污染研究判断 |
| 2026-06-20 | 页面状态用 Zustand 持久化 | 切换菜单后不丢长任务和查询结果 |
| 2026-06-21 | Qlib cn_data 作为本地主数据源 | 可追溯、稳定、适合盘后分析 |
| 2026-06-21 | 长任务改为异步任务 + 状态轮询 | 避免 504 和页面阻塞 |
| 2026-06-21 | 受保护接口统一走 `X-API-Key` | 服务器管理能力和数据源能力分离 |
| 2026-06-22 | 股票代码统一做标准化输入 | 支持 `600519` 这类自然输入 |
| 2026-06-22 | 通达信 MCP 作为可选补充源 | 扩大股票列表和行情补充能力 |
| 2026-06-22 | MultiIndex 按 `instrument/datetime` 读取 | 修复错读、空读、指标失真问题 |
| 2026-06-29 | 健康检查与更新起始日用特征文件真实日期，不信任日历尾部 | 避免日历已扩展但个股数据没跟上时误判为"新鲜" |
| 2026-06-29 | 小样本更新（`--max` / `--code`）不写全量 instruments 结束日期 | 避免只更新几只却让页面误以为全市场都已更新 |
| 2026-06-29 | 更新完成后自动清模块缓存并重载 Qlib 运行态 | 让当次进程的 `D.features` 立即看到新写的 bin 文件 |

## 3. 开放问题 / 待解决问题

> 截至 2026-06-30，原来的两个硬阻塞和"未同步线上 / 股票池未达 4000+"都已解决。下面只列真正剩余的事项。

### [已解决] 原 [阻塞] 1 / 2：LLM 与服务器管理 Key

- 服务器 `.env` 已配智谱 GLM（`glm-5.1` 快速 / `glm-5.2` 深度），`docker-compose.yml` 已传递；AI 策略 NL 生成端到端验证通过。
- 服务器管理 Key（`API_KEY`）已配置并验证有效；未带 `X-API-Key` 的 `/api/data/update` 会被拒。
- 残留风险：用户浏览器 localStorage 里若有旧 LLM key，前端已改成"服务器已配 LLM 时不传旧 key"（`427eebf`），但仍建议用户清一次浏览器旧配置。

### [已解决] 原 [高] 3 / 4：未同步线上 / 股票池未达 4000+

- 本地已 push 到 `origin/main`（HEAD `427eebf`），线上容器后端源码与本地 MD5 一致，64 项容器测试通过。
- 股票池已扩到 **4484 只**（含科创板 609 只），超过原 4000+ 目标；`instruments/all.txt` 已修复。

### [中] 1. 北交所覆盖仍是缺口

- 腾讯数据源不支持北交所，当前股票池里北交所是空白。
- 需另找数据源（akshare / Baostock 对北交所的支持待评估）或定向补 `bj` 代码。

### [中] 2. 回测标的覆盖可能偏窄

- 用户反馈线上回测结果里 A 股标的只有约 600 只，而非全市场 4000+。
- 怀疑回测用的 `stock universe` 仍指向窄样本（如 CSI300），未切到全市场 `instruments/all.txt`。
- 待核对：回测返回的标的数应接近全市场口径。

### [中] 3. ETF / 指数 / 部分风控字段仍有缺口

- 缺可靠来源的字段继续显示 `--`。
- 不能为了"看起来完整"去补模拟值。

### [中] 4. 部分模块仍带基准样本痕迹

- 与上一条相关：回测、因子、均值回归、风险等模块部分逻辑仍偏基准市场。
- 需要决定哪些保留基准、哪些切全市场，避免"对外说全市场、内部用基准"。

### [中] 5. 性能和缓存还不算彻底

- 页面切换、热点、ETF、配对、长任务仍有感知上的等待。
- 现状是"能跑"，还不是"足够丝滑"。

### [低] 6. 通达信 MCP 的部分工具名仍需最终确认

- `tdx_wenda_quotes` 已作为默认查询工具接入。
- 若要补全股票列表工具，`TDX_MCP_STOCK_LIST_TOOL` 可能还要按真实工具名确认。

## 4. 最近变更的文件列表 + 改动摘要

### 2026-06-22 ~ 2026-06-29 数据更新链路改动（已提交 e99b207，已上线同步）

> 这是把"数据更新 / 重建 stale 数据"推稳的核心一轮。详见 `docs/data-update-deploy-checklist.md`。

- `backend/api/data.py`
  - `/api/data/update` 支持 `rebuild_stale` / `overwrite_existing` / `codes` / `start_date` / `end_date`。
  - 数据更新任务状态持久化到 SQLite（`~/.qlib/data_update_tasks.db`），进程重启可恢复，并拒绝并发重复触发。
  - 更新 completed 后自动 `_refresh_runtime_after_update`：清 etf/pair/sectors/stocks 等模块缓存 + 重载 Qlib 运行态。
  - 健康检查改用特征文件（`close.day.bin`）的真实最新日期，不再被日历尾部欺骗；新增复权口径诊断（factor 字段状态、疑似未复权跳变 suspect_examples）。
- `update_cn_data.py`
  - 数据源优先级改为腾讯 `qfqday` → yfinance → Baostock → 东方财富，逐级回退。
  - `--rebuild-stale`：修复 0/NaN OHLC 行 + 重建异常短历史（`REBUILD_GAP_THRESHOLD` 判定）。
  - `--overwrite-existing`：覆盖指定窗口内非 0 价格字段，但保留 factor 不被覆盖。
  - `--max` / `--code` 小样本更新时不改写全量 instruments 结束日期。
  - 新增 `--codes-file` 批量定向更新。
- `frontend/src/pages/data-management/index.tsx` + `frontend/src/lib/api.ts`
  - 新增"修复 stale 数据"开关、"指定股票代码"输入、"修正列表中的疑似标的"一键定向修复（自动带 rebuild+overwrite+codes+startDate）。
  - 页面状态用 Zustand 持久化，切换菜单不丢长任务。
- `backend/api/industry.py`（06-29）：Baostock 被封后改用 akshare 东方财富行业分类（496 行业），属行业分类链路，与数据更新非强相关。
- 配套测试：`test_data_api.py`（25 项）、`test_update_cn_data.py`（15 项）、`test_data_management_rebuild_stale.py`（4 项）—— 2026-06-30 在本地 Python 3.12 跑通 44 passed。
- `docs/data-update-deploy-checklist.md`：已补强为最小上线包，含改动核对表 + 数据更新链路 5 步专项验收。
### 2026-06-22 本地未提交改动

- `backend/api/data.py`
  - 数据健康检查里加入 TDX MCP 状态。
  - 数据更新日志也会记录 TDX MCP 可用性。
- `backend/api/hot.py`
  - 修复 Qlib MultiIndex 读取方式。
  - 主题热点改成按真实股票序列算涨跌幅。
- `backend/api/pair.py`
  - 配对交易改为从真实 Qlib 序列提取指标。
  - `data_status` 明确标记为 `ok`。
- `backend/core/multi_agent.py`
  - 技术面指标摘要扩展为收盘价、RSI、MA、MACD、成交量、量比、趋势。
- `backend/services/tdx_mcp_provider.py`
  - 增加 MCP session、tools/list、查询封装。
  - 默认查询工具设为 `tdx_wenda_quotes`。
- `docker-compose.yml`
  - 注入 `TDX_API_KEY` 和 `TDX_MCP_URL`。

### 2026-06-22 新增 / 更新测试

- `backend/tests/test_multi_agent_indicators.py`
- `backend/tests/test_qlib_multiindex_metrics.py`
- `backend/tests/test_data_api.py`
- `backend/tests/test_fast_fallback_endpoints.py`
- `backend/tests/test_tdx_mcp_provider.py`
- `frontend/tests/test_hot_sectors_state.py`
- 重点覆盖：
  - MultiIndex 读取
  - 技术指标摘要
  - 热点板块真实 API
  - TDX MCP 会话与解析
  - 数据健康检查里的 MCP 状态

### 2026-06-20 ~ 2026-06-22 已提交的关键改动

- `backend/api/quote.py`
  - K 线历史与轴显示修复，避免高价股被压成细线。
- `backend/api/factors.py`
  - 因子分析改为后台任务模式，减少 504。
- `backend/api/backtest.py`
  - 回测状态轮询修复，任务化更稳定。
- `backend/api/risk.py`
  - 受保护接口的 Key 提示更清晰。
- `backend/api/portfolio.py`
  - 组合优化的权限与提示逻辑更明确。
- `backend/api/etf.py`
  - ETF 轮动 / 筛选改为更偏真实数据路径。
- `backend/api/data.py`
  - 数据更新任务状态持久化、支持定向更新 / 修复。
- `backend/core/stock_pool.py`
  - 股票池扩充到更接近全市场的范围。
- `backend/services/data_provider.py`
  - 引入 TDX / Baostock / Qlib 的分层数据源思路。
- `frontend/src/stores/app-store.ts`
  - 多页面状态持久化。
- `frontend/src/pages/*`
  - 多个页面加入状态恢复、错误提示和管理 Key 说明。
- `scripts/verify_current_fixes.sh`
  - 线上验证脚本。
- `docs/current-fixes-deploy-verify-2026-06-21.md`
  - 上线验证步骤。
- `docs/production-baseline-2026-06-21.md`
  - 线上基线记录。

## 5. 数据与回测现状

### 数据源

- 主数据源：Qlib `cn_data`
- 补充数据源：Baostock、akshare、yfinance
- 可选补充：通达信 MCP
- 当前原则：真实数据优先，缺失就空，不伪造

### 现状

- 股票池已经从早期"几百只"扩大到 4484 只（含科创板 609 只），超过 4000+ 目标。
- 截至 2026-06-30：`qlib last_date = 2026-06-29`，lag=0，覆盖率约 93.9%，无滞后。
- 贵州茅台等高价股 K 线曾出现 0 值 OHLC 问题，已在代码和定向修复脚本里处理，并已线上同步验证。
- 仍未覆盖：北交所（腾讯数据源不支持，需另找数据源）。

### 因子分析

- 基于 Alpha158 / Qlib 的分析框架已经存在。
- 目前更像“可提交任务 + 可轮询结果”的状态。
- 大样本或线上资源紧张时，仍可能慢，需要继续优化。

### 回测框架

- LightGBM / XGBoost / Qlib 回测链路已打通到任务化。
- 状态轮询和任务持久化已修过。
- 目前主要风险不是“完全跑不了”，而是：
  - 权限 Key
  - 数据覆盖
  - 模型资源
  - 线上是否已部署最新修复

## 6. UI / 前端现状

- 前端框架是 React 19 + Vite + TypeScript。
- 当前 UI 方向是“研究工作台”，不是营销型页面。
- 已做的主要前端修复：
  - 多个页面切换时保留状态
  - 热点板块改用真实 API
  - K 线图轴和数据过滤修复
  - 受保护功能增加 Key 提示
- 仍存在的体验点：
  - 页面切换后仍可能有少数模块恢复初始状态
  - 某些接口响应慢时，前端体感会卡
  - 目前没有统一的强缓存层，长任务仍依赖后端返回和轮询
- 结论：
  - UI 已从“演示感”明显往“可实操”走。
  - 但还没到完全轻快、全模块统一成熟的程度。

## 7. 下一步计划建议

> 截至 2026-06-30，原"先解锁、后补强"清单里的大头已经落地并验证。这一节按"已完成 / 仍要做"重排，避免把已上线的事当待办。

### 已完成并验证（2026-06-25 ~ 06-30 这一轮）

- **数据更新链路**：本地 44 项纯逻辑测试通过；`backend/api/data.py` + `update_cn_data.py` + 前端数据管理页已推 GitHub（`e99b207` 等）并线上同步。数据已补齐到 06-29，`lag=0`，覆盖率约 93.9%。部署清单 `docs/data-update-deploy-checklist.md` 已补强为可照做的最小上线包。
- **两个硬阻塞已解除**：服务器管理 Key（`API_KEY`）已配置并验证有效；服务器 LLM 已配智谱 GLM（`glm-5.1` 快速 / `glm-5.2` 深度），前端改成"服务器已配 LLM 时不传浏览器 localStorage 旧 key"，AI 策略 NL 生成端到端验证通过（`427eebf`）。
- **股票池已超 4000 目标**：从约 3875 扩到 **4484 只**，含科创板 609 只（SH688）；`instruments/all.txt` 已修复（曾因行拼接损坏）。
- **Factor 复权口径**：63300 个 NaN 已修复（916 只股票近 640 天），复权诊断正常。
- **行业分类数据源**：Baostock（被封）→ akshare 东方财富已完成并上线，4 个行业端点全部验证通过（`9c6ad2b`）。
- **盘后选股工作流**：编排层 `backend/api/screening.py` + `/api/screening` + 前端页面已实现、跑通测试、上线、端到端可用。
- **GitHub 与线上同步**：本地已 push 到 `origin/main`（HEAD `427eebf`），线上容器后端源码与本地 MD5 一致，64 项容器测试通过。

### 仍要做（真正的剩余事项）

1. **北交所覆盖**（中优先级）
   - 腾讯数据源不支持北交所，需另找数据源接入；当前股票池里北交所仍是缺口。
   - 入口：评估 akshare/Baostock 对北交所的支持，或定向补 `bj` 代码。

2. **回测标的覆盖核对**（待确认）
   - 用户反馈线上回测结果里 A 股标的只有约 600 只，而非 4000+；需核对回测用的 `stock universe` 是不是仍指向某个窄样本（如 CSI300），而不是全市场 `instruments/all.txt`（4484 只）。
   - 验收：回测返回的标的数接近全市场口径，且与 `/api/data/health` 的 `stocks.total` 对得上。

4. **容器内冗余清理**（低优先级，长期项）
   - 容器内 `backend/` 与 `backend/backend/` 双份嵌套是历史构建产物，不影响运行，但长期值得清理。

5. **性能 / 缓存 / 任务复用**（持续）
   - 热点、ETF、配对、因子、回测适合做结果复用，减少重复计算和页面卡顿。
   - 长任务继续异步化 + 持久化；数据更新链路的 SQLite 持久化 + 并发拒绝 + runtime 缓存刷新可作为其它长任务的参考实现。

## 8. 需要特别注意的坑

- 线上版本可能落后于 GitHub，本地通过不等于线上可用。
- `API_KEY` 只管服务器受保护操作，不是行情 Key，也不是 LLM Key。
- `TDX_API_KEY` 是通达信 MCP 用，不要和管理 Key 混用。
- LLM Key / Base URL / 模型名 / 资源包必须分清。
- Qlib 读取常见坑是 MultiIndex：
  - 不是所有数据都能按列索引读
  - `instrument/datetime` 的行索引要按正确层级切
- K 线里出现 0 值 OHLC 时，图表和指标都会被污染。
- 缺数据时就显示空或 `--`，不要拿模拟值填满。
- 切菜单后状态丢失，通常不是数据没回来，而是页面状态没持久化。
- 全量更新 / 全量重建前一定先小样本验证。
- 服务器还有别的项目，只能碰本项目目录，不要动全局配置和无关服务。

## 当前结论

这个项目已经不是“空壳展示页”了，核心数据链路和大部分研究模块都已往真实可用推进。

现在最关键的不是再加很多花样，而是：

- 把最新本地修复真正部署到线上
- 解决 LLM / Key 这类硬阻塞
- 补齐股票池和数据覆盖
- 继续压缩假数据、慢请求和状态丢失问题


## 2026-06-29 进展核对（本地核查）

> 核对方式：git status + 路由注册核对 + 后端纯逻辑测试（本地为 Python 3.14，未装 pandas/qlib）。
> 注：本节为 06-29 当时的即时快照。下方列出的"未提交 / 硬阻塞未解 / 股票池 3876"在 06-30 已全部解决——改动已提交 push（e99b207/9c6ad2b/427eebf）、线上已同步、LLM 与管理 Key 均已配置、股票池已达 4484。最新状态见顶部状态行与"2026-06-30 数据更新链路核对"小节。

### 自 06-24 以来已完成（仍为未提交改动）
- 盘后选股工作流：backend/api/screening.py（编排层）+ /api/screening 路由（已注册到 backend/main.py）+ frontend/src/pages/screening-workflow/；test_screening_workflow.py 11 项本地通过。
- AI 策略模板与回测：backend/api/ai_strategy.py + frontend/src/lib/ai-strategy-backtest.ts；test_ai_strategy_templates.py、test_ai_strategy_screening.py 本地通过。
- 宏观适配器：backend/api/macro.py + test_macro_data_adapters.py（依赖 pandas，本地未跑，待容器验证）。

### 本地可验证 / 不可验证
- 可验证（纯逻辑，本地通过）：screening、ai_strategy_templates、ai_strategy_screening、llm_request_models、backtest_status、agent_debate 归一化。
- 不可验证（本地未装 pandas/qlib）：test_macro_data_adapters、test_multi_agent_indicators、test_qlib_multiindex_metrics，需在 quant-backend 容器内跑。

### 待清理（需确认）
- 11 个 frontend-dist-*.tgz（06-24~06-25 部署打包产物，每个约 0.4MB），散在工作区根目录。

### 仍待推进
- 本地 34 文件改动（+2405/-250）尚未提交，线上基线仍停在 2026-06-21。
- LLM Key / 服务管理 Key 硬阻塞未解。
- 股票池仍未到完整 A 股口径（线上约 3876，目标 4000+）。

## 2026-06-30 数据更新链路核对（本地核查）

> 核对方式：精读 data.py / update_cn_data.py / 前端数据管理页 / 相关测试源码；在本地 Python 3.12（装 fastapi/loguru/pydantic/pytest/pandas/numpy）跑专项测试。

### 已验证
- 数据更新链路 44 项纯逻辑测试全过：端点参数、任务持久化与恢复、rebuild stale 修复 0/NaN、overwrite 保护 factor、小样本不写全量池、前端文案对照。
- `docs/data-update-deploy-checklist.md` 已补强，UTF-8 干净，7 个标题结构正确。

### 已上线验证（2026-06-30 会话确认）
- 数据已补齐到 06-29，lag=0，覆盖率约 93.9%；股票池 4484 只。
- 服务器管理 Key、LLM Key 均已配置并验证有效。
- 后端 64 项容器测试通过；线上容器源码与本地 MD5 一致。
- 详见本节上方"已完成并验证"小节与 docs/data-update-deploy-checklist.md。

### 后续参考
- 数据更新链路已上线；docs/data-update-deploy-checklist.md 保留为日常数据更新与回滚复用的操作手册。
- 后续做定向修复（rebuild+overwrite+codes）或全量更新时，仍建议先小样本再全量，按清单的 5 步专项验收确认。
