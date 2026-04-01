# -*- coding: utf-8 -*-
"""
前端静态资源服务 + API 反代
无需 Nginx，纯 Python 实现同源部署。

监听 :3000，规则：
  /api/* 和 /health  → 转发到后端 http://127.0.0.1:8000
  其他路径           → 从 src/frontend/dist/ 服务静态文件
  未找到文件         → 返回 index.html（React Router SPA 支持）
"""

import sys
import os
import io
import logging
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger("serve_frontend")

# 后端地址
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000

# 静态文件目录（相对于本文件的位置计算）
_HERE = Path(__file__).resolve().parent
DIST_DIR = _HERE.parent / "src" / "frontend" / "dist"


class UIXHandler(SimpleHTTPRequestHandler):
    """同源代理处理器：/api/* 转发后端，其余服务静态文件"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    # ── 日志静默（避免控制台刷屏） ────────────────────────────────
    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        pass

    # ── 代理判断 ─────────────────────────────────────────────────
    def _is_proxy_path(self):
        path = self.path.split("?")[0]
        return path.startswith("/api/") or path == "/api" or path == "/health"

    # ── GET / POST / OPTIONS ──────────────────────────────────────
    def do_GET(self):
        if self._is_proxy_path():
            self._proxy("GET")
        else:
            self._serve_static()

    def do_POST(self):
        if self._is_proxy_path():
            self._proxy("POST")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── 安全写入（客户端断开时静默忽略） ──────────────────────────
    def _safe_write(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return False
        except OSError:
            return False

    # ── 静态文件服务（SPA 回退到 index.html） ───────────────────────
    def _serve_static(self):
        path = self.path.split("?")[0]
        file_path = DIST_DIR / path.lstrip("/")
        if file_path.is_file():
            try:
                super().do_GET()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass
            return
        # 不是文件 → SPA 回退
        index_path = DIST_DIR / "index.html"
        if not index_path.exists():
            self.send_error(503, "Frontend not built. Run: npm run build in src/frontend/")
            return
        content = index_path.read_bytes()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self._safe_write(content)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    # ── API 反代 ─────────────────────────────────────────────────
    def _proxy(self, method):
        target = f"http://{BACKEND_HOST}:{BACKEND_PORT}{self.path}"
        headers = {}
        for key in ["content-type", "accept", "authorization"]:
            val = self.headers.get(key)
            if val:
                headers[key] = val

        body = None
        if method == "POST":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length) if length else b""

        try:
            req = urllib.request.Request(target, data=body, headers=headers, method=method)
            # timeout 提高到 120s，应对大时间范围 metadata 查询
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
            try:
                self.send_response(resp.status)
                ct = resp.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self._safe_write(resp_body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass  # 客户端取消请求，正常忽略
        except urllib.error.HTTPError as e:
            err_body = e.read()
            try:
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self._safe_write(err_body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass  # 客户端提前断开，忽略
        except Exception as e:
            msg = f'{{"detail":"前端代理错误：{e}"}}'.encode("utf-8")
            try:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self._safe_write(msg)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass


def run(port=3000):
    if not DIST_DIR.exists():
        print(f"[ERROR] 前端构建目录不存在: {DIST_DIR}", flush=True)
        print("[ERROR] 请先运行: cd src/frontend && npm run build", flush=True)
        sys.exit(1)

    # 确保 stdout/stderr 是 UTF-8（Windows 兼容）
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # ThreadingHTTPServer：每个请求独立线程，避免大查询阻塞其他请求
    server = ThreadingHTTPServer(("0.0.0.0", port), UIXHandler)

    # 覆盖错误处理：客户端断开（WinError 10053/10054）静默忽略，不打印堆栈
    _original_handle_error = server.handle_error
    def _quiet_handle_error(request, client_address):
        import traceback, sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        if isinstance(exc, OSError) and getattr(exc, 'winerror', None) in (10053, 10054):
            return
        _original_handle_error(request, client_address)
    server.handle_error = _quiet_handle_error

    print(f"[Frontend] 服务启动 http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    run(port)
