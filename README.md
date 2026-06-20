# Qlib A股量化分析平台

一个基于 Qlib、FastAPI 和 React 的 A 股量化分析平台，面向个人研究、策略验证和市场复盘场景。项目重点不是做“演示型页面”，而是尽量把行情、ETF、指数、因子、回测、风险和股票池等模块接到可追溯的数据源上；缺少可靠数据时明确显示为空或提示，不用模拟数据伪装真实结果。

## 功能概览

- **首页仪表盘**：股票覆盖数量、行业板块、ETF 信号、大盘趋势、主要指数表现对比。
- **数据管理**：Qlib 本地数据健康检查、更新任务触发、更新进度查询。
- **行情分析**：股票/ETF K 线和技术指标查询。
- **主题热点**：行业板块涨跌幅排行和成分股查看。
- **因子分析**：基于 Qlib Alpha158 的因子 IC、Rank IC、ICIR 等分析。
- **模型回测**：LightGBM / XGBoost 等策略回测和结果展示。
- **ETF 轮动与筛选**：优先使用本地 Qlib ETF 行情，缺失指标显示 `--`。
- **均值回归 / 配对交易**：基于真实行情计算信号，数据不可用时返回空状态。
- **风险管理 / 组合优化**：组合风险指标、压力测试、头寸建议、资产配置。
- **AI 策略 / 新闻分析 / 智能体辩论**：可配置 LLM Key 与 Base URL，用于辅助策略解释和新闻情绪分析。
- **智能股票池**：使用 Baostock 全市场股票列表或本地 Qlib 行情目录作为候选范围，按硬过滤、因子打分、组合约束三层筛选。

## 技术栈

**后端**

- FastAPI + Pydantic
- Qlib / Pandas / NumPy
- Baostock / yfinance / akshare
- Loguru

**前端**

- React 19 + TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- Recharts / Lightweight Charts
- Radix UI / Lucide React

**部署**

- Docker Compose
- Nginx 静态站点与 API 反向代理
- Qlib 数据目录通过 volume 挂载

## 项目结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── api/                 # 业务 API 路由
│   ├── core/                # 股票池、模型、缓存、新闻等核心逻辑
│   ├── services/            # 数据提供层
│   ├── models/              # Pydantic 数据模型
│   └── tests/               # 后端测试
├── frontend/                # React 前端
│   ├── src/components/      # UI、图表和功能组件
│   ├── src/pages/           # 页面模块
│   └── src/lib/api.ts       # 前端 API 客户端
├── docs/                    # 审计、部署和数据治理文档
├── scripts/                 # 服务器巡检、数据修复和验证脚本
├── update_cn_data.py        # Qlib 股票日线增量更新脚本
├── docker-compose.yml       # 容器编排
└── Dockerfile.backend       # 后端镜像
```

## 数据口径

项目目前使用多数据源组合：

- **Qlib cn_data**：主要股票日线、ETF 日线、Alpha158 因子、指数表现。
- **Baostock**：全市场股票列表、行业分类、部分行情备用。
- **yfinance**：ETF 或股票行情备用源。
- **akshare**：宏观与部分市场数据。

当前代码遵循一个基本原则：**没有可靠数据就显示为空或明确提示，不生成模拟行情、模拟评分或示例结果。**

典型表现：

- ETF PE、基金规模等暂未接入可靠来源时显示 `--`。
- ETF 只有能获取真实行情的标的才计算涨跌幅、夏普、动量等指标。
- 股票池候选范围可来自全市场列表；但真正能参与 Qlib 因子/动量评分的股票，取决于本地 Qlib 行情目录覆盖。
- 数据管理页会区分全市场股票清单、Qlib 本地日线覆盖、CSI300 辅助统计，避免把 CSI300 数量误认为全市场数量。

## 快速开始

### 1. 准备环境

建议使用 Docker Compose 启动完整服务。服务器或本机需要准备：

- Docker / Docker Compose
- 一个 Qlib 数据目录，例如 `~/.qlib/qlib_data/cn_data`
- 可选：`.env` 中配置服务器管理 Key

`.env` 示例：

```bash
API_KEY=replace-with-your-own-admin-key
```

`API_KEY` 只用于保护会修改服务器数据的接口，例如 `/api/data/update`。不配置时，服务可以启动，但网页触发数据更新会被禁用。

### 2. 启动服务

```bash
docker compose up -d --build
```

默认端口：

- 后端：`http://127.0.0.1:8001`
- 前端容器：`http://127.0.0.1:9090`
- 后端 API 文档：`http://127.0.0.1:8001/docs`

### 3. 验证服务

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/data/health
curl "http://127.0.0.1:8001/api/stocks/search?q=300750"
curl "http://127.0.0.1:8001/api/etf/signals?days=20"
```

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发环境前端默认请求 `http://localhost:8000`，生产构建使用相对路径，由 Nginx 或同域代理转发到后端。

## 数据更新

网页更新入口对应后端：

```text
POST /api/data/update
GET  /api/data/update/{task_id}
```

也可以直接运行脚本：

```bash
python update_cn_data.py --check
python update_cn_data.py --max 10
python update_cn_data.py --start 2026-06-01
```

常用参数：

- `--check`：只检查本地 Qlib 数据状态。
- `--max N`：只更新前 N 只股票，适合小样本验证。
- `--code sh600519`：只更新指定 Qlib 代码，可重复传入。
- `--codes-file path.txt`：按文件中的代码列表更新。
- `--rebuild-stale`：修复明显异常的短历史文件。

全量更新会写入 Qlib 数据目录，耗时较长，建议先做小样本验证。

## 测试

后端测试：

```bash
python -m unittest discover backend/tests
```

前端构建：

```bash
cd frontend
npm run build
```

## 部署注意事项

- 线上部署前先备份项目目录、前端静态目录和 Qlib 数据目录。
- 不要把 `.env`、私钥、服务器密码、真实 API Key 提交到 GitHub。
- `docs/data-update-deploy-checklist.md` 记录了更完整的服务器部署和验证步骤。
- `scripts/server_readonly_audit.sh` 可用于只读巡检服务器项目状态。

## 当前边界

- 本项目用于量化研究和辅助分析，不构成投资建议。
- 部分宏观、新闻、财务和 LLM 功能依赖外部服务，可用性取决于网络和 API 配置。
- Qlib 本地数据覆盖范围会影响因子、回测、股票池等模块的有效结果。
- ETF、指数等模块已尽量接入真实数据；暂未接入可靠来源的字段会显示为空。

## License

当前仓库尚未声明开源许可证。如需公开复用，请先补充明确的 LICENSE。
