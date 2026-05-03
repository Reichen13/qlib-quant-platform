#!/bin/bash
# Qlib 分析看板启动脚本
cd /home/jason/projects/qlib-workspace
echo "启动 Qlib 分析看板..."
echo "本地访问: http://localhost:8501"
echo "外网访问: http://192.227.182.104:8501 (需要先部署到VPS)"
echo ""
./venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
