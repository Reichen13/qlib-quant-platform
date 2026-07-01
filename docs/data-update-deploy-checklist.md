# 数据更新修复部署清单

本清单只针对量化平台项目本身，不处理服务器上的其他项目。服务器版本优先于 GitHub/本地版本；部署前必须先读取服务器当前代码并做差异比对。

## 变更范围

- 后端：`~/quant-platform/backend`、`~/quant-platform/update_cn_data.py`、`~/quant-platform/Dockerfile.backend`
- 后端容器：`quant-backend`
- 前端静态文件：`/var/www/quant`
- Qlib 数据目录：`/home/ubuntu/.qlib/qlib_data`

## 上线前确认

1. 先运行只读巡检，确认服务器真实版本和运行状态。不要在这一步重启、覆盖或删除任何文件：

   ```bash
   bash scripts/server_readonly_audit.sh ~/quant-platform
   ```

2. 确认当前项目目录和线上版本：

   ```bash
   cd ~/quant-platform
   pwd
   git rev-parse --is-inside-work-tree 2>/dev/null || true
   git status --short 2>/dev/null || true
   find . -maxdepth 2 -type f \( -name 'data.py' -o -name 'api.ts' -o -name 'index.tsx' -o -name 'docker-compose.yml' \) -print
   ```

3. 备份服务器当前项目和前端静态文件。后续补丁必须以这份服务器代码为基线：

   ```bash
   ts=$(date +%Y%m%d-%H%M%S)
   cp -a ~/quant-platform ~/quant-platform.bak-$ts
   sudo cp -a /var/www/quant /var/www/quant.bak-$ts
   ```

4. 配置服务器管理 Key。该 Key 只用于数据更新、回测、风险管理等受保护操作，不是 LLM API Key。

   ```bash
   echo 'API_KEY=请替换为你自己的强密码' > .env
   chmod 600 .env
   ```

5. `docker compose` 会自动读取项目根目录的 `.env`。如果暂时不创建 `.env`，后端仍可启动，但网页触发数据更新会被禁用。

## 本次可上线改动核对表（2026-06-30 核对）

下表对应本地工作区 06-22 ~ 06-29 的数据更新链路改动。每项都已跑过纯逻辑测试，判断是否具备直接上线价值。

| 文件 | 改动要点 | 测试覆盖 | 上线价值 |
|---|---|---|---|
| `backend/api/data.py` | update 端点支持 `rebuild_stale` / `overwrite_existing` / `codes` / `start_date` / `end_date`；任务状态持久化到 SQLite，进程重启可恢复；更新完成后自动清模块缓存并重载 Qlib 运行态；健康检查改用特征文件真实日期，不再被日历尾部欺骗 | `test_data_api.py` 25 项全过 | 直接上线 |
| `update_cn_data.py` | 数据源改为腾讯优先、yfinance / Baostock / 东方财富逐级回退；`--rebuild-stale` 修复 0/NaN OHLC 与异常短历史；`--overwrite-existing` 覆盖非 0 价格但保留 factor；小样本（`--max` / `--code`）不写全量股票池结束日期 | `test_update_cn_data.py` 15 项全过 | 直接上线 |
| `frontend/.../data-management/index.tsx` + `api.ts` | 新增「修复 stale 数据」开关、「指定股票代码」输入、「修正列表中的疑似标的」一键定向修复（自动带 rebuild+overwrite+codes+startDate）；页面状态用 Zustand 持久化，切换菜单不丢长任务 | `test_data_management_rebuild_stale.py` 4 项全过 | 直接上线 |
| `docker-compose.yml` | 注入 `API_KEY` / `TDX_API_KEY` / `TDX_MCP_URL` 到 backend 容器 | 已在容器环境变量中 | 直接上线 |
| `backend/api/industry.py`（06-29） | Baostock 被封后改用 akshare 东方财富行业分类（496 行业），4 端点线上验证通过 | 与数据更新链路非强相关 | 可同期上线，但属于另一条链路 |

> 本地验证命令：`py -3.12 -m pytest backend/tests/test_data_api.py backend/tests/test_update_cn_data.py frontend/tests/test_data_management_rebuild_stale.py -q` → 44 passed。

## 合并与部署步骤

1. 先把服务器当前关键文件拉回本地或在服务器上生成 diff，与本地候选补丁逐项比对。不要直接用 GitHub 版本覆盖服务器版本。

2. 只合并确认适用于服务器当前版本的文件级补丁。

3. 重建并重启后端：

   ```bash
   cd ~/quant-platform
   docker compose build backend
   docker compose up -d backend
   ```

4. 构建并发布前端：

   ```bash
   cd ~/quant-platform/frontend
   npm install --legacy-peer-deps
   npm run build
   sudo cp -r dist/* /var/www/quant/
   sudo chown -R www-data:www-data /var/www/quant
   ```

5. 检查 Nginx 配置并重载：

   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

## 验证步骤

1. 检查后端健康：

   ```bash
   curl -s http://127.0.0.1:8001/health
   curl -s http://127.0.0.1:8001/api/data/health
   ```

2. 验证未带管理 Key 时不能触发更新：

   ```bash
   curl -i -X POST http://127.0.0.1:8001/api/data/update \
     -H 'Content-Type: application/json' \
     -d '{"type":"stocks","max_stocks":1}'
   ```

3. 验证带管理 Key 的小样本更新。先只更新 1 只股票，确认链路可用，再考虑全量更新。

   ```bash
   curl -s -X POST http://127.0.0.1:8001/api/data/update \
     -H 'Content-Type: application/json' \
     -H 'X-API-Key: 请替换为你的 API_KEY' \
     -d '{"type":"stocks","max_stocks":1}'
   ```

4. 用返回的 `task_id` 查询进度：

   ```bash
   curl -s http://127.0.0.1:8001/api/data/update/返回的task_id
   ```

5. 打开页面 `http://49.235.215.39:9090/data-management`：

   - 先点“检查状态”，应快速返回。
   - 在“服务器管理 Key”输入服务器 `.env` 里的 `API_KEY`。
   - 先做小样本更新验证，再考虑全量更新。

## 数据更新链路专项验收

通用健康检查通过后，按这 5 步确认「数据更新 / 重建 stale 数据」这条链路真正可用。每步都给出期望结果，不符就停下排查。

1. **定向修复单只股票（验证 rebuild_stale + overwrite_existing + codes 闭环）**

   选一只健康检查里 `suspect_examples` 报出来的疑似跳变股票，或在 Qlib 数据里已知有 0/NaN OHLC 的代码（例如 `sh600519`），定向修复：

   ```bash
   curl -s -X POST http://127.0.0.1:8001/api/data/update \
     -H 'Content-Type: application/json' \
     -H 'X-API-Key: 请替换为你的 API_KEY' \
     -d '{"type":"stocks","codes":["600519"],"rebuild_stale":true,"overwrite_existing":true,"start_date":"2024-01-01"}'
   ```

   期望：返回 `task_id`，随后 `curl -s http://127.0.0.1:8001/api/data/update/<task_id>` 最终 `status=completed`，`message` 里能看到脚本结尾的「成功:1」字样。

2. **确认小样本不污染全量股票池**

   上一步只更新 1 只，按设计「不应改写 instruments 结束日期」。验证：

   ```bash
   curl -s http://127.0.0.1:8001/api/data/health | python3 -m json.tool | grep -A3 representative_date
   ```

   期望：`stocks.last_date` 的 `sample_latest_coverage` 很低（例如 < 0.01），说明只有极少数股票被推进，全市场日期没被误改。

3. **确认运行态缓存已刷新**

   更新 completed 后，`task_id` 详情里的 `runtime_refresh` 字段应满足：
   - `cache_cleared=true`，`cleared` 列表含 `api.etf._cache`、`api.stocks._full_name_cache` 等；
   - `qlib_reloaded=true`。

   若 `qlib_reloaded=false`，说明 Qlib 运行态没刷新，新写的 bin 文件不会被当次进程的 `D.features` 看到，需要查 `qlib_reload_error`。

4. **确认健康检查日期真的推进了（不被日历尾部欺骗）**

   再请求一次 `/api/data/health`，对比更新前后：
   - `stocks.last_date`（=特征文件 representative_date）应前进到本次更新的最新交易日；
   - `qlib.last_date` 同步前进；
   - 若 `last_date` 没变但 `sample_latest_coverage` 升高，说明只推进了部分股票，属正常（小样本）。

5. **页面端到端确认**

   打开 `http://49.235.215.39:9090/data-management`：
   - 「检查状态」快速返回，复权口径诊断卡显示 factor 状态；
   - 在「服务器管理 Key」填入 `.env` 的 `API_KEY`；
   - 勾选「修复 stale 数据」+ 填一两个代码，点更新，进度条轮询到 100%，状态卡日期推进；
   - 点「修正列表中的疑似标的」（若诊断卡列出了 suspect_examples），应自动带 `rebuild+overwrite+codes+startDate` 发起一次定向修复。

> 失败排查顺序：① `.env` 的 `API_KEY` 是否注入容器；② `update_cn_data.py` 是否在容器里能访问外网行情源；③ `~/.qlib/qlib_data/cn_data` 目录权限；④ `quant-backend` 日志 `docker logs quant-backend --tail 200`。

## 当前限制

- 当前后端只接入 Qlib 股票日线数据更新。
- ETF/指数按钮会明确返回“不支持独立更新脚本”，不是静默假成功。
- 全量更新会写入 `/home/ubuntu/.qlib/qlib_data`，耗时可能较长，建议先小样本验证。
