#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Qlib 量化平台 - 一键部署脚本 (腾讯云)
# 架构: Docker 后端 + 系统 Nginx 托管前端
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
QLIB_DATA_PATH="/home/ubuntu/.qlib/qlib_data"

cd "$PROJECT_DIR"

# ============================================================
# Step 1: Install Docker
# ============================================================
log "检查 Docker..."
if ! command -v docker &>/dev/null; then
    log "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker ubuntu
    log "Docker 安装完成 (需要重新登录以生效 docker 组权限)"
else
    log "Docker 已安装: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    error "需要 Docker Compose v2"
fi

# ============================================================
# Step 2: Swap (已有则跳过)
# ============================================================
if swapon --show | grep -q "/swapfile"; then
    log "Swap 已启用 (2GB)"
else
    log "创建 2GB swap..."
    sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
    log "Swap 创建完成"
fi

# ============================================================
# Step 3: Build and start Docker backend
# ============================================================
log "构建后端 Docker 镜像 (约 3-5 分钟)..."
docker compose build 2>&1 | tail -10

log "启动后端容器..."
docker compose up -d

log "等待后端健康检查..."
for i in $(seq 1 24); do
    if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
        log "后端启动成功！"
        break
    fi
    if [ $i -eq 24 ]; then
        warn "后端启动超时，查看日志:"
        docker compose logs --tail 30
        error "启动失败"
    fi
    sleep 5
    printf "."
done
echo ""

# ============================================================
# Step 4: Build frontend and deploy static files
# ============================================================
log "构建前端..."
cd "$PROJECT_DIR/frontend"

# 安装 Node.js (如果没有)
if ! command -v node &>/dev/null; then
    log "安装 Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

npm install --legacy-peer-deps 2>&1 | tail -5
npm run build 2>&1 | tail -5

# 部署到 Nginx 目录
log "部署前端静态文件..."
sudo mkdir -p /var/www/quant
sudo cp -r dist/* /var/www/quant/
sudo chown -R www-data:www-data /var/www/quant

cd "$PROJECT_DIR"

# ============================================================
# Step 5: Configure Nginx
# ============================================================
log "配置 Nginx..."
sudo cp nginx-quant.conf /etc/nginx/sites-available/quant
sudo ln -sf /etc/nginx/sites-available/quant /etc/nginx/sites-enabled/quant

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
log "Nginx 配置完成"

# ============================================================
# Step 6: Verify
# ============================================================
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================="
log "部署成功！"
echo "=========================================="
echo ""
echo "  前端访问:  http://${SERVER_IP}:9090"
echo "  API 文档:  http://${SERVER_IP}:9090/docs"
echo "  健康检查:  http://${SERVER_IP}:9090/health"
echo ""
echo "常用命令:"
echo "  docker compose logs -f          # 查看后端日志"
echo "  docker compose restart           # 重启后端"
echo "  docker compose down              # 停止后端"
echo "  docker stats --no-stream         # 查看资源占用"
echo ""
log "内存状态:"
free -h
