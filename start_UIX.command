#!/bin/bash
# ============================================================
#  UIX 一键启动器 (macOS / Linux 入口)
#  SXEE-LITHO-RCA 光刻机拒片根因分析系统
#
#  用法:
#    ./start_UIX.command                 默认 Tk GUI
#    ./start_UIX.command --console       无 GUI, 全部日志打到当前终端
#    ./start_UIX.command --console --env local
# ============================================================

cd "$(dirname "$0")"

export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

echo "============================================"
echo "  UIX 启动器 — SXEE-LITHO-RCA"
echo "============================================"

# ── 找 Python 3 ──
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
    echo "[ERROR] 未找到 Python 3，请安装 Python 3.9+"
    read -p "按回车退出..."
    exit 1
fi

echo "[INFO] 使用 Python: $($PYTHON --version 2>&1)"

# ── 直接把所有参数转给 start.py ──
$PYTHON scripts/start.py "$@"
EXIT_CODE=$?

# console 模式下保留终端
if echo "$*" | grep -q -- "--console"; then
    echo
    echo "============================================"
    echo "[launcher] 进程已退出 (exit=$EXIT_CODE), 按回车关闭"
    echo "============================================"
    read -r
fi

exit $EXIT_CODE
