#!/bin/bash
# 停止 Qlib 量化平台服务

echo "🛑 停止 Qlib 量化平台..."

pkill -f "uvicorn main:app" && echo "   ✅ FastAPI 后端已停止" || echo "   ⚠️  FastAPI 后端未运行"
pkill -f "vite" && echo "   ✅ React 前端已停止" || echo "   ⚠️  React 前端未运行"

echo "✨ 所有服务已停止"
