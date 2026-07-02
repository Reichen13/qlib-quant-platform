# Windows 本地安装快速指南

这份文档面向第一次在自己电脑上部署本项目的用户。你不需要使用 Codex，也不需要理解全部代码；只要能按步骤安装软件、复制命令、查看终端输出，就可以把前端页面和后端 API 在本地跑起来。

> 本项目不会自带市场数据、API Key、服务器账号或任何私人配置。每个人都需要准备自己的本地数据和自己的 Key。

## 你最终会得到什么

完成后，你会在本地电脑打开：

- 前端网页：`http://localhost:5173`
- 后端 API：`http://127.0.0.1:8001`
- 后端健康检查：`http://127.0.0.1:8001/health`

## 一、安装前准备

### 1. 推荐环境

- Windows 10 或 Windows 11
- 至少 8GB 内存，推荐 16GB
- 至少 20GB 可用磁盘空间
- 稳定网络连接

### 2. 需要安装的软件

请先安装：

1. Git：<https://git-scm.com/download/win>
2. Python 3.12：<https://www.python.org/downloads/windows/>
3. Node.js 20 LTS 或更高：<https://nodejs.org/>
4. VS Code（可选）：<https://code.visualstudio.com/>

安装 Python 时建议勾选：

```text
Add python.exe to PATH
```

安装完成后，打开 PowerShell，检查版本：

```powershell
git --version
python --version
node --version
npm --version
```

如果这些命令都能显示版本号，说明基础环境可用。

## 二、下载项目代码

选择一个你常放代码的目录，例如：

```powershell
cd $HOME\Documents
git clone https://github.com/Reichen13/qlib-quant-platform.git
cd qlib-quant-platform
```

如果你下载的是 ZIP，也可以解压后进入项目目录，但更推荐用 Git。

## 三、创建后端 Python 环境

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

如果 PowerShell 提示不允许执行脚本，可以临时执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

确认当前 Python 来自 `.venv`：

```powershell
python -c "import sys; print(sys.executable)"
```

你应该看到路径里包含：

```text
.venv\Scripts\python.exe
```

## 四、准备 Qlib 市场数据

这是最容易卡住的一步。

本仓库不会包含市场数据。你需要自己准备 Qlib A 股数据目录。默认路径是：

```text
C:\Users\你的用户名\.qlib\qlib_data\cn_data
```

这个目录里通常应包含：

```text
calendars\day.txt
features\sh600000\close.day.bin
features\sz000001\close.day.bin
instruments\all.txt
```

如果你还没有 Qlib 数据，可以先查阅 Qlib 官方文档，下载或生成中国市场数据：

<https://qlib.readthedocs.io/>

准备好后，可以在 PowerShell 里检查：

```powershell
Test-Path "$HOME\.qlib\qlib_data\cn_data\calendars\day.txt"
Test-Path "$HOME\.qlib\qlib_data\cn_data\features"
```

如果都返回 `True`，说明基础数据目录存在。

> 如果没有 Qlib 数据，前端页面仍然能打开，但行情、因子、回测等功能会没有数据或显示不可用。

## 五、启动后端

回到项目根目录，并确认虚拟环境已激活：

```powershell
cd $HOME\Documents\qlib-quant-platform
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

启动成功时，你会看到类似：

```text
Uvicorn running on http://127.0.0.1:8001
Application startup complete.
```

不要关闭这个 PowerShell 窗口。后端需要一直运行。

### 验证后端

新开一个 PowerShell 窗口，执行：

```powershell
curl http://127.0.0.1:8001/health
```

如果返回类似下面内容，说明后端正常：

```json
{"status":"healthy","qlib":"initialized"}
```

如果看到 `degraded` 或错误，通常是 Qlib 数据目录没有准备好。

## 六、启动前端

再新开一个 PowerShell 窗口，进入前端目录：

```powershell
cd $HOME\Documents\qlib-quant-platform\frontend
npm install
npm run dev
```

启动成功时，你会看到类似：

```text
Local: http://localhost:5173/
```

打开浏览器访问：

```text
http://localhost:5173
```

如果页面能打开，说明前端正常。

## 七、第一次打开后检查什么

建议按顺序检查：

1. 打开首页，看页面是否正常加载。
2. 打开“数据管理”，查看 Qlib 数据健康状态。
3. 打开“主题热点”，确认板块数据是否能显示。
4. 打开“模型回测”，先选择较短时间区间测试。
5. 如果要用 AI 功能，再打开“LLM 设置”。

## 八、本地服务器管理 Key 怎么填

本地开发默认可以不设置服务器管理 Key。

如果你没有在启动后端前设置 `API_KEY`，那么页面里的“服务器管理 Key”可以留空。

如果你想模拟线上保护模式，可以这样启动后端：

```powershell
$env:API_KEY="local-dev-key"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

这时页面里的“服务器管理 Key”填写：

```text
local-dev-key
```

注意：服务器管理 Key 只用于保护本地后端操作，不是 LLM Key，也不是行情数据 Key。

## 九、LLM 设置怎么填

如果你不用 AI 策略、新闻分析或智能体辩论，可以先不填。

如果要使用 AI 功能，需要准备自己的 OpenAI-compatible API：

常见示例：

```text
OpenAI Base URL: https://api.openai.com/v1
DeepSeek Base URL: https://api.deepseek.com
通义千问 Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
```

你需要填写：

- API Key
- Base URL
- 快速模型名
- 深度模型名

不要把 API Key 写进代码、README、截图或 GitHub Issue。

## 十、常见问题

### 1. 前端能打开，但提示无法连接后端 API

检查后端是否还在运行：

```powershell
curl http://127.0.0.1:8001/health
```

如果请求失败，说明后端窗口可能关闭了，或者端口不是 `8001`。

### 2. 后端启动失败：No module named xxx

通常是依赖没有安装到当前 Python 环境。请确认虚拟环境已激活，然后重新安装：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### 3. 回测没有结果或很慢

常见原因：

- Qlib 数据不完整
- 回测区间太长
- 股票池选择太大
- 电脑内存或 CPU 不够

建议第一次测试使用较短区间，例如 1 到 3 个月。

### 4. LLM 测试连接超时

常见原因：

- Base URL 填错
- 模型名填错
- API Key 没有权限
- 本地网络访问服务商较慢

线上可用不代表本地网络一定可用。可以先在服务商后台确认 Key 和模型权限。

### 5. 页面显示乱码

请确认文件是 UTF-8 编码，并重新拉取最新代码：

```powershell
git pull
```

如果你手动编辑代码，建议使用 VS Code，并保持 UTF-8。

## 十一、停止服务

停止前端或后端时，在对应 PowerShell 窗口按：

```text
Ctrl + C
```

## 十二、更新项目代码

以后想更新到最新版：

```powershell
cd $HOME\Documents\qlib-quant-platform
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
cd frontend
npm install
```

然后重新启动后端和前端。

## 十三、不要同步到 GitHub 的内容

请不要提交：

- `.env`、真实 API Key、服务器账号、密码、Token
- Qlib 市场数据目录
- SQLite 数据库、缓存、模型文件
- 本地日志、临时文件、下载的 wheel 包

这些内容已经在 `.gitignore` 中默认排除。提交前可以检查：

```powershell
git status --short
```

只提交代码和文档，不提交个人数据。
