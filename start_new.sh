#!/bin/bash
# Qlib 量化平台启动脚本
# 启动 FastAPI 后端和 React 前端

PROJECT_DIR="/home/jason/projects/qlib-workspace"
cd "$PROJECT_DIR"

echo "🚀 启动 Qlib 量化平台..."

# 检查并停止旧进程
echo "📋 检查现有进程..."
pkill -f "uvicorn main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 2

# 启动 FastAPI 后端
echo "🔧 启动 FastAPI 后端 (端口 8000)..."
cd backend
source ../venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/fastapi.log 2>&1 &
BACKEND_PID=$!
echo "   后端 PID: $BACKEND_PID"

# 等待后端启动
sleep 5

# 检查后端状态
if curl -s http://localhost:8000/ > /dev/null; then
    echo "   ✅ FastAPI 后端启动成功"
else
    echo "   ❌ FastAPI 后端启动失败，查看日志: /tmp/fastapi.log"
    cat /tmp/fastapi.log
fi

# 启动前端
echo "🎨 启动 React 前端 (端口 5173)..."
cd frontend
nohup npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   前端 PID: $FRONTEND_PID"

# 等待前端启动
sleep 5

# 检查前端状态
if curl -s http://localhost:5173 > /dev/null; then
    echo "   ✅ React 前端启动成功"
else
    echo "   ⚠️  正在启动前端..."
fi

cd "$PROJECT_DIR"

echo ""
echo "✨ 服务启动完成！"
echo ""
echo "📊 前端地址: http://localhost:5173"
echo "🔧 后端 API: http://localhost:8000"
echo "📚 API 文档: http://localhost:8000/docs"
echo ""
echo "📝 查看日志:"
echo "   后端: tail -f /tmp/fastapi.log"
echo "   前端: tail -f /tmp/frontend.log"
echo ""
echo "🛑 停止服务:"
echo "   ./stop.sh"
echo ""
echo "💡 提示: Streamlit 备用版本仍然可用: ./start_streamlit.sh"
