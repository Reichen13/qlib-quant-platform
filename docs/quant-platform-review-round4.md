# Qlib 量化平台第四轮审查报告

**日期**: 2026-05-05
**评分**: 72/100（较第三轮 66 分提升 6 分）
**目标**: 85 分以上的专业投资量化工具

---

## 评分维度

| 维度 | 权重 | 第三轮 | 第四轮 | 变化 | 说明 |
|------|------|--------|--------|------|------|
| 数据真实性 | 25% | 40 | 85 | +45 | ETF/板块/配对/Dashboard 全部真实化 |
| 功能完整性 | 20% | 70 | 72 | +2 | Brinson归因、压力测试、SQLite持久化 |
| 架构与工程化 | 20% | 55 | 68 | +13 | 认证、动态日期、收缩估计 |
| 用户体验 | 15% | 75 | 72 | -3 | 仍有个别 mock 残留 |
| 生产就绪 | 20% | 55 | 58 | +3 | Docker不完整、零测试、文档过时 |
| **加权总分** | | **57** | **72** | **+15** | |

---

## 第三轮修复确认

以下第三轮发现的 P0/P1 问题已全部修复：

- [x] ETF 轮动假数据 → 真实 yfinance 动量信号（`backend/api/etf.py` 已重写）
- [x] 行业板块假数据 → 真实成分股加权计算（`backend/api/sectors.py` 已重写，5 分钟 TTL 缓存）
- [x] 配对交易假数据 → 动态计算真实指标（`backend/api/pair.py` 已重写，15 分钟 TTL 缓存）
- [x] 首页 Dashboard 假数据 → 调用真实后端 API（`frontend/src/pages/dashboard/index.tsx` mock 已移除）
- [x] 回测任务内存存储 → SQLite 持久化（`backend/db/task_store.py` + `backtest.py` 已切换）
- [x] 无认证机制 → API Key 认证（`backend/auth.py`, router 级依赖注入）
- [x] 推荐理由模板化 → Brinson 归因动态生成（`backtest.py` 归因上下文注入）
- [x] 默认日期硬编码 → `relativeDate()` 工厂函数（`utils.ts` + `app-store.ts`）
- [x] 组合优化 → Ledoit-Wolf 收缩 + James-Stein 收缩（`portfolio.py`）
- [x] A股压力测试场景库（`risk.py`）
- [x] 因子分析随机采样替代 [:80] 截断
- [x] 行业映射启动预加载

---

## 本轮新发现问题

### P0 — 关键缺陷（0 项）

本轮未发现 P0 级问题。所有模块均已使用真实数据源。

---

### P1 — 高优先级（8 项，必须修复才能达 85 分）

#### P1-1: ETF 轮动页面 `Math.random()` 非确定性

**文件**: `frontend/src/pages/etf-rotation/index.tsx:48`

```typescript
rsiScore: Math.round(score * 0.9 + Math.random() * 10),
```

每次渲染 RSI 分数随机变化，与市场数据无关。后端 `compute_signal()` 已返回真实动量分数，前端不应再用 `Math.random()` 覆盖。**应直接使用后端的 `score` 字段计算 RSI 分数，或新增后端 RSI 字段。**

#### P1-2: 数据管理页面全部假日志

**文件**: `frontend/src/pages/data-management/index.tsx:326-365`

三条"更新日志"条目硬编码（"更新股票 3800 只，ETF 320 只"），时间用 `getLastTradeDate()` 伪装，但数据本身是假的。

**文件**: `frontend/src/lib/api.ts:516-531`

`api.data.update()` 和 `api.data.updateProgress()` 返回硬编码假响应，不调用任何后端端点。

**修复方案**:
- 后端 `data.py` 已有 `GET /health` 数据状态检查，应增加 `POST /data/sync` 端点触发 yfinance 增量同步
- 新增 `GET /data/logs` 端点返回实际数据更新历史（从 SQLite 读取）
- 前端替换假日志为真实 API 调用

#### P1-3: 板块定义 4 处重复且不一致

三个后端模块和一个前端定义各自维护独立的板块列表：

| 位置 | 板块数 | 每板块股票数 | 代码格式 |
|------|--------|-------------|---------|
| `backend/api/hot.py:55-72` | 8 | 10 | Qlib (SH/SZ) |
| `backend/api/sectors.py:22-43` | 20 | 5 | yfinance (.SS/.SZ) |
| `backend/api/dashboard.py:42-49` | 8 | 3 | Qlib (SH/SZ) |
| `frontend/src/pages/hot-sectors/index.tsx` | — | — | — |

用户访问"热门板块"看到 8 个板块（各 10 只成分股），访问"行业板块"看到 20 个板块（各 5 只成分股），同一板块涨跌幅可能不同。

**修复方案**: 提取 `backend/core/sector_definitions.py` 作为唯一数据源，所有模块引用同一份定义。Dashboard 直接调用 sectors API 而不自行定义。

#### P1-4: 技术指标前后端双重计算

**前端**: `frontend/src/pages/quote/index.tsx:121-213` — MA、Bollinger、RSI、MACD 完整实现
**后端**: `backend/api/quote.py:102-143` — MA、RSI 计算

相同逻辑维护两份，修改指标参数需同步两处。

**修复方案**: 后端 `/api/quote/{code}` 的 `indicators=true` 参数已返回 MA/RSI/MACD。前端应删除本地计算逻辑，完全依赖后端数据。如果担心网络延迟，可在前端做轻量缓存但不可重复实现指标算法。

#### P1-5: `text-white` 硬编码颜色

**文件**: `frontend/src/pages/quote/index.tsx:481`

```tsx
<span className="font-medium text-white">
```

项目统一使用 CSS 变量系统（`text-foreground`, `text-muted-foreground`），这里硬编码 `text-white` 在 light mode 下不可见。**改为 `text-foreground`。**

#### P1-6: USER_MANUAL.md 完全过时

**文件**: `USER_MANUAL.md`

描述的是 Streamlit 架构（`streamlit run app.py --server.port 8501`），而实际平台是 FastAPI + React。启动命令、端口、架构图全部错误。用户按手册操作无法启动系统。

**修复方案**: 重写为 FastAPI + React 架构，包含 Docker 部署、API Key 配置、功能模块说明。

#### P1-7: 零测试覆盖

项目目录中没有任何测试文件（排除 `venv/` 和 `node_modules/`）：
- 后端: 0 个 `test_*.py` 文件
- 前端: 0 个 `*.test.ts` 文件

量化平台的核心计算（因子 IC、Brinson 归因、协方差收缩、回测引擎）完全没有自动化验证。任何重构都可能悄悄破坏计算正确性。

**修复方案**: 
- 最小可行：为核心计算函数添加单元测试（`backend/tests/`）
  - `test_portfolio.py`: 验证 Ledoit-Wolf 收缩、James-Stein 收缩
  - `test_backtest.py`: 验证 Brinson 归因数值正确性
  - `test_pair.py`: 验证协整检验、Z-score 计算
- 前端：为关键工具函数添加测试（`relativeDate`, `toDateString`）

#### P1-8: docker-compose.yml 缺少前端和 Nginx 服务

**文件**: `docker-compose.yml`

当前仅含 `backend` 服务。前端构建和 Nginx 部署依赖 `deploy.sh` 手动完成。`Dockerfile.frontend` 已存在（多阶段构建，nginx:alpine），但未接入 compose。

**修复方案**: 添加 `frontend` 服务到 `docker-compose.yml`，使用 `Dockerfile.frontend`，代理 API 请求到 `backend:8000`。

---

### P2 — 中优先级（5 项）

#### P2-1: 两份 Nginx 配置互相矛盾

| 文件 | 端口 | API 代理目标 | 静态文件路径 | 用途 |
|------|------|-------------|-------------|------|
| `nginx.conf` | 80 | `backend:8000` | `/usr/share/nginx/html` | Docker 多服务 |
| `nginx-quant.conf` | 9090 | `127.0.0.1:8001` | `/var/www/quant` | 系统级部署 |

没有注释说明哪个是权威配置。`deploy.sh` 使用 `nginx-quant.conf`，`Dockerfile.frontend` 使用 `nginx.conf`。

**修复方案**: 
- `nginx.conf` → 重命名为 `nginx-docker.conf`，供 Docker Compose 使用
- `nginx-quant.conf` → 重命名为 `nginx-system.conf`，供系统级部署
- 在两个文件中添加注释说明用途

#### P2-2: 缺少 .env.example

项目使用 `API_KEY` 环境变量但无 `.env.example` 文档。新开发者不知道需要配置什么。

**修复方案**: 创建 `.env.example`：
```
API_KEY=your-secret-api-key-here  # 留空则跳过认证（开发模式）
DEBUG=false
```

#### P2-3: 回测无实时进度推送

前端通过 60 秒轮询 `/api/backtest/status/{task_id}` 获取进度，无 SSE/WebSocket 推送。回测可能运行 5-10 分钟，轮询效率低。

**修复方案**: 可选方案 — 将当前轮询改为 SSE（`text/event-stream`），在 `backtest.py` 的后台线程中向 SSE 连接推送进度。

#### P2-4: Dashboard 硬编码参数

**文件**: `frontend/src/pages/dashboard/index.tsx:113`

```tsx
const totalCapital = 1000000
```

本金硬编码 100 万，无法修改。首页 ETF 表格描述文字也是静态模板。

#### P2-5: 部分页面状态处理不统一

大多数页面已处理 loading/error/empty 状态（通过 `useQuery` 的 `isLoading`/`isError`），但回测页面 (`frontend/src/pages/backtest/index.tsx`) 和行情分析页面 (`frontend/src/pages/quote/index.tsx`) 部分场景缺少 error boundary。

---

### P3 — 低优先级/增强项（3 项）

- **API 限流缺失**: 无 rate limiting，yfinance 批量请求可能被限
- **请求日志中间件**: 无结构化请求日志（响应时间、状态码）
- **国际化**: 仅中文，无英文界面支持

---

## 85 分达成路径

当前 72 分 → 85 分需要修复全部 P1（8 项）和至少 3 项 P2。

### 预计修复工作量

| 优先级 | 项数 | 预计工作量 | 预计加分 |
|--------|------|-----------|---------|
| P1 | 8 | 2-3 天 | +10 |
| P2 | 5 | 1-2 天 | +5 |
| **合计** | **13** | **3-5 天** | **+15 → 87分** |

### 建议执行顺序

1. **P1-3 板块定义统一** + **P1-4 指标去重** — 消除数据源不一致这个最根本问题
2. **P1-1 Math.random() 修复** + **P1-5 text-white 修复** — 低成本高收益
3. **P1-2 数据管理真实化** — 需要后端新端点
4. **P1-6 文档重写** — 独立任务，可并行
5. **P1-7 测试** — 为核心计算添加最低限度测试
6. **P1-8 Docker 完善** — 补齐生产部署
7. **P2 各项** — 按需完成

---

## 与第三轮对比总结

第三轮核心问题是"数据造假"——4 个模块使用完全虚假的硬编码数据。本轮所有假数据模块已修复，平台从"不可信的演示系统"提升到"数据可信但工程粗糙"的阶段。剩余问题集中在代码质量、工程规范和生产就绪度，属于从 72 分打磨到 85 分的最后一公里。
