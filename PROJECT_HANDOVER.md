# Qlib 量化平台 - 项目交接文档

> 生成时间：2026-05-01
> 项目路径：`/home/jason/projects/qlib-workspace`
> 云端地址：`http://49.235.215.39:9090`

---

## 一、项目概述

A股量化交易平台，从 Streamlit 单体应用迁移到 **FastAPI + React** 前后端分离架构。已部署到腾讯云轻量服务器（2C/2GB/50GB Ubuntu）。

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite + Tailwind CSS + Shadcn UI |
| 后端 | FastAPI + Pydantic + Uvicorn |
| 量化引擎 | Qlib 0.9.6（Alpha158 特征 + LightGBM/XGBoost） |
| 数据源 | Qlib 本地数据 / baostock / yfinance |
| 部署 | Docker（后端）+ 系统 Nginx（前端静态文件 + 反向代理） |
| 图表 | Lightweight Charts（K线）+ Recharts（折线/柱状图） |

### 架构

```
浏览器 → http://49.235.215.39:9090
              |
         Nginx (系统服务, 端口 9090)
         /              \
   / (静态文件)     /api (反向代理)
        |                  |
  /var/www/quant/    Docker 容器 backend (127.0.0.1:8001)
                           |
                     Qlib 数据卷 (~/.qlib/qlib_data)
```

---

## 二、已完成的工作

### 后端 API（12 个模块，约 3,500 行 Python）

| 模块 | 路径 | 状态 |
|------|------|------|
| 股票搜索 | `/api/stocks/*` | ✅ 已修复：用 baostock 加载完整 CSI300 名称，纯内存搜索 <10ms |
| 行情数据 | `/api/quote/{code}` | ✅ 返回真实 Qlib K 线数据 |
| 模型回测 | `/api/backtest/*` | ✅ 已重写为真实 Qlib 框架（Alpha158 + LGBModel + TopkDropoutStrategy + backtest_daily） |
| 热门板块 | `/api/hot/*` | ✅ 使用 yfinance 友好中文板块名 |
| 板块数据 | `/api/sectors/*` | ✅ yfinance 数据源 |
| 因子分析 | `/api/factors/*` | ⚠️ 使用简化 IC 计算，非 Qlib 标准 eval |
| ETF 信号 | `/api/etf/*` | ⚠️ 部分使用模拟数据 |
| 配对交易 | `/api/pair/*` | ⚠️ 部分使用模拟数据 |
| 均值回归 | `/api/mean-reversion/*` | ⚠️ 部分使用模拟数据 |
| 财务数据 | `/api/financials/*` | ⚠️ 使用 baostock 数据 |
| 行业分析 | `/api/industry/*` | ⚠️ 使用 baostock 数据 |
| 指数数据 | `/api/index/*` | ⚠️ 使用 baostock 数据 |

### 前端页面（10 个页面，约 6,000 行 TypeScript）

| 页面 | 路径 | 状态 |
|------|------|------|
| 仪表盘 | `/` | ⚠️ 大部分数据是 mock |
| 热门板块 | `/hot-sectors` | ✅ 真实 API 数据 |
| 行情分析 | `/quote` | ✅ 真实 Qlib K 线数据 |
| 因子分析 | `/factors` | ⚠️ 部分 mock |
| 模型回测 | `/backtest` | ✅ 真实 Qlib 回测框架 |
| ETF 轮动 | `/etf-rotation` | ⚠️ mock |
| ETF 筛选 | `/etf-screener` | ⚠️ mock |
| 均值回归 | `/mean-reversion` | ⚠️ mock |
| 配对交易 | `/pair-trading` | ⚠️ mock |
| 数据管理 | `/data-management` | ⚠️ mock |

### Docker 部署

- `docker-compose.yml` — 后端容器，端口 127.0.0.1:8001:8000，内存限制 1200MB
- `Dockerfile.backend` — python:3.11-slim 基础镜像
- 前端作为静态文件由系统 Nginx 在 9090 端口提供
- `/etc/nginx/sites-available/quant` — Nginx 配置

### 关键修复记录

1. **Qlib ParallelExt 兼容性补丁**：joblib 1.5+ 将 `_backend_args` 改名为 `_backend_kwargs`，在 `main.py:_patch_parallel_ext()` 中猴子补丁修复
2. **回测框架重写**：从随机模拟逻辑改为真实 Qlib 回测流程
3. **搜索性能优化**：移除 `get_transparency_level()` 中的 yfinance 调用（每只股票超时），改为纯内存字典搜索
4. **股票代码格式**：统一为 Qlib 格式（`SH600519` 而非 `600519.SH`）

---

## 三、当前存在的问题

### 🔴 严重问题（影响核心功能）

#### 1. 后端容器 unhealthy
- **现象**：`docker ps` 显示 `quant-backend Up X minutes (unhealthy)`
- **原因**：健康检查超时，可能是 baostock 首次加载或 yfinance 调用卡住
- **影响**：搜索 API 和其他接口可能响应超慢
- **文件**：`backend/api/stocks.py` 的 `_load_stock_names()` 使用 baostock，首次调用可能慢
- **修复方向**：在 `main.py` 启动时预加载 stock names 缓存；检查 health check 超时配置

#### 2. 搜索下拉效果未生效
- **现象**：用户输入后看不到下拉选择效果
- **已做的改动**：
  - `frontend/src/components/layout/header.tsx` — 已添加搜索 API 调用 + 下拉结果
  - `frontend/src/pages/quote/index.tsx` — 已添加搜索 API 调用 + 下拉结果
- **可能原因**：
  - 浏览器缓存了旧 JS（已给 `index.html` 加了 no-cache 头）
  - 后端搜索 API 超时导致前端收不到结果
  - 前端 `fetch` 调用的 URL 可能不对（检查 `import.meta.env.DEV` 判断）
- **修复方向**：
  1. 先确保后端 `/api/stocks/search?q=茅台` 能快速返回
  2. 在浏览器 DevTools Network 面板看搜索请求是否发出、是否返回
  3. 检查前端搜索组件的 CSS z-index 和定位是否被遮挡

### 🟡 中等问题（影响体验）

#### 3. 首页仪表盘数据大部分是 mock
- **文件**：`frontend/src/pages/dashboard/index.tsx`
- **问题**：市场概览、涨跌排行、资金流向等模块使用硬编码 mock 数据
- **修复方向**：调用后端已有 API（`/api/hot/sectors`, `/api/index/performance` 等）

#### 4. 多个策略页面使用 mock 数据
- **涉及页面**：ETF 轮动、ETF 筛选、均值回归、配对交易、数据管理
- **后端 API** 已存在但前端未接入真实数据
- **修复方向**：逐页面对接后端 API，移除 mock 数据

#### 5. `stock_names.py` 中的 `get_stock_name()` 使用 yfinance
- **问题**：首次调用时 yfinance 网络请求慢，在服务器上经常超时
- **影响**：任何调用此函数的地方都可能卡住
- **修复方向**：改用 baostock 或本地缓存文件替代 yfinance 名称查询

### 🟢 小问题

#### 6. Qlib 数据只到 2024-12-31
- 路径：`~/.qlib/qlib_data/cn_data/`
- 需要定期运行 `python update_cn_data.py` 更新

#### 7. 后端 `stock_names.py` 的 `STOCK_NAMES` 字典不完整
- 只有约 80 个硬编码映射，已通过 baostock 动态加载绕过
- 但其他 API（如 quote.py）可能仍调用 `get_stock_name()` 的 yfinance 路径

#### 8. 前端构建体积过大
- 单个 JS 包 1.18MB（gzip 后 349KB）
- 建议使用 dynamic import 拆分

---

## 四、关键文件清单

### 需要重点关注的文件

```
backend/
├── main.py                          # FastAPI 入口 + ParallelExt 补丁 + Qlib 初始化
├── api/
│   ├── stocks.py                    # 股票搜索 API（baostock 缓存）
│   ├── quote.py                     # 行情数据 API（Qlib D.features）
│   ├── backtest.py                  # 回测引擎（真实 Qlib 框架）
│   ├── factors.py                   # 因子分析
│   ├── sectors.py                   # 板块数据（yfinance）
│   └── hot.py                       # 热门板块
├── models/
│   └── schemas.py                   # Pydantic 数据模型
└── requirements.txt                 # Python 依赖

frontend/src/
├── App.tsx                          # 路由定义
├── lib/
│   └── api.ts                       # API 客户端 + 类型定义
├── components/
│   └── layout/
│       └── header.tsx               # 全局搜索栏
├── pages/
│   ├── dashboard/index.tsx          # 首页
│   ├── quote/index.tsx              # 行情分析（含搜索）
│   └── backtest/index.tsx           # 模型回测（真实 API 轮询）
└── stores/
    └── app-store.ts                 # Zustand 全局状态

根目录/
├── docker-compose.yml               # Docker 部署配置
├── Dockerfile.backend               # 后端容器镜像
├── stock_names.py                   # 股票名称映射（含 yfinance 回退）
├── app.py                           # Streamlit 原版（参考实现）
└── deploy.sh                        # 一键部署脚本
```

### 服务器上的关键路径

```
服务器: 49.235.215.39 (SSH: ubuntu@49.235.215.39, 密码: Cg2303834)

~/quant-platform/                    # 项目代码（Docker 构建 context）
├── backend/                         # 后端代码
├── docker-compose.yml
├── Dockerfile.backend
└── stock_names.py

/var/www/quant/                      # 前端静态文件（Nginx 提供）
├── index.html
├── assets/
│   ├── index-ehZ4HarY.js            # 最新构建
│   └── index-DIl0odh-.css
└── ...

/etc/nginx/sites-available/quant     # Nginx 配置（端口 9090）
~/.qlib/qlib_data/cn_data/           # Qlib 数据目录（bind mount 到容器）
```

---

## 五、部署操作速查

```bash
# SSH 登录
ssh ubuntu@49.235.215.39

# 查看容器状态
docker ps
docker logs quant-backend --tail 50

# 重建并重启后端（修改后端代码后）
cd ~/quant-platform
docker-compose build backend && docker-compose up -d backend

# 部署前端（本地构建后上传）
# 本地:
cd ~/projects/qlib-workspace/frontend && npm run build
scp -r dist/* ubuntu@49.235.215.39:/tmp/quant-dist/
# 服务器:
sudo cp -r /tmp/quant-dist/* /var/www/quant/

# 重载 Nginx
sudo nginx -t && sudo systemctl reload nginx

# 查看内存
free -h
docker stats --no-stream

# 健康检查
curl http://localhost:8001/health
curl http://localhost:9090/api/stocks/search?q=茅台
```

---

## 六、Streamlit 原版参考

`app.py`（约 3,000 行）包含完整可用的实现，是功能验证的参考。关键逻辑：

- **回测**：`app.py:1168-1304` — Alpha158 + LGBModel + TopkDropoutStrategy + backtest_daily
- **因子分析**：`app.py:约 900-1100` — 因子 IC 计算
- **ETF 轮动**：`app.py:约 600-800` — 动量排名
- **配对交易**：`app.py:约 400-600` — 协整检验 + 配对交易
- **股票名称**：`stock_names.py` 中的 `get_stock_name()` 使用 yfinance

---

## 七、建议的优先修复顺序

1. **修复后端 unhealthy** — 确保健康检查通过，搜索 API 正常响应
2. **修复搜索下拉效果** — 确认前端请求能到达后端并显示结果
3. **首页仪表盘接入真实数据** — 替换 mock 数据
4. **其余页面逐步去 mock** — ETF、均值回归、配对交易等
5. **优化 stock_names.py** — 用 baostock 替代 yfinance 名称查询
6. **定期更新 Qlib 数据** — 超过 2024-12-31 的数据需要手动更新
