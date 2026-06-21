# 2026-06-21 当前修复上线验证清单

本清单只针对本轮已验证的线上问题：

- 行情分析 K 线前段出现 0 值，导致图表只从 2026 年 4 月底附近开始显示有效 K 线。
- 因子分析请求在 Nginx 前面出现 `504 Gateway Time-out`。
- ETF 轮动/筛选接口在页面请求中触发慢速外部行情补抓，容易超时或卡顿。
- 配对交易列表打开时实时重算 Qlib 指标，增加页面等待和服务器压力。

服务器上还有其他项目，上线时只允许操作量化平台项目目录、该项目的前端静态目录、该项目容器，以及该项目使用的 Qlib 数据目录。不要修改系统级配置、其他项目目录或无关服务。

## 1. 上线前只读确认

先确认真实项目目录。历史记录里出现过不同路径，必须以服务器当前实际路径为准。

```bash
pwd
ls
find ~ -maxdepth 3 -type f -name docker-compose.yml 2>/dev/null
find ~ -maxdepth 4 -type f -name update_cn_data.py 2>/dev/null
```

进入确认后的项目目录后，先做只读检查：

```bash
git status --short 2>/dev/null || true
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -s http://127.0.0.1:8001/health
curl -s 'http://127.0.0.1:8001/api/quote/600519?frequency=daily&indicators=true' | head -c 500
```

## 2. 上线前备份

不要跳过备份。项目代码、前端静态文件、Qlib 数据目录至少要各保留一份。

```bash
ts=$(date +%Y%m%d-%H%M%S)
cp -a ./ "../qlib-platform.bak-$ts"
sudo cp -a /var/www/quant "/var/www/quant.bak-$ts"
cp -a ~/.qlib/qlib_data/cn_data "$HOME/cn_data.bak-$ts"
```

如果服务器实际 Qlib 数据目录不是 `~/.qlib/qlib_data/cn_data`，先用项目配置或容器挂载确认后再备份。

## 3. 部署代码后验证服务

后端：

```bash
docker compose build backend
docker compose up -d backend
docker compose logs --tail=100 backend
curl -s http://127.0.0.1:8001/health
```

前端：

```bash
cd frontend
npm install --legacy-peer-deps
npm run build
sudo cp -r dist/* /var/www/quant/
sudo chown -R www-data:www-data /var/www/quant
sudo nginx -t
sudo systemctl reload nginx
```

## 4. K 线 0 值定向验证

先不要全量修复。先只检查贵州茅台当前线上数据：

```bash
curl -s 'http://127.0.0.1:8001/api/quote/600519?frequency=daily&indicators=true' > /tmp/quote-600519-before.json
python - <<'PY'
import json
data=json.load(open('/tmp/quote-600519-before.json', encoding='utf-8'))['data']
valid=[r for r in data if sum(abs(float(r[k] or 0)) for k in ('open','high','low','close')) > 0]
print({'total': len(data), 'zero_ohlc_count': len(data)-len(valid), 'first_valid': valid[0]['date'] if valid else None})
PY
```

再做单只股票修复：

```bash
python update_cn_data.py --code sh600519 --start 2026-03-20 --end 2026-06-19 --rebuild-stale
```

修复后复查：

```bash
curl -s 'http://127.0.0.1:8001/api/quote/600519?frequency=daily&indicators=true' > /tmp/quote-600519-after.json
python - <<'PY'
import json
data=json.load(open('/tmp/quote-600519-after.json', encoding='utf-8'))['data']
valid=[r for r in data if sum(abs(float(r[k] or 0)) for k in ('open','high','low','close')) > 0]
print({'total': len(data), 'zero_ohlc_count': len(data)-len(valid), 'first_valid': valid[0]['date'] if valid else None})
PY
```

通过标准：

- `zero_ohlc_count` 明显下降，理想情况为 0。
- `first_valid` 早于当前线上看到的 `2026-04-30`。
- 打开 `http://49.235.215.39:9090/quote` 查看贵州茅台，K 线不再只从 4 月底开始。

## 5. 因子分析 504 验证

因子分析现在应当先返回任务号，再由页面轮询状态。先用短周期验证提交接口不会等待完整计算。

```bash
curl -s -X POST http://127.0.0.1:8001/api/factors/analyze/submit \
  -H 'Content-Type: application/json' \
  -d '{"start_date":"2026-01-01","end_date":"2026-04-30","predict_period":5,"top_k":20}'
```

通过标准：

- 接口快速返回 `task_id` 和 `status: running`。
- 用返回的任务号查询：

```bash
curl -s http://127.0.0.1:8001/api/factors/analyze/status/替换为task_id
```

- 页面 `http://49.235.215.39:9090/factors` 点击运行分析后，不应再直接显示 Nginx 504 HTML。

## 6. 快速行情接口验证

ETF 轮动和配对交易列表应当快速返回；缺数据时只显示“暂无可靠数据/未生成模拟数据”类提示，不在页面请求里慢速补抓或重算。

```bash
curl -s --max-time 12 'http://127.0.0.1:8001/api/etf/signals?days=20' > /tmp/etf-signals.json
python - <<'PY'
import json
data=json.load(open('/tmp/etf-signals.json', encoding='utf-8'))
print({'etf_count': len(data.get('etfs') or []), 'warning': data.get('warning')})
PY

curl -s --max-time 12 'http://127.0.0.1:8001/api/pair/list' > /tmp/pair-list.json
python - <<'PY'
import json
data=json.load(open('/tmp/pair-list.json', encoding='utf-8'))
pairs=data.get('pairs') or []
first=pairs[0] if pairs else {}
print({
  'pair_total': data.get('total'),
  'first_data_status': first.get('data_status'),
  'first_signal': first.get('signal'),
  'first_warning': first.get('warning'),
})
PY
```

通过标准：

- 两个接口都在 `12` 秒内返回。
- ETF 接口不再因为外部行情源慢而超时。
- 配对列表首项若缺缓存，应显示 `signal: 待分析`，而不是打开列表就实时重算。

## 7. 前端包版本验证

部署后还要确认公网前端静态包确实替换成功，避免后端已更新但浏览器仍加载旧 `dist` 文件。

`scripts/verify_current_fixes.sh` 会自动读取 `PUBLIC_URL` 首页里的 JS 资源，并检查是否包含最新文案：

- `去数据管理配置 Key`
- `ETF/指数暂按 Qlib 状态代理展示`
- `指定股票代码`
- `用于提交模型回测`

脚本还会读取后端 `/openapi.json`，确认 AI 相关接口已经接收用户在设置页选择的模型名称：

- `quick_model`
- `deep_model`

通过标准：

- 输出 `FRONTEND_BUNDLE_COPY_OK`。
- 输出 `BACKEND_LLM_MODEL_PARAMS_OK`。
- 如果输出 `FRONTEND_BUNDLE_COPY_MISSING`，说明 `/var/www/quant` 或实际静态目录仍是旧包，需要重新复制前端构建产物并清理浏览器缓存后复查。

## 8. 扩大修复范围前的判断

只有在单只股票验证通过后，才考虑扩大范围：

- 如果 0 值只集中在少数股票，优先用 `--code` 定向修复。
- 如果大面积股票都有同一段 0 值，再考虑用数据管理页面勾选“修复已有 0 值历史 K 线”后执行股票数据更新。
- 全量修复前再次确认磁盘空间、备份和当前交易时段，避免在交易中或服务器高负载时运行。
