# -*- coding: utf-8 -*-
"""
UIX 一键启动器（Tkinter GUI）
支持：Windows 10/11、macOS、Linux
"""

import sys
import os
import platform
import subprocess
import threading
import time
import webbrowser
import socket
import shutil
import importlib.util
import urllib.request
import urllib.error
from pathlib import Path

# ── UTF-8 输出（Windows CMD 兼容） ───────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

IS_WINDOWS = platform.system() == "Windows"

# ── 路径常量 ─────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
BACKEND  = ROOT / "src" / "backend"
SCRIPTS  = ROOT / "scripts"
ENV_FILE = BACKEND / ".env"
FRONTEND_DIST = ROOT / "src" / "frontend" / "dist" / "index.html"
BACKEND_REQUIREMENTS = BACKEND / "requirements.txt"

BACKEND_PORT  = 8000
FRONTEND_PORT = 3000

ENVS = ["local", "test", "prod"]


# ── Python 可执行路径 ─────────────────────────────────────────────────────────
def _find_python() -> str:
    exe = sys.executable
    if IS_WINDOWS:
        p = Path(exe)
        if p.name.lower() == "pythonw.exe":
            candidate = p.parent / "python.exe"
            if candidate.exists():
                return str(candidate)
    return exe


PYTHON = _find_python()


# ── Windows 子进程不弹黑窗 ────────────────────────────────────────────────────
def _no_window() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ── 读取当前 .env 里的 APP_ENV ────────────────────────────────────────────────
def _current_env() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("APP_ENV="):
                val = line.split("=", 1)[1].strip()
                if val in ENVS:
                    return val
    return "local"


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk
    HAS_TK = True
except ImportError:
    HAS_TK = False


class LauncherApp:
    def __init__(self, root: "tk.Tk"):
        self.root = root
        self.root.title("UIX Launcher  —  SXEE-LITHO-RCA")
        self.root.resizable(False, False)

        # ── 颜色 ─────────────────────────────────────────────────────────
        BG     = "#1a1a2e"
        CARD   = "#16213e"
        ACCENT = "#0f3460"
        GREEN  = "#00b894"
        RED    = "#d63031"
        YELLOW = "#fdcb6e"
        FG     = "#dfe6e9"
        FG_DIM = "#636e72"
        SEL_BG = "#2d3436"

        self.GREEN  = GREEN
        self.RED    = RED
        self.YELLOW = YELLOW
        self.FG_DIM = FG_DIM
        self.FG     = FG
        self.ACCENT = ACCENT

        # ── 字体（Windows 优先用 Microsoft YaHei UI 支持中文） ──────────
        if IS_WINDOWS:
            UI   = ("Microsoft YaHei UI", 9)
            BOLD = ("Microsoft YaHei UI", 10, "bold")
            CODE = ("Consolas", 8)
            BIG  = ("Microsoft YaHei UI", 14, "bold")
            SMALL= ("Microsoft YaHei UI", 8)
        else:
            UI   = ("Arial", 9)
            BOLD = ("Arial", 10, "bold")
            CODE = ("Courier", 8)
            BIG  = ("Arial", 14, "bold")
            SMALL= ("Arial", 8)

        self.root.configure(bg=BG)
        self.root.geometry("520x520")

        # ── 标题 ─────────────────────────────────────────────────────────
        tk.Label(root, text="SXEE-LITHO-RCA", bg=BG, fg=FG,
                 font=BIG).pack(pady=(16, 2))
        tk.Label(root, text="光刻机拒片根因分析系统  —  启动器",
                 bg=BG, fg=FG_DIM, font=UI).pack(pady=(0, 10))

        # ── 环境选择卡片 ──────────────────────────────────────────────────
        env_card = tk.Frame(root, bg=CARD, padx=20, pady=12)
        env_card.pack(fill="x", padx=24)

        tk.Label(env_card, text="运行环境", bg=CARD, fg=FG,
                 font=BOLD).pack(anchor="w", pady=(0, 6))

        btn_row = tk.Frame(env_card, bg=CARD)
        btn_row.pack(fill="x")

        self._env_var = tk.StringVar(value=_current_env())
        self._env_btns = {}

        env_info = {
            "local": ("本地 / Local", "测试用 Docker MySQL"),
            "test":  ("测试 / Test",  "内网测试数据库"),
            "prod":  ("生产 / Prod",  "内网正式数据库"),
        }

        for key, (label, tip) in env_info.items():
            col = tk.Frame(btn_row, bg=CARD)
            col.pack(side="left", expand=True, fill="x", padx=4)

            rb = tk.Radiobutton(
                col, text=label, variable=self._env_var, value=key,
                bg=CARD, fg=FG, selectcolor=SEL_BG,
                activebackground=CARD, activeforeground=FG,
                font=UI, indicatoron=False,
                relief="flat", bd=0, pady=6, padx=10,
                width=12,
                highlightthickness=0,
                command=self._on_env_change,
            )
            rb.pack(fill="x")
            tk.Label(col, text=tip, bg=CARD, fg=FG_DIM,
                     font=SMALL).pack()
            self._env_btns[key] = rb

        self._refresh_env_buttons()

        # ── 状态卡片 ──────────────────────────────────────────────────────
        status_card = tk.Frame(root, bg=CARD, padx=20, pady=10)
        status_card.pack(fill="x", padx=24, pady=(8, 0))

        def _row(label):
            row = tk.Frame(status_card, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=CARD, fg=FG_DIM,
                     font=UI, width=6, anchor="w").pack(side="left")
            dot = tk.Label(row, text="●", bg=CARD, fg=FG_DIM, font=UI)
            dot.pack(side="left", padx=(4, 6))
            lbl = tk.Label(row, text="等待", bg=CARD, fg=FG_DIM,
                           font=UI, anchor="w")
            lbl.pack(side="left")
            return dot, lbl

        self.be_dot, self.be_lbl = _row("后端")
        self.fe_dot, self.fe_lbl = _row("前端")

        # ── 日志区 ───────────────────────────────────────────────────────
        self.log = tk.Text(root, bg=ACCENT, fg=FG, font=CODE,
                           height=10, bd=0, padx=8, pady=6,
                           state="disabled", relief="flat")
        self.log.pack(fill="both", padx=24, pady=(10, 0))

        # ── 按钮区 ───────────────────────────────────────────────────────
        btn_f = tk.Frame(root, bg=BG)
        btn_f.pack(pady=12)

        self.btn_start = tk.Button(
            btn_f, text="▶  启动", bg=GREEN, fg="#fff",
            font=BOLD, width=10, bd=0, pady=6,
            activebackground="#00cec9", activeforeground="#fff",
            command=self.on_start)
        self.btn_start.pack(side="left", padx=6)

        self.btn_stop = tk.Button(
            btn_f, text="■  停止", bg=RED, fg="#fff",
            font=BOLD, width=10, bd=0, pady=6,
            activebackground="#ff7675", activeforeground="#fff",
            command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

        self.btn_browser = tk.Button(
            btn_f, text="打开浏览器", bg=ACCENT, fg=FG,
            font=BOLD, width=12, bd=0, pady=6,
            activebackground="#2d3436", activeforeground=FG,
            command=lambda: webbrowser.open(f"http://localhost:{FRONTEND_PORT}"),
            state="disabled")
        self.btn_browser.pack(side="left", padx=6)

        self._procs: list = []
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 环境切换 ─────────────────────────────────────────────────────────────
    def _on_env_change(self):
        self._refresh_env_buttons()

    def _refresh_env_buttons(self):
        cur = self._env_var.get()
        colors = {"local": "#00b894", "test": "#fdcb6e", "prod": "#d63031"}
        for key, rb in self._env_btns.items():
            if key == cur:
                rb.configure(bg=colors[key], fg="#fff", relief="solid", bd=1)
            else:
                rb.configure(bg="#16213e", fg=self.FG_DIM, relief="flat", bd=0)

    def _selected_env(self) -> str:
        return self._env_var.get()

    # ── 日志 ─────────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, dot, lbl, text: str, color: str):
        def _do():
            dot.configure(fg=color)
            lbl.configure(text=text, fg=color)
        self.root.after(0, _do)

    # ── 启动 ─────────────────────────────────────────────────────────────────
    def on_start(self):
        self.root.after(0, lambda: self.btn_start.configure(state="disabled"))
        # 禁用环境选择
        for rb in self._env_btns.values():
            self.root.after(0, lambda r=rb: r.configure(state="disabled"))
        self._log("─" * 44)
        self._log(f"  环境: {self._selected_env().upper()}  |  UIX 启动中...")
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        env = self._selected_env()

        # [1/5] 运行前检查
        self._log("  [1/5] 检查运行依赖...")
        ok, err = self._ensure_backend_runtime()
        if not ok:
            self._log(f"  ✗ 后端依赖检查失败: {err}")
            self._reset_ui()
            return

        ok, err = self._ensure_frontend_dist()
        if not ok:
            self._log(f"  ✗ 前端构建产物检查失败: {err}")
            self._reset_ui()
            return

        # [2/5] 切换环境
        self._log(f"  [2/5] 切换环境配置 → {env}...")
        ok, err = self._switch_env(env)
        if not ok:
            self._log(f"  ✗ 环境切换失败: {err}")
            self._reset_ui()
            return
        self._log(f"  ✓ .env 已更新 (APP_ENV={env})")

        # [3/5] 启动后端
        self._log("  [3/5] 启动后端 (port 8000)...")
        self._set_status(self.be_dot, self.be_lbl, "启动中", self.YELLOW)
        # 先释放端口，等待确认空闲再启动
        if _port_open(BACKEND_PORT):
            self._log("  [INFO] 端口 8000 被占用，正在释放...")
            _free_port(BACKEND_PORT)
            # 最多等 3 秒确认端口释放
            for _ in range(6):
                if not _port_open(BACKEND_PORT):
                    break
                time.sleep(0.5)
        if not self._start_backend():
            self._set_status(self.be_dot, self.be_lbl, "启动失败", self.RED)
            self._reset_ui()
            return

        # [4/5] 等待后端就绪
        self._log("  [4/5] 等待后端就绪...")
        if not self._wait_backend(timeout=30):
            self._log("  ✗ 后端无响应，请查看日志")
            self._set_status(self.be_dot, self.be_lbl, "无响应", self.RED)
            self._reset_ui()
            return
        self._set_status(self.be_dot, self.be_lbl, "运行中 :8000", self.GREEN)
        self._log("  ✓ 后端就绪")

        # [5/5] 启动前端
        self._log("  [5/5] 启动前端服务 (port 3000)...")
        self._set_status(self.fe_dot, self.fe_lbl, "启动中", self.YELLOW)
        if _port_open(FRONTEND_PORT):
            self._log("  [INFO] 端口 3000 被占用，正在释放...")
            _free_port(FRONTEND_PORT)
            for _ in range(6):
                if not _port_open(FRONTEND_PORT):
                    break
                time.sleep(0.5)
        self._start_frontend()
        time.sleep(2)

        if _port_open(FRONTEND_PORT):
            self._set_status(self.fe_dot, self.fe_lbl, "运行中 :3000", self.GREEN)
            self._log("  ✓ 前端就绪")
            self._log("─" * 44)
            self._log(f"  访问: http://localhost:{FRONTEND_PORT}")
            time.sleep(0.8)
            webbrowser.open(f"http://localhost:{FRONTEND_PORT}")
            self.root.after(0, lambda: (
                self.btn_stop.configure(state="normal"),
                self.btn_browser.configure(state="normal"),
            ))
        else:
            self._set_status(self.fe_dot, self.fe_lbl, "异常", self.RED)
            self._log("  ✗ 前端端口未响应，请查看日志")
            self._reset_ui()

    def _reset_ui(self):
        self.root.after(0, lambda: self.btn_start.configure(state="normal"))
        for rb in self._env_btns.values():
            self.root.after(0, lambda r=rb: r.configure(state="normal"))

    # ── 停止 ─────────────────────────────────────────────────────────────────
    def on_stop(self):
        self._log("  正在停止所有服务...")
        for p in self._procs:
            try:
                p.terminate()
            except Exception:
                pass
        self._procs.clear()
        self._set_status(self.be_dot, self.be_lbl, "已停止", self.FG_DIM)
        self._set_status(self.fe_dot, self.fe_lbl, "已停止", self.FG_DIM)
        self._log("  服务已全部停止")
        self.root.after(0, lambda: (
            self.btn_stop.configure(state="disabled"),
            self.btn_browser.configure(state="disabled"),
            self.btn_start.configure(state="normal"),
        ))
        for rb in self._env_btns.values():
            self.root.after(0, lambda r=rb: r.configure(state="normal"))

    def _on_close(self):
        self.on_stop()
        self.root.destroy()

    # ── 内部方法 ─────────────────────────────────────────────────────────────
    def _switch_env(self, env: str):
        """运行 switch_env.py <env> 生成 .env；即使 DB 连接检查失败也继续启动"""
        switch_script = SCRIPTS / "switch_env.py"
        if not switch_script.exists():
            return self._write_env_direct(env)
        try:
            result = subprocess.run(
                [PYTHON, str(switch_script), env],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                **_no_window(),
            )
            # 不论成败，把 switch_env.py 的有效输出行打印到 log（过滤掉纯空行）
            for line in (result.stdout or "").splitlines():
                stripped = line.strip()
                if stripped:
                    self._log(f"    {stripped}")
            if result.returncode != 0:
                # switch_env.py 失败（通常是 DB 连接失败）：降级写最小 .env，继续启动
                self._log("  [WARN] switch_env.py 返回错误（见上方日志），将以最小配置继续启动")
                return self._write_env_direct(env)
            return True, None
        except Exception as e:
            return self._write_env_direct(env)

    def _ensure_backend_runtime(self):
        """确保启动后端所需依赖存在；缺失时尝试自动安装。"""
        required_modules = {
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
            "pydantic": "pydantic",
            "sqlalchemy": "sqlalchemy",
            "dotenv": "python-dotenv",
            "pymysql": "pymysql",
            "clickhouse_connect": "clickhouse-connect",
        }
        missing = [pkg for mod, pkg in required_modules.items() if importlib.util.find_spec(mod) is None]
        if not missing:
            self._log("  ✓ 后端依赖已就绪")
            return True, None

        self._log(f"  [INFO] 缺少依赖: {', '.join(missing)}")
        if not BACKEND_REQUIREMENTS.exists():
            return False, f"requirements.txt 不存在: {BACKEND_REQUIREMENTS}"

        self._log("  [INFO] 尝试自动安装依赖，请稍候...")
        try:
            result = subprocess.run(
                [PYTHON, "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                **_no_window(),
            )
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, self._format_subprocess_output("pip install", result.stdout, result.stderr)

        still_missing = [pkg for mod, pkg in required_modules.items() if importlib.util.find_spec(mod) is None]
        if still_missing:
            return False, f"安装后仍缺少依赖: {', '.join(still_missing)}"

        self._log("  ✓ 后端依赖安装完成")
        return True, None

    def _ensure_frontend_dist(self):
        """确保前端 dist 存在；不存在则尝试自动构建。"""
        if FRONTEND_DIST.exists():
            self._log("  ✓ 前端 dist 已就绪")
            return True, None

        self._log("  [INFO] 前端 dist 不存在，尝试自动构建...")
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            return False, "未找到预编译 dist，且系统未安装 Node.js/npm"

        frontend_dir = ROOT / "src" / "frontend"
        package_json = frontend_dir / "package.json"
        if not package_json.exists():
            return False, f"缺少 package.json: {package_json}"

        try:
            install = subprocess.run(
                [npm, "install", "--prefer-offline"],
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                **_no_window(),
            )
            if install.returncode != 0:
                return False, self._format_subprocess_output("npm install", install.stdout, install.stderr)

            build = subprocess.run(
                [npm, "run", "build"],
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                **_no_window(),
            )
            if build.returncode != 0:
                return False, self._format_subprocess_output("npm run build", build.stdout, build.stderr)
        except Exception as e:
            return False, str(e)

        if not FRONTEND_DIST.exists():
            return False, "前端构建结束后仍未生成 dist/index.html"

        self._log("  ✓ 前端 dist 构建完成")
        return True, None

    def _format_subprocess_output(self, title: str, stdout: str, stderr: str) -> str:
        """完整保留子进程 stdout/stderr，避免启动窗口里只看到截断错误。"""
        parts = [f"{title} 执行失败"]
        out = (stdout or "").strip()
        err = (stderr or "").strip()
        if out:
            parts.append("[stdout]")
            parts.append(out)
        if err:
            parts.append("[stderr]")
            parts.append(err)
        return "\n".join(parts)

    def _write_env_direct(self, env: str):
        """fallback：直接写最小 .env"""
        try:
            metric_mode = "mock_allowed" if env == "local" else "real"
            content = (
                f"APP_ENV={env}\n"
                f"CORS_ORIGINS=http://localhost:3000,http://localhost:8000\n"
                f"METRIC_SOURCE_MODE={metric_mode}\n"
                f"LOG_LEVEL=INFO\n"
            )
            ENV_FILE.write_text(content, encoding="utf-8")
            return True, None
        except Exception as e:
            return False, str(e)

    def _start_backend(self) -> bool:
        try:
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
            p = subprocess.Popen(
                [PYTHON, "-m", "uvicorn", "app.main:app",
                 "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
                cwd=str(BACKEND),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                **_no_window(),
            )
            self._procs.append(p)
            threading.Thread(
                target=self._stream_log, args=(p, "[后端]"), daemon=True
            ).start()
            return True
        except Exception as e:
            self._log(f"  ✗ 启动后端失败: {e}")
            return False

    def _start_frontend(self):
        try:
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
            p = subprocess.Popen(
                [PYTHON, str(SCRIPTS / "serve_frontend.py"), str(FRONTEND_PORT)],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                **_no_window(),
            )
            self._procs.append(p)
            threading.Thread(
                target=self._stream_log, args=(p, "[前端]"), daemon=True
            ).start()
        except Exception as e:
            self._log(f"  ✗ 启动前端失败: {e}")

    def _wait_backend(self, timeout: int = 30) -> bool:
        url = f"http://127.0.0.1:{BACKEND_PORT}/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _stream_log(self, proc: subprocess.Popen, prefix: str):
        try:
            for raw in proc.stdout:
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    line = repr(raw)
                if line:
                    self._log(f"  {prefix} {line}")
        except Exception:
            pass


# ── 工具 ─────────────────────────────────────────────────────────────────────
def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _free_port(port: int) -> None:
    """强制释放端口：找到占用该端口的进程并杀掉（Windows / Unix）"""
    if platform.system() == "Windows":
        # 方法 1：netstat + findstr（精确匹配 ":PORT " 避免误伤）
        pids = set()
        try:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port} "',
                shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5
            )
            for line in result.stdout.decode("gbk", errors="replace").splitlines():
                parts = line.strip().split()
                if parts:
                    last = parts[-1]
                    if last.isdigit() and int(last) > 0:
                        pids.add(last)
        except Exception:
            pass

        # 方法 2：PowerShell（备用，更可靠）
        if not pids:
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue)"
                     f".OwningProcess | Sort-Object -Unique"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=5
                )
                for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.isdigit() and int(line) > 0:
                        pids.add(line)
            except Exception:
                pass

        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=5
                )
            except Exception:
                pass

        if pids:
            time.sleep(1.5)  # 给 Windows 足够时间释放端口
    else:
        # Unix/macOS: lsof
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5
            )
            for pid in result.stdout.decode().strip().split():
                if pid.isdigit():
                    subprocess.run(["kill", "-9", pid],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=5)
            time.sleep(0.5)
        except Exception:
            pass


# ── 主入口 ───────────────────────────────────────────────────────────────────
def main():
    if not HAS_TK:
        print("Tkinter not available. Please reinstall Python with Tk support.",
              flush=True)
        sys.exit(1)

    root = tk.Tk()
    LauncherApp(root)

    try:
        icon = ROOT / "deploy" / "icon.ico"
        if icon.exists():
            root.iconbitmap(str(icon))
    except Exception:
        pass

    root.mainloop()


if __name__ == "__main__":
    main()
