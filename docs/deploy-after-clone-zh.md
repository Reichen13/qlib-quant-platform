# Qlib 量化平台 — 拉取后数据不显示的排查与部署指南

> 适用场景：朋友从 GitHub 拉取本项目后，启动了前后端，但所有页面（行情、ETF、因子、回测）数据都不显示。
> 本指南按"从最常见到最少见"的顺序排查，按顺序做完就能让数据正常显示。

---

## 一句话结论先放这里

**本项目不附带任何行情数据。** GitHub 仓库里只有代码，没有 Qlib 的 bin 数据文件（`.qlib/qlib_data/cn_data/`）。拉取后必须先初始化本地数据，否则所有依赖本地数据的页面都会是空的。这不是 bug，是设计——项目原则是"没有可靠数据就明确显示为空，不用假数据伪装"。

---

## 第一步：确认本地有没有数据（最常见的根因）

### 1.1 检查数据目录

项目所有行情都读这个目录：

```
~/.qlib/qlib_data/cn_data/
```

- Windows：`C:\Users\你的用户名\.qlib\qlib_data\cn_data\`
- Linux/Mac：`~/.qlib/qlib_data/cn_data/`

里面应该有：
```
cn_data/
  ├─ calendars/day.txt          # 交易日历（必须有）
  ├─ instruments/all.txt        # 股票池清单（必须有）
  ├─ instruments/csi300.txt     # 沪深300成分
  └─ features/
      ├─ sh600000/close.day.bin # 每只股票的日线数据
      ├─ sh600000/factor.day.bin
      └─ ...
```

**如果 `features/` 目录不存在或为空，就是数据没初始化——这是数据不显示的第一原因。**

### 1.2 用项目自带命令检查

```bash
# 在项目根目录
python update_cn_data.py --check
```

这条命令会读本地数据并报告最新日期、股票数量。如果报"未找到数据"或目录不存在，确认是数据问题。

---

## 第二步：初始化数据（让数据显示起来的核心步骤）

### 2.1 安装数据拉取依赖

项目的 `backend/requirements.txt` 只装了运行时依赖。数据拉取脚本额外依赖 **baostock**（必须单独装）：

```bash
pip install baostock
```

### 2.2 小样本初始化（先验证流程通不通）

不要一上来就全量拉取（全市场 4500 只要跑几小时）。先用小样本验证：

```bash
# 拉取 10 只代表性股票的完整历史（约 1 分钟）
python update_cn_data.py --full-rebuild --max 10 --data-dir ~/.qlib/qlib_data/cn_data
```

成功后 `features/` 下会出现 10 个股票目录。此时启动后端，这几只股票的行情、因子就能显示了。

### 2.3 全量初始化（让所有股票都有数据）

小样本验证通过后，拉取全市场（需要联网，耗时约 4-8 小时，支持中断续跑）：

```bash
python update_cn_data.py --full-rebuild --all --migrate-instruments --data-dir ~/.qlib/qlib_data/cn_data
```

- `--all`：从沪深交易所成分读取约 4500 只股票
- `--migrate-instruments`：迁移沪深300、中证500 等股票池文件
- 中断了直接重跑同一条命令，已完成的股票会自动跳过

### 2.4 关于 ETF（重要）

本项目目前 **ETF 历史数据不可用**（baostock 对 ETF 覆盖不足）。ETF 轮动、ETF 筛选页面会显示"ETF 历史数据通道重建中，轮动信号暂不可用"——**这是预期行为，不是故障**。ETF 的实时行情仍会从外部源拉取。详情见 `docs/etf-independent-channel-backlog.md`。

---

## 第三步：确认后端正常连到数据

### 3.1 启动后端

```bash
# 装依赖（首次）
pip install -r backend/requirements.txt

# 启动
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
```

启动日志里会看到：
```
Qlib 初始化成功，数据目录: C:\Users\xxx\.qlib\qlib_data\cn_data
```

**如果看到"Qlib 数据目录不存在"** → 回到第二步初始化数据。

### 3.2 健康检查

打开浏览器或用 curl 访问后端健康接口：

```
http://localhost:8001/api/data/health
```

正常应返回 `status: healthy` 和数据覆盖范围。如果返回 `degraded`，按返回的 `qlib_error` 信息排查。

### 3.3 行情接口抽查

```
http://localhost:8001/api/stocks/list
```

如果返回空列表，说明后端没连上数据——回到第一步确认数据目录。

---

## 第四步：确认前端连到后端

### 4.1 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4.2 前后端地址匹配（前端数据不显示的第二大原因）

前端开发模式默认请求 `http://localhost:8001`（见 `frontend/src/lib/api.ts`）。

**如果你的后端跑在别的端口或别的机器上**，前端的 API 地址就对不上，所有请求会失败，表现为页面全空。

解决方法：在 `frontend/` 下创建 `.env.local`：

```
VITE_API_BASE=http://你的后端地址:端口
```

然后改 `api.ts` 里的 `API_BASE`，或者直接在 `api.ts:3` 把开发地址改成你的后端地址。

### 4.3 生产构建部署

如果是正式部署（不是开发模式），前端 `npm run build` 后产物走同源，需要 Nginx 反代到后端。参考项目根目录的 `deploy.sh`。

---

## 排查清单（按顺序问自己）

| 现象 | 第一步检查 |
|---|---|
| 所有页面全空 | `~/.qlib/qlib_data/cn_data/features/` 是否有数据？ |
| 后端日志报"数据目录不存在" | 数据没初始化，跑 `update_cn_data.py --full-rebuild` |
| 后端启动正常但前端空 | 浏览器 F12 看 Network，API 请求是否 200？地址对不对？ |
| API 返回 200 但数据为空 | 后端连上数据了但该股票没拉取，跑全量初始化 |
| 只有 ETF 页面空 | 正常，ETF 显式降级中（见第二步 2.4） |
| 因子分析报错 | `csi300.txt` 等股票池文件是否在 `instruments/` 下？用 `--migrate-instruments` |
| 回测报错 | alpha158 缓存可能过期，删除 `~/.qlib/alpha158_cache/` 重试 |

---

## 最小可运行顺序（给朋友的速查版）

```bash
# 1. 克隆
git clone https://github.com/Reichen13/qlib-quant-platform.git qlib
cd qlib

# 2. 装依赖
pip install -r backend/requirements.txt
pip install baostock
cd frontend && npm install && cd ..

# 3. 初始化数据（小样本先验证，约 1 分钟）
python update_cn_data.py --full-rebuild --max 10 --data-dir ~/.qlib/qlib_data/cn_data

# 4. 启动后端（终端 1）
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001

# 5. 启动前端（终端 2）
cd frontend && npm run dev

# 6. 打开 http://localhost:5173，此时 10 只股票的数据能显示

# 7. 验证通过后，全量拉取（终端 3，耗时数小时，可中断续跑）
python update_cn_data.py --full-rebuild --all --migrate-instruments --data-dir ~/.qlib/qlib_data/cn_data
```

---

## 常见踩坑

1. **Python 版本**：baostock 需要 Python 3.8-3.12。Python 3.13+ 可能装不上，建议用 3.12。
2. **数据目录权限**：`~/.qlib/` 必须可写。Docker 部署时要把这个目录挂载出来，否则容器重启数据丢失。
3. **联网**：数据拉取依赖 baostock（免费，但需要能访问 `baostock.com`）。中国大陆网络通常没问题，海外或有防火墙环境可能连不上。
4. **alpha158 缓存**：换数据后如果因子计算结果不对，删 `~/.qlib/alpha158_cache/` 让它重建。
5. **不要用假数据**：如果某页面显示空，不要去改代码塞假数据。先确认对应数据源是否可用（行情→本地Qlib，板块→akshare，ETF→降级中）。
