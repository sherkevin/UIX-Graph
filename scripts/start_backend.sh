#!/bin/bash
# ============================================================
# UIX 后端启动脚本（Linux / macOS）
# 使用方式：
#   bash scripts/start_backend.sh               # 开发模式（带 --reload）
#   bash scripts/start_backend.sh production    # 生产模式
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/src/backend"

echo "================================================"
echo " UIX 后端启动"
echo " 后端目录: $BACKEND_DIR"
echo "================================================"

# 检查 .env 文件
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "⚠️  未找到 src/backend/.env，正在使用默认 local 环境..."
    cd "$PROJECT_ROOT"
    python scripts/switch_env.py local || echo "switch_env.py 执行失败，将使用硬编码默认值"
fi

# 读取端口（默认 8000）
PORT=${PORT:-8000}
HOST=${HOST:-0.0.0.0}
MODE="${1:-development}"

cd "$BACKEND_DIR"

# 检查端口是否占用
if lsof -i :$PORT -t >/dev/null 2>&1; then
    echo "⚠️  端口 $PORT 已被占用，请先终止占用进程或修改 PORT 环境变量"
    exit 1
fi

# 激活虚拟环境（若存在）
if [ -d "$BACKEND_DIR/.venv" ]; then
    source "$BACKEND_DIR/.venv/bin/activate"
    echo "✅ 已激活虚拟环境: $BACKEND_DIR/.venv"
elif [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "✅ 已激活虚拟环境: $PROJECT_ROOT/.venv"
fi

if [ "$MODE" = "production" ]; then
    echo "🚀 生产模式启动 (${HOST}:${PORT})..."
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 2
else
    echo "🔧 开发模式启动 (${HOST}:${PORT}, --reload)..."
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
fi
