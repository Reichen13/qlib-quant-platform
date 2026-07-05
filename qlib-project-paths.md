# qlib-quant-platform 项目路径与同步指南

## 1. 项目概览

| 项目 | 值 |
|------|-----|
| GitHub 仓库 | [Reichen13/qlib-quant-platform](https://github.com/Reichen13/qlib-quant-platform) |
| 分支 | `main` |
| 本地路径 | `/home/jason/projects/qlib-workspace/` |
| 腾讯云服务器 | `ubuntu@49.235.215.39` |

---

## 2. 本地环境（WSL2）

```
/home/jason/projects/qlib-workspace/
├── backend/               # FastAPI 后端 (49 个 .py 文件)
│   ├── api/               # API 路由层
│   ├── core/              # 核心业务逻辑（LLM、因子、行业定义等）
│   ├── models/            # Pydantic 数据模型
│   ├── db/                # SQLite 持久化
│   ├── services/          # 数据服务层
│   └── main.py            # FastAPI 入口
├── frontend/              # React 前端 (TypeScript + Vite)
│   ├── src/
│   │   ├── pages/         # 页面组件
│   │   ├── components/    # UI 组件
│   │   ├── stores/        # Zustand 状态管理
│   │   └── lib/api.ts     # API 调用封装
│   └── dist/              # 构建产物（部署到服务器）
├── .git/                  # Git 仓库
├── requirements.txt       # Python 依赖
└── docs/                  # 文档
```

---

## 3. 腾讯云服务器

### 3.1 服务器信息

| 项目 | 值 |
|------|-----|
| IP | `49.235.215.39` |
| 用户 | `ubuntu` |
| SSH | `ssh ubuntu@49.235.215.39` |

### 3.2 Docker 容器

| 项目 | 值 |
|------|-----|
| 容器名 | `quant-backend` |
| 镜像 | `quant-platform-backend` |
| 应用路径 | `/app/` |
| API 代码 | `/app/backend/api/` |
| 端口映射 | `8000 → 127.0.0.1:8001` |
| 数据卷 | `/home/ubuntu/.qlib/qlib_data` → `/root/.qlib/qlib_data` |

### 3.3 Nginx 配置

| 项目 | 值 |
|------|-----|
| 监听端口 | `9090` |
| 配置路径 | `/etc/nginx/sites-available/quant` |
| API 代理 | `/api/` → `http://127.0.0.1:8001/api/` |
| 前端静态文件 | `/var/www/quant/` |

### 3.4 关键服务端口

```
用户请求 → :9090 (nginx) → /api/* → :8001 (docker) → :8000 (uvicorn)
                           → /*     → /var/www/quant/ (静态文件)
```

---

## 4. GitHub 仓库

| 项目 | 值 |
|------|-----|
| 仓库地址 | `https://github.com/Reichen13/qlib-quant-platform` |
| 认证方式 | Personal Access Token（embedded in remote URL） |
| 默认分支 | `main` |

---

## 5. 同步方式

### 5.1 代码同步：本地 → 服务器

**部署后端**（每次代码修改后执行）：

```bash
# 1. 上传文件到服务器
scp <本地文件> ubuntu@49.235.215.39:/tmp/

# 2. 复制到容器内
ssh ubuntu@49.235.215.39 "docker cp /tmp/<文件> quant-backend:/app/backend/api/<文件>"

# 3. 重启容器
ssh ubuntu@49.235.215.39 "docker restart quant-backend"
```

**一次性部署多个文件示例**：

```bash
scp backend/api/sectors.py backend/api/quote.py ubuntu@49.235.215.39:/tmp/ && \
ssh ubuntu@49.235.215.39 "
  docker cp /tmp/sectors.py quant-backend:/app/backend/api/sectors.py && \
  docker cp /tmp/quote.py quant-backend:/app/backend/api/quote.py && \
  docker restart quant-backend
"
```

**部署前端**（构建后执行）：

```bash
# 上传构建产物
scp -r frontend/dist/* ubuntu@49.235.215.39:/tmp/qlib-dist/

# 复制到 nginx 目录并重载
ssh ubuntu@49.235.215.39 "
  sudo cp -r /tmp/qlib-dist/* /var/www/quant/ && \
  sudo nginx -s reload
"
```

### 5.2 代码同步：本地 → GitHub

```bash
cd /home/jason/projects/qlib-workspace
git add <文件>
git commit -m "描述"
git push origin main
```

### 5.3 数据同步

Qlib 本地数据通过 Docker volume 挂载，无需同步：
- **宿主机路径**: `/home/ubuntu/.qlib/qlib_data/cn_data/`
- **容器内路径**: `/root/.qlib/qlib_data/cn_data/`

数据直接操作宿主机文件，容器可实时读取。

### 5.4 pip 包安装（服务器容器内）

```bash
ssh ubuntu@49.235.215.39 "docker exec quant-backend pip install <包名>"
```

> 腾讯云服务器访问 PyPI 可能较慢，建议使用清华镜像：
> ```bash
> ssh ubuntu@49.235.215.39 "docker exec quant-backend pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <包名>"
> ```

---

## 6. 注意事项

1. **容器重启后需等待 2-3 分钟**：baostock 行业映射在启动时预加载 690 只 CSI300 股票，耗时较长。健康检查会显示 `(unhealthy)` → `(healthy)` 的过程。

2. **数据源限制**：腾讯云服务器 IP 被 Yahoo Finance (`yfinance`) 和东方财富 (`akshare`) 封禁。目前股票数据通过本地 Qlib 数据提供（最后交易日：2026-04-30，约滞后 6 天）。

3. **Qlib 版本兼容**：Qlib 0.9.6 的 `ParallelExt` 类与新版 joblib 不兼容。已在容器中打补丁修复（`/usr/local/lib/python3.11/site-packages/qlib/utils/paral.py`），但容器重建后需重新打补丁。

4. **localStorage 中的 API Key**：用户 LLM API Key 保存在浏览器 localStorage 中，通过 HTTP Header (`X-API-Key`, `X-LLM-Base-URL`) 发送，不会出现在 URL 或 nginx access log 中。

5. **API 超时**：部分端点（板块数据、因子分析）执行时间较长（20-30s），前端 `api.ts` 中已配置相应超时时间。

---

## 7. 常用命令速查

```bash
# 查看容器状态
ssh ubuntu@49.235.215.39 "docker ps -a | grep quant"

# 查看容器日志（最近 50 行）
ssh ubuntu@49.235.215.39 "docker logs quant-backend --tail 50"

# 测试 API（从服务器内部）
ssh ubuntu@49.235.215.39 "curl -s --max-time 10 'http://127.0.0.1:8001/api/sectors/list'"

# 测试 API（外部，绕过本地代理）
curl -s --noproxy '*' --max-time 10 "http://49.235.215.39:9090/api/sectors/list"

# 前端构建
cd /home/jason/projects/qlib-workspace/frontend && npm run build
```
