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

## 当前限制

- 当前后端只接入 Qlib 股票日线数据更新。
- ETF/指数按钮会明确返回“不支持独立更新脚本”，不是静默假成功。
- 全量更新会写入 `/home/ubuntu/.qlib/qlib_data`，耗时可能较长，建议先小样本验证。
