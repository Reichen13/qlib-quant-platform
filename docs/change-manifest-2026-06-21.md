# 2026-06-21 本地待上线改动清单

本清单用于上线和 GitHub 同步前复核。服务器版本可能领先于 GitHub，正式上线时仍要先读取服务器当前文件并做差异比对，不能直接覆盖服务器项目。

## A. 建议作为一组上线的修复

### 1. 股票代码输入与 API 统一

目的：允许页面输入 `600519`、`SH600519`、`sh.600519`、`600519.SS` 等格式，后端统一转换为 Qlib/yfinance/baostock 所需格式。

涉及文件：

- `backend/utils/code_normalization.py`
- `backend/utils/__init__.py`
- `backend/api/agent_debate.py`
- `backend/api/portfolio.py`
- `backend/api/quote.py`
- `backend/api/risk.py`
- `backend/services/data_provider.py`
- `frontend/src/pages/agent-debate/index.tsx`
- `frontend/src/pages/portfolio/index.tsx`
- `frontend/src/pages/risk/index.tsx`
- `frontend/src/pages/news-analysis/index.tsx`

上线验证：

- 风险管理输入 `600519` 不应再因为缺少 `.SS` / `.SH` 报错。
- 投资组合优化输入 `600519,300750,688981` 应能进入后端计算链路。
- 智能体辩论输入 `600519` 应转换为正确股票代码再分析。

### 2. 受保护接口的服务器管理 Key 提示

目的：风险管理、组合优化等接口需要 `X-API-Key` 时，前端显示可理解提示，而不是只暴露原始 JSON。

涉及文件：

- `frontend/src/lib/api.ts`
- `frontend/src/pages/portfolio/index.tsx`
- `frontend/src/pages/risk/index.tsx`
- `frontend/src/pages/data-management/index.tsx`

上线验证：

- 不配置服务器管理 Key 时，风险管理/组合优化提示去数据管理页配置 Key。
- 配置正确 Key 后，请求头带上 `X-API-Key`。

### 3. 行情分析 K 线显示与 0 值过滤

目的：高价股 K 线不被坐标轴压成细线；线上 Qlib 返回 0 值 OHLC 时，不再把无效行送入图表和指标展示。

涉及文件：

- `backend/api/quote.py`
- `frontend/src/pages/quote/index.tsx`
- `frontend/src/components/charts/candlestick-chart.tsx`

上线验证：

- 贵州茅台 K 线实体可正常看到，不再几乎是一条细线。
- 对当前线上 `600519`，前 28 行 0 值不会污染图表。

### 4. Qlib 历史 0 值修复能力

目的：增量更新时可选择修复已存在日期里的 `0/NaN` OHLC，而不是只追加新日期。

涉及文件：

- `update_cn_data.py`
- `backend/api/data.py`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/data-management/index.tsx`

上线验证：

- 数据管理页出现“修复已有 0 值历史 K 线”选项。
- 后端 `/api/data/update` 接收 `{"rebuild_stale": true}` 后命令包含 `--rebuild-stale`。
- 先对 `sh600519` 做定向修复，确认 `zero_ohlc_count` 从 28 下降。

### 5. 因子分析 504 修复

目的：因子分析提交接口快速返回任务号，长计算在后台执行，避免 Nginx 504。

涉及文件：

- `backend/api/factors.py`
- `frontend/src/lib/api.ts`
- `frontend/src/pages/factors/index.tsx`
- `frontend/src/stores/app-store.ts`

上线验证：

- `POST /api/factors/analyze/submit` 快速返回 `task_id`。
- `GET /api/factors/analyze/status/{task_id}` 可查询 running/completed/failed。
- 页面切换后再回到因子分析，仍能保留任务状态。

### 6. 通达信 MCP 股票列表补充

目的：在配置了 TDX MCP 的情况下，可作为全市场股票列表补充来源。当前只接入股票清单，不接入日线 K 线。

涉及文件：

- `backend/services/data_provider.py`
- `backend/tests/test_tdx_mcp_provider.py`

上线验证：

- 未配置 TDX MCP 时不影响现有 Baostock/Qlib 回退。
- 配置 TDX MCP 后，股票列表候选范围可扩大。

## B. 本轮新增测试

- `backend/tests/test_code_normalization.py`
- `backend/tests/test_data_api.py`
- `backend/tests/test_factor_analysis_tasks.py`
- `backend/tests/test_stocks.py`
- `backend/tests/test_tdx_mcp_provider.py`
- `backend/tests/test_update_cn_data.py`
- `frontend/tests/test_agent_debate_state.py`
- `frontend/tests/test_candlestick_axis.py`
- `frontend/tests/test_data_management_rebuild_stale.py`
- `frontend/tests/test_portfolio_state.py`
- `frontend/tests/test_quote_chart_data_filter.py`

已通过的关键验证：

- `backend.tests.test_factor_analysis_tasks backend.tests.test_data_api`：17 个通过。
- `backend.tests.test_update_cn_data`：8 个通过。
- 前端数据管理/K 线相关静态测试：3 个通过。
- `npm run build` 通过，只有 Vite 包体积提醒。

## C. 本轮新增文档

- `docs/current-fixes-deploy-verify-2026-06-21.md`
- `docs/change-manifest-2026-06-21.md`

## D. 上线注意事项

1. 不要只部署前端或只部署后端。代码格式统一、数据更新参数、因子后台任务和前端状态是联动的。
2. 不要直接全量修复 Qlib 数据。先按文档只修 `sh600519`，验证有效后再扩大。
3. 不要提交或复制 `.env`、API Key、服务器密码到 GitHub。
4. 不要修改服务器其他项目目录、系统 Nginx 全局配置或无关 Docker 服务。
5. 如果服务器当前版本和本地文件差异较大，先生成服务器 diff，再逐文件合并。

