#!/bin/bash
# 启动 Streamlit 备用版本

PROJECT_DIR="/home/jason/projects/qlib-workspace"
cd "$PROJECT_DIR"

echo "🚀 启动 Streamlit 备用版本..."

# 检查并停止旧进程
pkill -f "streamlit run" 2>/dev/null
sleep 2

# 设置环境变量
export STREAMLIT_SERVER_HEADLESS=true

# 启动 Streamlit
nohup ./venv/bin/streamlit run app_streamlit.py.bak \
    --server.port 8501 \
    --server.address 0.0.0.0 > /tmp/streamlit.log 2>&1 &

sleep 5

if curl -s http://localhost:8501 > /dev/null; then
    echo "✅ Streamlit 版本启动成功"
    echo "📊 访问地址: http://localhost:8501"
else
    echo "❌ Streamlit 版本启动失败"
    cat /tmp/streamlit.log
fi
