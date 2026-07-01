# CLAUDE.md

## 项目概述

Qlib Quant Platform 是一个面向 A 股个人量化研究、策略验证和盘后复盘的 Web 平台；目标用户是非职业程序员但懂投资研究、希望用真实数据做行情、因子、回测、风控、ETF 与智能分析的研究者。

## 技术栈与关键版本

- Backend: Python 3.11, FastAPI 0.115.0, Pydantic 2.9.2, Uvicorn 0.32.0。
- Quant/Data: pyqlib 0.9.6, pandas 2.2.3, numpy 2.0.0, baostock, yfinance 0.2.50, akshare。
- ML/AI: scikit-learn, LightGBM/XGBoost 相关策略接口, langchain, langchain-openai, OpenAI-compatible LLM。
- Frontend: React 19, TypeScript 6.0, Vite 8, Tailwind CSS 4, TanStack Query 5, Zustand 5。
- UI/Charts: Radix UI, lucide-react, Recharts, lightweight-charts。
- Deploy: Docker Compose, backend container `quant-backend`, optional frontend container `quant-frontend`, Nginx reverse proxy/static hosting。
- Persistence: SQLite files under `~/.qlib/`, including task/report/stock-pool stores; Qlib data under `~/.qlib/qlib_data/cn_data`。
- Security/env: `API_KEY` for protected server operations, `TDX_API_KEY` for Tongdaxin MCP, `LLM_API_KEY` or user-provided localStorage LLM key for AI features.

## 核心架构原则

- 真实数据优先：没有可靠数据时返回空值、`--`、`unavailable` 或明确 warning，不生成模拟行情、模拟评分或假结果。
- Qlib 是本地日线主数据源；读取 `D.features` 时注意真实结构通常是 MultiIndex `instrument/datetime` 行索引、字段列如 `$close`。
- 前端只负责交互和展示；关键计算、数据校验、任务状态、受保护操作应在后端完成。
- 重任务走异步任务 + 轮询状态；任务状态持久化到 SQLite，避免服务重启后“无法查询任务状态”。
- 线上受保护操作必须经 `X-API-Key`；管理 Key 只用于权限控制，不用于抓行情、LLM 或通达信。
- LLM 功能必须能区分：服务器默认 LLM 配置、用户 per-request LLM Key、服务器管理 Key；不要混用。
- 代码修改应小步、可验证、可回滚；线上服务器还有其它项目，部署时只碰 `/home/ubuntu/quant-platform`、`quant-backend` 和明确的静态目录。
- 业务结果要讲清口径：A 股覆盖数、Qlib 覆盖数、CSI300 辅助统计、ETF/指数代理状态不能混写。

## 编码规范与约定

- Python: 使用类型注解、Pydantic schema、清晰的 helper 函数；避免在 API handler 中堆大段不可测试逻辑。
- FastAPI: 用户可理解的错误用 `HTTPException(status_code, detail=...)`；内部异常记录日志，外部不泄露密钥或堆栈。
- 日志: 使用 loguru；warning 用于外部数据源失败/降级，error 用于任务失败或不可恢复错误。
- 前端 API: 统一走 `frontend/src/lib/api.ts`，通过 `handleResponse` 解析 JSON `detail/message`，不要在页面里散写 fetch。
- 前端状态: 跨菜单需保留的页面状态放 Zustand store；不要让用户切换菜单后丢失长任务或查询结果。
- 代码规范化: 股票代码通过 `utils.code_normalization.normalize_stock_code`，支持普通 A 股输入如 `600519/300750/688981`。
- 数据字段: 缺失字段用 `null` 或空数组；前端显示 `--`，不要把 0 当作“暂无可靠数据”。
- 测试: 后端以 `unittest` 为主；新增数据通道、任务状态、代码归一化、无模拟 fallback 等行为必须补测试。
- 兼容性: Qlib/joblib、MultiIndex、ETF/指数数据缺口、LLM 额度失败都要当成常见线上状态处理。
- 密钥: `.env`、API Key、服务器密码、真实 Token 不得写入代码、日志、测试快照或提交说明。

## 关键命令

```bash
# 后端本地开发
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 前端本地开发
cd frontend
npm install
npm run dev

# 前端构建
cd frontend
npm run build

# Docker 部署/重建
docker compose up -d --build
docker ps
docker logs --tail 100 quant-backend
docker restart quant-backend
docker commit quant-backend quant-platform-backend:latest

# 健康检查
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/data/health
curl "http://127.0.0.1:8001/api/quote/SH601318?indicators=true"
curl "http://127.0.0.1:8001/api/hot/sectors?days=10"
curl "http://127.0.0.1:8001/api/pair/list"

# 后端测试
python -m unittest discover backend/tests
python -m unittest backend.tests.test_qlib_multiindex_metrics
python -m unittest backend.tests.test_multi_agent_indicators
python -m unittest backend.tests.test_fast_fallback_endpoints

# 前端轻量测试/静态规则测试
python -m unittest frontend.tests.test_hot_sectors_state
python -m unittest frontend.tests.test_auth_error_guidance

# Qlib 数据检查与更新
python update_cn_data.py --check
python update_cn_data.py --max 10
python update_cn_data.py --start 2026-06-01
python update_cn_data.py --code sh600519
python update_cn_data.py --rebuild-stale
python update_cn_data.py --code sh600519 --rebuild-stale --overwrite-existing --start 2024-01-01

# 受保护的数据更新接口示例
curl -X POST http://127.0.0.1:8001/api/data/update \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"type":"stocks","codes":["600036"],"rebuild_stale":true,"overwrite_existing":true,"start_date":"2024-01-01"}'
```

## 部署与线上验证要点

- 健康检查与更新起始日要看特征文件（`close.day.bin`）的真实最新日期，不是 Qlib 日历尾部；日历可能已扩展但个股数据没跟上，会误判为"新鲜"。
- 更新 completed 后后端会自动清模块缓存并重载 Qlib 运行态；若任务详情里 `runtime_refresh.qlib_reloaded=false`，新写的 bin 不会被当次进程看到，需查 `qlib_reload_error`。


- 常规容器模式：backend 监听宿主 `127.0.0.1:8001`，frontend 可监听 `127.0.0.1:9090`。
- 当前线上可能使用宿主 Nginx 直接服务 `/var/www/quant`，API 反代到 `127.0.0.1:8001`；替换前端时先备份静态目录。
- 热修后端文件时，同步顺序：备份服务器源码 -> 上传源码 -> `docker cp` 到 `quant-backend` -> 重启 -> 验证 -> `docker commit`。
- 数据更新或全量重建会写 Qlib 数据目录，必须先做小样本验证，再扩大范围。
- LLM 429/余额不足不是代码错误；先确认 LLM Key、Base URL、模型名和资源包。

## 禁止事项（Anti-patterns）

- 禁止用模拟数据冒充真实行情、真实因子、真实 ETF 指标或真实配对信号。
- 禁止把 CSI300 数量、Qlib 覆盖数量、全市场股票清单混成同一个口径。
- 禁止让前端页面调用已知不稳定外部源作为主链路，例如 yfinance 板块批量接口。
- 禁止在页面组件里复制后端计算逻辑；应复用 API 或后端 helper。
- 禁止在未确认的情况下全量更新、删除、重建 Qlib 数据目录或服务器静态目录。
- 禁止把 `API_KEY` 当作 LLM Key 或行情 Key；三类 Key 必须隔离。
- 禁止在错误处理中吞掉关键失败原因；至少要有日志和用户可理解的 warning。
- 禁止修一个模块时顺手重构无关页面、格式化全仓或改部署目录。
- 禁止提交 `.env`、真实 API Key、服务器密码、日志里的敏感头信息。
- 禁止只看本地通过就宣称线上修好；线上版本以服务器实际访问和接口验证为准。

## 当前重点开发方向

- 数据源治理：继续减少 yfinance 主链路依赖，优先 Qlib、本地数据、通达信 MCP 或明确标注的代理数据。
- A 股覆盖：补齐全市场股票池和 Qlib 日线覆盖差距，明确科创板、创业板、北交所支持状态。
- 智能体辩论：已打通技术面 K 线/RSI/MACD/成交量摘要；下一步改善基本面、情绪面和行业数据输入。
- 配对交易：从相关性/Z-score 升级到真实协整检验、滚动 OLS 对冲比率、交易成本和流动性约束。
- 主题热点：从代表股样本扩展到完整行业分类，并统一成交额、成分股、强弱排名口径。
- 任务体验：因子分析、回测、数据更新等长任务继续异步化、持久化、可恢复、可解释。
- 性能与缓存：减少页面切换丢状态，增加轻量缓存和结果复用，避免重任务阻塞健康检查。

