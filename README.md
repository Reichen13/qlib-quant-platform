# Qlib A股量化分析平台

一个面向个人量化研究、A 股市场复盘和策略验证的 Web 平台。后端基于 FastAPI 与 Qlib，前端基于 React 与 Vite，目标是把行情、ETF、指数、因子、回测、风险和 AI 辅助分析放到一个可本地部署、可审计、可持续维护的系统里。

项目原则很简单：**真实数据优先，没有可靠数据就明确显示为空或不可用，不用模拟数据伪装真实行情、真实因子或真实投资结论。**

> 本项目用于研究和辅助分析，不构成投资建议。市场数据、模型结果和 AI 输出都需要使用者自行核对。

## 目录

- [功能概览](#功能概览)
- [技术架构](#技术架构)
- [项目结构](#项目结构)
- [数据口径](#数据口径)
- [快速部署](#快速部署)
- [本地开发](#本地开发)
- [配置说明](#配置说明)
- [数据更新](#数据更新)
- [常用验证](#常用验证)
- [隐私与发布边界](#隐私与发布边界)
- [故障排查](#故障排查)
- [当前边界](#当前边界)

## 功能概览

- **首页仪表盘**：展示股票覆盖数量、行业板块、ETF 信号、大盘趋势和主要指数表现。
- **数据管理**：检查本地 Qlib 数据健康状态，触发增量更新，查询后台任务进度。
- **行情分析**：查询股票与 ETF K 线、技术指标和基础行情。
- **主题热点**：基于板块定义和本地行情计算行业板块涨跌幅排行。
- **因子分析**：基于 Qlib Alpha158 计算 IC、Rank IC、ICIR 等因子表现。
- **模型回测**：支持 LightGBM、XGBoost 等模型策略回测和结果展示。
- **ETF 轮动与筛选**：优先使用本地 Qlib ETF 行情；缺失字段显示 `--`。
- **均值回归 / 配对交易**：基于真实行情计算信号，数据不足时返回空状态。
- **风险管理 / 组合优化**：提供组合风险指标、压力测试、头寸建议和资产配置入口。
- **AI 策略 / 新闻分析 / 智能体辩论**：支持配置 OpenAI-compatible LLM，用于辅助策略解释、新闻情绪和多智能体讨论。
- **智能股票池**：使用全市场股票列表或本地 Qlib 覆盖范围作为候选，按硬过滤、因子打分、组合约束筛选。

## 技术架构

### 后端

- Python 3.11+
- FastAPI + Pydantic
- Qlib / Pandas / NumPy
- Baostock / akshare / yfinance
- Loguru
- SQLite 本地任务与缓存文件
- OpenAI-compatible LLM 接入

### 前端

- React 19 + TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- Recharts / Lightweight Charts
- Radix UI / Lucide React

### 部署

- Docker Compose
- Nginx 静态站点与 API 反向代理
- Qlib 数据目录通过 volume 挂载，不进入 Git 仓库

## 项目结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── api/                 # 业务 API 路由
│   ├── core/                # 股票池、模型、缓存、新闻等核心逻辑
│   ├── models/              # Pydantic 数据模型
│   ├── services/            # 数据提供层
│   └── tests/               # 后端测试
├── frontend/                # React 前端
│   ├── src/components/      # UI、图表和功能组件
│   ├── src/pages/           # 页面模块
│   └── src/lib/api.ts       # 前端 API 客户端
├── docs/                    # 审计、部署和数据治理文档
├── scripts/                 # 服务器巡检、数据修复和验证脚本
├── update_cn_data.py        # Qlib 股票日线增量更新脚本
├── docker-compose.yml       # Docker Compose 编排
├── Dockerfile.backend       # 后端镜像
├── Dockerfile.frontend      # 前端镜像
└── README.md                # 项目说明
```

## 数据口径

项目使用多数据源组合，不同数据的定位不同：

- **Qlib cn_data**：主要股票日线、ETF 日线、指数表现、Alpha158 因子和回测输入。
- **Baostock**：全市场股票列表、部分基础行情或行业信息备用。
- **akshare**：宏观、行业、市场辅助数据。
- **yfinance**：部分 ETF 或股票行情备用源，仅在明确可用时使用。
- **LLM**：只做解释、总结和辅助分析，不作为行情或交易数据源。

重要口径：

- 没有可靠数据时返回空值、空数组、`--` 或 `unavailable`，不生成模拟值。
- 股票池候选范围和 Qlib 实际日线覆盖范围不是同一个概念。
- CSI300 统计只代表指数样本或辅助口径，不能当作全市场覆盖数量。
- ETF 的 PE、规模等字段如果没有可靠来源，会显示为空，不用假数据补齐。

## 快速部署

以下步骤适合希望在自己电脑、NAS、小型服务器或云主机上部署的人。

### 1. 准备硬件和系统

建议配置：

- CPU：2 核以上
- 内存：4 GB 以上，回测和因子分析建议 8 GB 以上
- 磁盘：至少 20 GB 可用空间，取决于 Qlib 数据规模
- 系统：Linux 服务器最省心；Windows / macOS 可用于本地开发

必需软件：

- Git
- Docker
- Docker Compose

### 2. 克隆仓库

```bash
git clone https://github.com/Reichen13/qlib-quant-platform.git
cd qlib-quant-platform
```

### 3. 准备 Qlib 数据目录

本项目不把市场数据放进 GitHub。你需要在部署机器上准备自己的 Qlib 数据目录。

默认 `docker-compose.yml` 挂载路径是：

```text
/home/ubuntu/.qlib/qlib_data -> /root/.qlib/qlib_data
```

如果你的数据目录不在 `/home/ubuntu/.qlib/qlib_data`，请修改 `docker-compose.yml` 中 backend 服务的 volume，例如：

```yaml
volumes:
  - /your/local/.qlib/qlib_data:/root/.qlib/qlib_data
```

如果暂时没有完整数据，也可以先启动系统，再通过数据管理页或 `update_cn_data.py` 做小样本更新验证。

### 4. 创建本地环境变量

在项目根目录创建 `.env`。真实 `.env` 不要提交到 GitHub。

```bash
API_KEY=replace-with-your-own-admin-key

# 可选：服务器默认 LLM 配置
LLM_BASE_URL=
LLM_API_KEY=
LLM_QUICK_MODEL=glm-5.1
LLM_DEEP_MODEL=glm-5.2

# 可选：通达信 MCP 配置
TDX_API_KEY=
TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
TDX_MCP_STOCK_LIST_TOOL=
```

说明：

- `API_KEY` 用于保护会修改服务器数据的接口，例如 `/api/data/update`。
- `LLM_API_KEY` 只用于 AI 功能，不是服务器管理 Key。
- `TDX_API_KEY` 只用于通达信相关数据能力，不是服务器管理 Key。
- 如果不配置这些 Key，基础页面可以启动，但对应受保护或外部服务功能会不可用。

### 5. 启动服务

```bash
docker compose up -d --build
```

默认端口：

- 前端页面：`http://127.0.0.1:9090`
- 后端 API：`http://127.0.0.1:8001`
- 后端文档：`http://127.0.0.1:8001/docs`

如果部署在云服务器，建议用 Nginx、Caddy 或反向代理暴露前端页面，不建议直接把后端管理接口裸露到公网。

### 6. 首次验证

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/data/health
curl "http://127.0.0.1:8001/api/stocks/search?q=300750"
curl "http://127.0.0.1:8001/api/etf/signals?days=20"
```

如果这些接口能返回 JSON，说明后端已经启动。接着打开 `http://127.0.0.1:9090` 检查页面。

## 本地开发

### 后端开发

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
```

当前开发环境前端 API 地址在 `frontend/src/lib/api.ts` 中配置为 `http://localhost:8001`。生产构建使用相对路径，由 Nginx 或同域代理转发到后端。

## 配置说明

| 配置项 | 是否必需 | 用途 |
| --- | --- | --- |
| `API_KEY` | 推荐 | 保护数据更新等管理接口 |
| `LLM_BASE_URL` | 可选 | OpenAI-compatible LLM 服务地址 |
| `LLM_API_KEY` | 可选 | AI 策略、新闻分析、智能体辩论等功能 |
| `LLM_QUICK_MODEL` | 可选 | 较快的默认模型 |
| `LLM_DEEP_MODEL` | 可选 | 较强的默认模型 |
| `TDX_API_KEY` | 可选 | 通达信 MCP 数据能力 |
| `TDX_MCP_URL` | 可选 | 通达信 MCP 服务地址 |
| `TDX_MCP_STOCK_LIST_TOOL` | 可选 | 通达信股票列表工具名 |

不要把真实 Key、服务器账号、私钥、Cookie、Token 写入代码、README、Issue 或提交记录。

## 数据更新

网页更新入口对应后端接口：

```text
POST /api/data/update
GET  /api/data/update/{task_id}
```

也可以直接运行脚本：

```bash
python update_cn_data.py --check
python update_cn_data.py --max 10
python update_cn_data.py --start 2026-06-01
python update_cn_data.py --code sh600519
python update_cn_data.py --code sh600519 --rebuild-stale --overwrite-existing --start 2024-01-01
```

常用参数：

- `--check`：只检查本地 Qlib 数据状态。
- `--max N`：只更新前 N 只股票，适合小样本验证。
- `--code sh600519`：只更新指定 Qlib 代码，可重复传入。
- `--codes-file path.txt`：按文件中的代码列表更新。
- `--rebuild-stale`：修复明显异常的短历史文件。
- `--overwrite-existing`：覆盖已有数据，使用前建议先做小样本验证。

全量更新会写入 Qlib 数据目录，耗时较长，也更容易暴露网络或数据源限制。建议先小样本验证，再扩大范围。

## 常用验证

### 后端测试

```bash
python -m unittest discover backend/tests
```

### 前端构建

```bash
cd frontend
npm run build
```

### Docker 状态

```bash
docker compose ps
docker logs --tail=100 quant-backend
docker logs --tail=100 quant-frontend
```

### Git 发布前检查

```bash
git status --short --branch
git diff --stat
git ls-files --others --exclude-standard
git grep -n -I -E "API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE KEY"
```

发布前请确认：

- `.env`、私钥、服务器密码、真实 API Key 没有进入 Git。
- Qlib 数据、CSV 导出、SQLite、本地模型文件、离线 wheel 包没有进入 Git。
- `git status` 中只包含你确实想发布的源码和文档改动。

## 隐私与发布边界

这个仓库只应该同步源码、文档、配置模板和可复现的脚本。以下内容不应同步到 GitHub：

- `.env`、`.env.*`、真实 API Key、LLM Key、通达信 Key。
- 服务器账号、SSH 私钥、公钥授权文件、证书、Cookie、Token。
- Qlib 市场数据目录、`.bin`、`.parquet`、`.pkl`、SQLite 数据库。
- 本地日志、临时脚本、Codex 会话产物、Playwright 缓存、离线 wheel 包。
- Excel、CSV、PDF、Word 等可能包含个人或业务数据的导出文件。

`.gitignore` 已按这些边界设置防护，但发布前仍建议执行一次敏感扫描。

## 故障排查

### 页面能打开，但 API 失败

- 检查后端是否运行：`curl http://127.0.0.1:8001/health`
- 检查前端 API 地址是否指向正确端口。
- Docker 部署时确认 Nginx 或前端容器是否正确代理 `/api`。

### 数据健康检查为空或覆盖数量很低

- 确认 Qlib 数据目录已经挂载到容器内 `/root/.qlib/qlib_data`。
- 检查 `calendars/day.txt`、`features/` 等目录是否存在。
- 先运行 `python update_cn_data.py --check`，不要直接全量重建。

### AI 功能不可用

- 检查 `LLM_BASE_URL` 是否是 OpenAI-compatible API 地址。
- 检查 `LLM_API_KEY` 是否有效，且模型名与服务商一致。
- 如果只是测试连接超时，可先确认后端日志，不要把服务器管理 Key 当成 LLM Key。

### 回测或因子分析很慢

- Qlib 计算依赖本地数据和机器性能。
- 先用较短日期区间和较小股票池验证。
- Docker 内存过小会导致计算慢或任务失败，可调整 `docker-compose.yml` 的资源限制。

## 当前边界

- 本项目不提供市场数据授权，使用者需要自行准备合法数据来源。
- 部分宏观、新闻、财务和 LLM 功能依赖外部服务，可用性取决于网络和 API 配置。
- Qlib 本地数据覆盖范围会影响因子、回测、股票池和板块排行结果。
- 任何策略、模型或 AI 解释都只能作为研究参考，不应直接作为交易依据。

## License

当前仓库尚未声明开源许可证。如需开放给他人复用，建议补充明确的 `LICENSE` 文件。
