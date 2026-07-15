# PROJECT_STATE.md

> 记录时间：2026-07-16  
> 范围：本地工作区 `D:\qlib`  
> Git：`main` 相对 `origin/main` **ahead 3+**（见下方提交）；本地 smoke 已通过。

## 1. 当前整体进度

平台已从「能展示」进入「数据可信门禁 + 盘后选股闭环 + 因子/回测可治理」阶段。

### 已较稳定 / 近期已落地（本地代码）

| 主题 | 说明 |
|---|---|
| data_trust | 尾部复权污染检测；`trading_allowed` 控制 buyable / 回测 / 股票池刷新 |
| core650 | 核心研究池 ~650，**不是**官方沪深300；`csi300` 仅兼容映射 |
| 盘后筛选 | 异步 `/api/screening/run` + status；股票池候选；T+5 验证 |
| 首页 focus | 精简为 holdings / buyable / trust / circuit / 决策入口 |
| 因子分析 | 串行 joblib、真实进度、心跳、僵尸失败；Alpha158 数据指纹缓存 |
| 均值回归 | JSON 禁止 nan/inf |
| 数据更新 | 腾讯 fallback 对齐限制；可选 Tushare（`TUSHARE_TOKEN`，勿与 baostock 混写增量） |

### 仍开放

- 本地日线日历尾约 **2026-07-09**，需按需增量更新并再跑 trust 断言  
- 北交所覆盖仍弱  
- ETF / 部分风控字段仍可能 `unavailable` / `--`  
- **未 push 到 origin**；线上若只跟远端 main，尚无本轮能力  
- 因子分析首次无缓存、长区间仍可能 5–15 分钟  

## 2. 重要设计决策（2026-07 补充）

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-07 | 默认研究宇宙 = `core650` | 数据质量可核验；禁止再标成「CSI300 成分」 |
| 2026-07 | data_trust 失败则禁交易动作 | 假跳空污染比「页面空着」更危险 |
| 2026-07 | ICIR 用带符号权重 | `abs(icir)` 会反转错误方向 |
| 2026-07 | Alpha158 缓存绑数据指纹 | 修 bin 后必须失效旧特征 |
| 2026-07 | 因子任务强制串行 + 心跳 | Windows daemon 线程 + loky 会卡死/僵尸 |
| 2026-07 | Tushare 可选、不可混写增量 | 复权因子基准与 baostock 不同 |

## 3. 本地数据与服务（2026-07-16 抽检）

| 项 | 值 |
|---|---|
| instruments/all | ~4481 |
| instruments/core650 | 653 |
| 日历尾 | 约 2026-07-09 |
| 后端 smoke | `127.0.0.1:8000`：health / data health / trust / mean-reversion / focus / factor submit **6/6 OK** |
| 单元测试抽样 | factor 任务、serial compat、mean-reversion json、universe、factor_scoring **通过** |

## 4. 本轮 Git 提交（本地，未默认 push）

1. `67bb023` feat: data trust gate, core650 universe, and data pipeline hardening  
2. `f1a2244` feat: async screening, T+5 verify, and focus-first dashboard  
3. `38a1043` fix: factor analysis hang, Alpha158 fingerprint cache, mean-reversion JSON nan  
4. （文档提交，若存在）docs: refresh PROJECT_STATE and CLAUDE for 2026-07  

**未入库：** `.agents/`、`zhengxi-views/`、`skills-lock.json`（已 gitignore，属 agent skill 语料）。

## 5. 关键文档

- `docs/data-trust-p0-runbook.md`  
- `docs/universe-core650.md`  
- `CLAUDE.md`  
- `.env.example`  

## 6. 建议下一步

1. 需要远端备份时：`git push origin main`（确认无密钥）  
2. 数据增量更新后：`python scripts/assert_data_trust.py --no-cache`  
3. 线上部署：只同步 `quant-platform` / `quant-backend`，先小样本再全量  
4. 前端本地：`cd frontend && npm run dev`（API 指向 8000）  
