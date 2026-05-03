# Qlib 量化平台 UI 改造计划
## 从 Streamlit 迁移到 Shadcn UI

---

## 📋 项目对比分析

### 当前技术栈 (Streamlit)
```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit 架构                            │
├─────────────────────────────────────────────────────────────┤
│  前端+后端: Python + Streamlit                               │
│  图表: Plotly                                                 │
│  样式: 简单 CSS                                               │
│  数据处理: Qlib + Pandas + NumPy                              │
│  部署: 单体应用                                               │
└─────────────────────────────────────────────────────────────┘
```

### 目标技术栈 (Shadcn UI)
```
┌─────────────────────────────────────────────────────────────┐
│                    Shadcn Admin 架构                         │
├─────────────────────────────────────────────────────────────┤
│  前端: React 19 + TypeScript + Vite                         │
│  UI库: Radix UI + Tailwind CSS + Shadcn                     │
│  路由: TanStack Router                                      │
│  数据请求: TanStack Query + Axios                           │
│  图表: Recharts                                             │
│  图标: Lucide React                                         │
│  状态管理: Zustand                                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    后端架构 (新增)                           │
├─────────────────────────────────────────────────────────────┤
│  API层: Python FastAPI                                      │
│  量化引擎: Qlib + Pandas + NumPy (保持不变)                  │
│  数据缓存: Redis (可选)                                     │
│  认证: JWT                                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 实施方案

### 方案选择：混合架构（推荐）

```
┌─────────────────────────────────────────────────────────────┐
│                       用户界面                               │
│                   React + Shadcn UI                         │
├─────────────────────────────────────────────────────────────┤
│  页面: Dashboard, 主题热点, 行情分析, 因子分析, 模型回测      │
│  组件: Sidebar, DataTable, Chart, Form, Dialog              │
└─────────────────────────────────────────────────────────────┘
                              ↓ REST API
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI 后端                            │
├─────────────────────────────────────────────────────────────┤
│  /api/stocks     - 股票列表和名称                            │
│  /api/hot        - 主题热点分析                              │
│  /api/quote      - 行情数据                                  │
│  /api/factors    - 因子分析                                  │
│  /api/backtest   - 模型回测                                  │
│  /api/etf        - ETF 轮动                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    量化计算引擎                              │
│                  Qlib + Python                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构规划

```
qlib-workspace/
├── backend/                    # FastAPI 后端
│   ├── api/
│   │   ├── __init__.py
│   │   ├── stocks.py          # 股票相关 API
│   │   ├── hot.py             # 主题热点 API
│   │   ├── quote.py           # 行情 API
│   │   ├── factors.py         # 因子分析 API
│   │   ├── backtest.py        # 回测 API
│   │   └── etf.py             # ETF API
│   ├── models/
│   │   └── schemas.py         # Pydantic 模型
│   ├── services/
│   │   ├── qlib_service.py    # Qlib 服务
│   │   └── data_service.py    # 数据服务
│   ├── main.py                # FastAPI 入口
│   └── requirements.txt
│
├── frontend/                   # React 前端 (基于 shadcn-admin)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/            # Shadcn UI 组件
│   │   │   ├── layout/
│   │   │   │   ├── app-sidebar.tsx
│   │   │   │   ├── header.tsx
│   │   │   │   └── main.tsx
│   │   │   ├── dashboard/
│   │   │   ├── stocks/
│   │   │   ├── backtest/
│   │   │   └── charts/
│   │   ├── features/
│   │   │   ├── dashboard/     # 仪表盘页面
│   │   │   ├── hot-topics/    # 主题热点
│   │   │   ├── quote/         # 行情分析
│   │   │   ├── factors/       # 因子分析
│   │   │   ├── backtest/      # 模型回测
│   │   │   └── etf/           # ETF 轮动
│   │   ├── lib/
│   │   │   └── api.ts         # API 客户端
│   │   └── routes/
│   ├── package.json
│   └── vite.config.ts
│
├── core/                       # 现有量化引擎
│   ├── stock_names.py
│   ├── retail_factors.py
│   └── generate_stock_names.py
│
├── app.py                      # 保留 Streamlit 版本
├── start.sh                    # 后端启动脚本
└── MIGRATION_PLAN.md           # 本文件
```

---

## 🚀 实施步骤

### Phase 1: 后端 API 开发 (1-2周)

#### 1.1 创建 FastAPI 项目骨架
```bash
cd /home/jason/projects/qlib-workspace
mkdir -p backend/api backend/models backend/services
```

#### 1.2 核心 API 端点
| 端点 | 方法 | 描述 | 对应 Streamlit 功能 |
|------|------|------|---------------------|
| `/api/stocks/list` | GET | 获取股票列表 | `get_csi300_codes()` |
| `/api/stocks/search` | GET | 搜索股票 | 股票名称搜索 |
| `/api/hot/sectors` | GET | 板块涨跌幅 | 主题热点分析 |
| `/api/hot/stocks` | GET | 个股涨跌幅 | 热门股票 |
| `/api/quote/{code}` | GET | 获取行情数据 | K线图 |
| `/api/factors/analyze` | POST | 因子IC分析 | 因子分析模块 |
| `/api/backtest/run` | POST | 运行回测 | 模型回测 |
| `/api/backtest/status/{id}` | GET | 回测状态 | 异步回测 |
| `/api/etf/signals` | GET | ETF轮动信号 | ETF轮动 |

### Phase 2: 前端项目搭建 (1周)

#### 2.1 初始化 Shadcn Admin 模板
```bash
cd /home/jason/projects/qlib-workspace
npx create-vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init
```

#### 2.2 安装依赖
```json
{
  "dependencies": {
    "react": "^19.2.3",
    "react-dom": "^19.2.3",
    "@tanstack/react-query": "^5.90.12",
    "@tanstack/react-router": "^1.141.2",
    "axios": "^1.13.2",
    "recharts": "^3.6.0",
    "lucide-react": "^0.561.0",
    "tailwindcss": "^4.1.18"
  }
}
```

### Phase 3: 页面迁移 (2-3周)

#### 3.1 页面映射表
| Streamlit 页面 | Shadcn 页面 | 路由 |
|----------------|-------------|------|
| 首页 | Dashboard | `/` |
| 主题热点 | Hot Topics | `/hot-topics` |
| 行情分析 | Quote Analysis | `/quote` |
| 因子分析 | Factor Analysis | `/factors` |
| 模型回测 | Backtest | `/backtest` |
| ETF 轮动 | ETF Rotation | `/etf` |
| ETF 全量筛选 | ETF Screener | `/etf/screener` |
| 数据管理 | Data Management | `/data` |

#### 3.2 侧边栏配置
```typescript
// src/components/layout/data/sidebar-data.ts
export const sidebarData: SidebarData = {
  navGroups: [
    {
      title: '量化分析',
      items: [
        { title: '仪表盘', url: '/', icon: LayoutDashboard },
        { title: '主题热点', url: '/hot-topics', icon: TrendingUp },
        { title: '行情分析', url: '/quote', icon: LineChart },
        { title: '因子分析', url: '/factors', icon: BarChart3 },
        { title: '模型回测', url: '/backtest', icon: PlayCircle },
      ],
    },
    {
      title: 'ETF 策略',
      items: [
        { title: '轮动信号', url: '/etf', icon: RotateCcw },
        { title: '全量筛选', url: '/etf/screener', icon: Filter },
      ],
    },
    {
      title: '系统',
      items: [
        { title: '数据管理', url: '/data', icon: Database },
        { title: '设置', url: '/settings', icon: Settings },
      ],
    },
  ],
}
```

### Phase 4: 组件开发 (2周)

#### 4.1 核心组件
| 组件 | 描述 |
|------|------|
| `StockTable` | 股票列表表格 (带名称、透明度) |
| `SectorChart` | 板块涨跌幅图表 |
| `KLineChart` | K线图组件 (复用 Plotly) |
| `FactorHeatmap` | 因子IC热力图 |
| `BacktestForm` | 回测参数表单 |
| `BacktestResults` | 回测结果展示 |
| `ETFCard` | ETF 信息卡片 |

#### 4.2 UI 组件 (Shadcn)
- `DataTable` - 数据表格 (排序、筛选、分页)
- `Card` - 卡片容器
- `Tabs` - 标签页
- `Dialog` - 对话框
- `Form` - 表单输入
- `Select` - 下拉选择
- `DatePicker` - 日期选择
- `Switch` - 开关
- `Slider` - 滑块

### Phase 5: 集成与测试 (1周)

#### 5.1 API 集成
```typescript
// src/lib/api.ts
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = {
  // 股票
  getStocks: () => axios.get(`${API_BASE}/api/stocks/list`),
  searchStocks: (query: string) => axios.get(`${API_BASE}/api/stocks/search?q=${query}`),

  // 主题热点
  getHotSectors: (days: number) => axios.get(`${API_BASE}/api/hot/sectors?days=${days}`),

  // 行情
  getQuote: (code: string, start: string, end: string) =>
    axios.get(`${API_BASE}/api/quote/${code}?start=${start}&end=${end}`),

  // 因子
  analyzeFactors: (params: FactorParams) =>
    axios.post(`${API_BASE}/api/factors/analyze`, params),

  // 回测
  runBacktest: (params: BacktestParams) =>
    axios.post(`${API_BASE}/api/backtest/run`, params),
  getBacktestStatus: (id: string) =>
    axios.get(`${API_BASE}/api/backtest/status/${id}`),
}
```

---

## 🎨 UI 设计参考

### 颜色方案
```css
/* 量化主题配色 */
:root {
  --primary: 224 76% 48%;      /* 蓝色 - 主色 */
  --success: 142 76% 36%;      /* 绿色 - 上涨 */
  --danger: 0 84% 60%;         /* 红色 - 下跌 */
  --warning: 38 92% 50%;       /* 黄色 - 警告 */
  --chart-1: 224 76% 48%;      /* 图表色1 */
  --chart-2: 142 76% 36%;      /* 图表色2 */
  --chart-3: 262 83% 58%;      /* 图表色3 */
}
```

### 仪表盘布局
```
┌─────────────────────────────────────────────────────────────┐
│  🔍 搜索                      🌙 主题    👤 用户            │
├───────────┬─────────────────────────────────────────────────┤
│           │  📊 数据状态卡片 (4个)                           │
│  侧边栏   ├─────────────────────────────────────────────────┤
│           │  📈 热门板块图表                                  │
│  - 仪表盘 │  📉 最近操作建议                                  │
│  - 热点   ├─────────────────────────────────────────────────┤
│  - 行情   │  📊 持仓分布                                      │
│  - 因子   │  💰 收益概览                                      │
│  - 回测   └─────────────────────────────────────────────────┤
│  - ETF                                                    │
└───────────┴─────────────────────────────────────────────────┘
```

---

## 📊 图表组件迁移

| Plotly 图表 | Recharts 组件 | 说明 |
|-------------|---------------|------|
| `go.Candlestick` | 自定义 KLineChart | 需要封装 |
| `go.Bar` | BarChart | 直接使用 |
| `go.Line` | LineChart | 直接使用 |
| `go.Heatmap` | Custom Heatmap | 需要封装 |
| `px.scatter` | ScatterChart | 直接使用 |

---

## 🔧 技术要点

### 数据流
```
用户操作 → React Query → API 请求 → FastAPI → Qlib 计算器
                                                           ↓
      ← 数据更新 ← 组件重渲染 ← ← ← ← ← ← ← ← ← ← ← 返回结果
```

### 状态管理
```typescript
// 使用 Zustand 管理全局状态
interface AppState {
  selectedStock: string | null
  dateRange: [Date, Date]
  theme: 'light' | 'dark'
  setSelectedStock: (code: string) => void
}
```

### 异步处理
```typescript
// 使用 TanStack Query 处理 API 请求
const { data, isLoading, error } = useQuery({
  queryKey: ['hot-sectors', days],
  queryFn: () => api.getHotSectors(days),
  refetchInterval: 60000,  // 每分钟刷新
})
```

---

## 📅 时间线

| 阶段 | 任务 | 时间 |
|------|------|------|
| Week 1-2 | FastAPI 后端开发 | API 端点实现 |
| Week 3 | 前端项目搭建 | Shadcn 初始化 |
| Week 4-5 | 页面迁移 | Dashboard, Hot Topics |
| Week 6-7 | 页面迁移 | Quote, Factors, Backtest |
| Week 8 | 组件优化 | 图表、表格组件 |
| Week 9 | 集成测试 | API 集成、测试 |
| Week 10 | 部署上线 | Docker、文档 |

**总计: 约 10 周**

---

## ⚠️ 注意事项

1. **保留 Streamlit 版本**：作为备用，逐步迁移
2. **API 兼容性**：确保后端 API 足够通用
3. **性能优化**：使用 React Query 缓存，减少 API 调用
4. **数据更新**：WebSocket 或轮询实现实时更新
5. **错误处理**：统一的错误处理机制
6. **测试覆盖**：单元测试 + 集成测试

---

## 🚦 下一步行动

需要确认：
1. 是否开始实施此迁移计划？
2. 希望先从哪个模块开始？（推荐：从后端 API 开始）
3. 是否需要保留 Streamlit 版本作为备选？
