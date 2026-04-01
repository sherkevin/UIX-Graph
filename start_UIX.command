#!/bin/bash
# ============================================================
#  UIX 一键启动器（macOS 双击运行）
#  SXEE-LITHO-RCA 光刻机拒片根因分析系统
# ============================================================

# 切换到脚本所在目录（项目根目录）
cd "$(dirname "$0")"

# ── 确保终端 UTF-8 ──────────────────────────────────────────
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

echo "============================================"
echo "  UIX 启动器 — SXEE-LITHO-RCA"
echo "============================================"

# ── 查找 Python ──────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        VER=$($cmd -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        if [ "$VER" = "3" ]; then
            PYTHON=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[错误] 未找到 Python 3，请安装 Python 3.9+"
    read -p "按回车退出..."
    exit 1
fi

echo "[信息] 使用 Python: $($PYTHON --version 2>&1)"

# ── 检查依赖 ─────────────────────────────────────────────────
$PYTHON -c "import fastapi" &>/dev/null
if [ $? -ne 0 ]; then
    echo "[信息] 首次运行，安装后端依赖..."
    $PYTHON -m pip install -r src/backend/requirements.txt -q
    if [ $? -ne 0 ]; then
        echo "[错误] 依赖安装失败，请检查网络"
        read -p "按回车退出..."
        exit 1
    fi
fi

# ── 检查前端构建产物 ─────────────────────────────────────────
if [ ! -f "src/frontend/dist/index.html" ]; then
    echo "[信息] 前端尚未构建，开始构建..."
    if ! command -v node &>/dev/null; then
        echo "[错误] 未找到 Node.js 且前端未构建"
        echo "  请先运行: cd src/frontend && npm run build"
        read -p "按回车退出..."
        exit 1
    fi
    cd src/frontend
    npm install --prefer-offline -q
    npx vite build
    cd ../..
fi

# ── 启动 GUI ─────────────────────────────────────────────────
echo "[信息] 正在启动 UIX 启动器..."
$PYTHON scripts/start.py
