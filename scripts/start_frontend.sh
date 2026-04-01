#!/bin/bash
# ============================================================
# UIX 前端启动脚本（Linux / macOS）
# 使用方式：
#   bash scripts/start_frontend.sh             # 开发模式（npm run dev）
#   bash scripts/start_frontend.sh build       # 生产构建
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/src/frontend"
MODE="${1:-dev}"

echo "================================================"
echo " UIX 前端"
echo " 目录: $FRONTEND_DIR"
echo " 模式: $MODE"
echo "================================================"

cd "$FRONTEND_DIR"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "📦 安装依赖..."
    npm ci
fi

if [ "$MODE" = "build" ]; then
    echo "🔨 生产构建..."
    npm run build
    echo "✅ 构建完成，产物在: $FRONTEND_DIR/dist/"
    echo "   将 dist/ 内容复制到 Nginx 静态目录即可"
else
    echo "🔧 开发服务器启动（http://localhost:3000）..."
    npm run dev
fi
