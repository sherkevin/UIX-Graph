# -*- coding: utf-8 -*-
"""
UIX 一键启动器

两种运行方式：
    python scripts/start.py              # 默认：Tkinter GUI（双击 start_UIX.bat 走这里）
    python scripts/start.py --console    # 无 GUI，所有日志直接打到 stdout
                                          （用在 Tkinter 不可用 / 内网排障 / 远程 ssh 场景）

运行约束（来自用户反馈）：
- 后端 / 前端 / switch_env / pip / npm 的 stdout + stderr 必须**完整**回流到启动器窗口；
- 同时落到 ``logs/launcher-<YYYYmmdd-HHMMSS>.log``，方便用户直接把这个 log 文件给我；
- 任何失败都要打 [ERROR] 大标记 + 完整 traceback，不允许"看上去启动了但其实挂了"。

支持平台：Windows 10/11、macOS、Linux
"""

import argparse
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
from datetime import datetime
from pathlib import Path

# ── UTF-8 输出（Windows CMD/PowerShell 默认 GBK） ──────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

IS_WINDOWS = platform.system() == "Windows"

# ── 路径常量 ─────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
BACKEND  = ROOT / "src" / "backend"
SCRIPTS  = ROOT / "scripts"
ENV_FILE = BACKEND / ".env"
FRONTEND_DIST = ROOT / "src" / "frontend" / "dist" / "index.html"
BACKEND_REQUIREMENTS = BACKEND / "requirements.txt"
LOG_DIR  = ROOT / "logs"

BACKEND_PORT  = 8000
FRONTEND_PORT = 3000

ENVS = ["local", "test", "prod"]


# ── 日志文件 ─────────────────────────────────────────────────────────────────
def _open_log_file() -> tuple[Path, "object"]:
    """返回 (log_path, file_handle)；失败时回退到 stderr。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"launcher-{ts}.log"
    try:
        fh = log_path.open("a", encoding="utf-8", buffering=1)  # 行缓冲
        fh.write(f"==== UIX Launcher started at {datetime.now().isoformat(timespec='seconds')} ====\n")
        fh.write(f"==== Python: {sys.version.splitlines()[0]} ====\n")
        fh.write(f"==== Platform: {platform.platform()} ====\n")
        fh.write(f"==== ROOT: {ROOT} ====\n\n")
        return log_path, fh
    except Exception as exc:  # 极端情况(磁盘只读等)：回退到 stderr，不让启动器自己挂掉
        sys.stderr.write(f"[launcher] WARN: cannot open log file: {exc}\n")
        return log_path, sys.stderr


LOG_PATH, LOG_FILE = _open_log_file()


def _write_log_file(line: str) -> None:
    """所有 GUI / console 输出都同步写一份到日志文件。"""
    try:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        LOG_FILE.write(f"[{ts}] {line}\n")
        if hasattr(LOG_FILE, "flush"):
            LOG_FILE.flush()
    except Exception:
        pass


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


def _minimal_backend_env_text(env: str) -> str:
    """与 switch_env 无关时的最小 .env 主体(不含合入键)。"""
    metric_mode = "mock_allowed" if env == "local" else "real"
    return (
        f"APP_ENV={env}\n"
        f"CORS_ORIGINS=http://localhost:3000,http://localhost:8000\n"
        f"METRIC_SOURCE_MODE={metric_mode}\n"
        f"LOG_LEVEL=INFO\n"
        f"UIX_DETAIL_TRACE=1\n"
    )


def _write_backend_env_preserved_file(env: str) -> tuple:
    """写最小 .env，并合入原文件中需保留的键(如 REJECTED_DETAILED_CACHE)。"""
    try:
        from backend_env_preserve import merge_preserved_from_prev, parse_simple_dotenv

        prev = parse_simple_dotenv(ENV_FILE) if ENV_FILE.exists() else {}
        text = merge_preserved_from_prev(_minimal_backend_env_text(env), prev)
        ENV_FILE.write_text(text, encoding="utf-8")
        return True, None
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
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
        self.root.geometry("760x720")
        self.root.minsize(600, 520)

        # ── 标题 ─────────────────────────────────────────────────────────
        tk.Label(root, text="SXEE-LITHO-RCA", bg=BG, fg=FG,
                 font=BIG).pack(pady=(14, 2))
        tk.Label(root, text="光刻机拒片根因分析系统  —  启动器",
                 bg=BG, fg=FG_DIM, font=UI).pack(pady=(0, 4))
        tk.Label(root, text=f"日志文件: {LOG_PATH}", bg=BG, fg=FG_DIM,
                 font=SMALL).pack(pady=(0, 8))

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

        # ── 日志区（可滚动 + 可扩展） ──────────────────────────────────
        log_frame = tk.Frame(root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(10, 0))

        self.log = tk.Text(log_frame, bg=ACCENT, fg=FG, font=CODE,
                           height=18, bd=0, padx=8, pady=6,
                           state="disabled", relief="flat",
                           wrap="none")
        log_yscroll = tk.Scrollbar(log_frame, orient="vertical",
                                    command=self.log.yview, bg=BG)
        log_xscroll = tk.Scrollbar(log_frame, orient="horizontal",
                                    command=self.log.xview, bg=BG)
        self.log.configure(yscrollcommand=log_yscroll.set,
                           xscrollcommand=log_xscroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_yscroll.grid(row=0, column=1, sticky="ns")
        log_xscroll.grid(row=1, column=0, sticky="ew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        # 错误高亮 tag
        self.log.tag_config("error",  foreground="#ff7675")
        self.log.tag_config("warn",   foreground=YELLOW)
        self.log.tag_config("ok",     foreground=GREEN)
        self.log.tag_config("dim",    foreground=FG_DIM)

        # ── 日志辅助按钮（复制 / 保存 / 打开文件夹 / 清屏） ────────────
        log_btn_f = tk.Frame(root, bg=BG)
        log_btn_f.pack(pady=(4, 0))

        def _mk_btn(text, cmd):
            return tk.Button(log_btn_f, text=text, bg=ACCENT, fg=FG,
                             font=SMALL, bd=0, padx=10, pady=2,
                             activebackground="#2d3436", activeforeground=FG,
                             command=cmd)

        _mk_btn("复制全部",     self._copy_all_log).pack(side="left", padx=4)
        _mk_btn("另存为...",   self._save_log_as).pack(side="left", padx=4)
        _mk_btn("打开日志文件夹", self._open_log_dir).pack(side="left", padx=4)
        _mk_btn("清屏",         self._clear_log).pack(side="left", padx=4)

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
    def _log(self, msg: str, tag: str = ""):
        """同步：写日志文件 + 异步更新 GUI（可选高亮 tag: error/warn/ok/dim）"""
        _write_log_file(msg)

        def _do():
            self.log.configure(state="normal")
            if tag:
                self.log.insert("end", msg + "\n", tag)
            else:
                self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _do)

    def _log_error(self, msg: str):
        """突出显示的错误：分隔线 + ERROR 标记 + 完整保留多行 traceback。"""
        sep = "─" * 60
        self._log(sep, tag="error")
        for i, line in enumerate(str(msg).splitlines() or [""]):
            prefix = "  ✗ [ERROR] " if i == 0 else "             "
            self._log(prefix + line, tag="error")
        self._log(sep, tag="error")

    def _log_warn(self, msg: str):
        for line in str(msg).splitlines() or [""]:
            self._log("  ⚠ [WARN] " + line, tag="warn")

    def _log_ok(self, msg: str):
        self._log("  ✓ " + str(msg), tag="ok")

    # ── 日志区辅助按钮回调 ───────────────────────────────────────────────────
    def _all_log_text(self) -> str:
        try:
            return self.log.get("1.0", "end-1c")
        except Exception:
            return ""

    def _copy_all_log(self):
        text = self._all_log_text()
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            self._log(f"  [INFO] 已复制 {len(text)} 字符到剪贴板", tag="dim")
        except Exception as exc:
            self._log_error(f"复制日志失败: {exc}")

    def _save_log_as(self):
        try:
            initial = LOG_PATH.name
            path = filedialog.asksaveasfilename(
                defaultextension=".log",
                initialfile=initial,
                filetypes=[("Log files", "*.log"), ("All files", "*.*")],
                title="另存日志为...",
            )
            if not path:
                return
            Path(path).write_text(self._all_log_text(), encoding="utf-8")
            self._log(f"  [INFO] 日志已另存为: {path}", tag="dim")
        except Exception as exc:
            self._log_error(f"另存日志失败: {exc}")

    def _open_log_dir(self):
        try:
            target = LOG_PATH.parent
            if IS_WINDOWS:
                os.startfile(str(target))  # noqa: S606
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            self._log_error(f"打开日志目录失败: {exc}")

    def _clear_log(self):
        try:
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            self._log(f"  [INFO] 屏幕日志已清空（文件 {LOG_PATH.name} 仍保留全部历史）", tag="dim")
        except Exception:
            pass

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
            self._log_error(f"后端依赖检查失败:\n{err}")
            self._reset_ui()
            return

        ok, err = self._ensure_frontend_dist()
        if not ok:
            self._log_error(f"前端构建产物检查失败:\n{err}")
            self._reset_ui()
            return

        # [2/5] 切换环境
        self._log(f"  [2/5] 切换环境配置 → {env}...")
        ok, err = self._switch_env(env)
        if not ok:
            self._log_error(f"环境切换失败:\n{err}")
            self._reset_ui()
            return
        self._log_ok(f".env 已更新 (APP_ENV={env})")

        # [3/5] 启动后端
        self._log("  [3/5] 启动后端 (port 8000)...")
        self._set_status(self.be_dot, self.be_lbl, "启动中", self.YELLOW)
        # 先释放端口，等待确认空闲再启动
        if _port_open(BACKEND_PORT):
            self._log("  [INFO] 端口 8000 被占用，正在释放...", tag="dim")
            _free_port(BACKEND_PORT)
            # 最多等 3 秒确认端口释放
            for _ in range(6):
                if not _port_open(BACKEND_PORT):
                    break
                time.sleep(0.5)
        if not self._start_backend():
            self._set_status(self.be_dot, self.be_lbl, "启动失败", self.RED)
            self._log_error("后端进程启动失败，请查看上方 [后端] 日志")
            self._reset_ui()
            return

        # [4/5] 等待后端就绪
        self._log("  [4/5] 等待后端 /health 就绪 (最多 30s)...")
        if not self._wait_backend(timeout=30):
            self._set_status(self.be_dot, self.be_lbl, "无响应", self.RED)
            self._log_error(
                "后端 /health 30 秒内无 200 响应。\n"
                "排障建议：\n"
                "  1) 上方 [后端] 行有没有 traceback / 配置加载失败？\n"
                "  2) 数据库连不上？(local 环境需要 docker-compose up -d)\n"
                "  3) 端口 8000 是否被其它进程占用？\n"
                f"日志文件: {LOG_PATH}"
            )
            self._reset_ui()
            return
        self._set_status(self.be_dot, self.be_lbl, "运行中 :8000", self.GREEN)
        self._log_ok("后端就绪")

        # [5/5] 启动前端
        self._log("  [5/5] 启动前端服务 (port 3000)...")
        self._set_status(self.fe_dot, self.fe_lbl, "启动中", self.YELLOW)
        if _port_open(FRONTEND_PORT):
            self._log("  [INFO] 端口 3000 被占用，正在释放...", tag="dim")
            _free_port(FRONTEND_PORT)
            for _ in range(6):
                if not _port_open(FRONTEND_PORT):
                    break
                time.sleep(0.5)
        self._start_frontend()
        time.sleep(2)

        if _port_open(FRONTEND_PORT):
            self._set_status(self.fe_dot, self.fe_lbl, "运行中 :3000", self.GREEN)
            self._log_ok("前端就绪")
            self._log("─" * 60, tag="ok")
            self._log_ok(f"访问: http://localhost:{FRONTEND_PORT}")
            time.sleep(0.8)
            webbrowser.open(f"http://localhost:{FRONTEND_PORT}")
            self.root.after(0, lambda: (
                self.btn_stop.configure(state="normal"),
                self.btn_browser.configure(state="normal"),
            ))
        else:
            self._set_status(self.fe_dot, self.fe_lbl, "异常", self.RED)
            self._log_error(
                "前端端口 3000 未响应。\n"
                "排障建议：\n"
                "  1) 上方 [前端] 行是否有 Python / Node 报错？\n"
                "  2) src/frontend/dist/index.html 是否存在？\n"
                f"日志文件: {LOG_PATH}"
            )
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
        """运行 switch_env.py <env> 生成 .env；即使 DB 连接检查失败也继续启动。

        失败时**完整保留** stdout + stderr 到日志，并加 [WARN] 醒目提示，
        方便用户把日志复制给我排查。
        """
        switch_script = SCRIPTS / "switch_env.py"
        if not switch_script.exists():
            self._log_warn(f"switch_env.py 不存在 ({switch_script})，使用最小 .env")
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
            for line in _strip_ansi(result.stdout or "").splitlines():
                stripped = line.strip()
                if stripped:
                    self._log(f"    {stripped}", tag="dim")
            for line in _strip_ansi(result.stderr or "").splitlines():
                stripped = line.strip()
                if stripped:
                    self._log(f"    [stderr] {stripped}", tag="warn")
            if result.returncode != 0:
                self._log_warn(
                    f"switch_env.py 返回非零退出码 {result.returncode}（通常是 DB 连接失败），"
                    "将以最小 .env 配置继续启动；如果后端起不来请优先排查数据库可达性。"
                )
                return self._write_env_direct(env)
            return True, None
        except subprocess.TimeoutExpired as e:
            self._log_warn(f"switch_env.py 超时 (30s): {e}，使用最小 .env 继续")
            return self._write_env_direct(env)
        except Exception as e:
            self._log_warn(f"switch_env.py 异常: {e}，使用最小 .env 继续")
            return self._write_env_direct(env)

    def _ensure_backend_runtime(self):
        """确保启动后端所需依赖存在；缺失时尝试自动安装。

        依赖清单从 ``requirements.txt`` 动态解析（不再硬编码），
        添加新依赖只需改 requirements.txt，不用回头改启动器。
        """
        if not BACKEND_REQUIREMENTS.exists():
            return False, f"requirements.txt 不存在: {BACKEND_REQUIREMENTS}"

        required = _parse_requirements(BACKEND_REQUIREMENTS)
        missing = [(pkg, mod) for pkg, mod in required if importlib.util.find_spec(mod) is None]
        if not missing:
            self._log_ok(f"后端依赖已就绪 ({len(required)} 个包)")
            return True, None

        miss_pkgs = ", ".join(p for p, _ in missing)
        self._log(f"  [INFO] 缺少依赖: {miss_pkgs}", tag="dim")
        self._log("  [INFO] 尝试自动安装依赖（pip install -r requirements.txt），请稍候...", tag="dim")
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

        still_missing = [pkg for pkg, mod in required if importlib.util.find_spec(mod) is None]
        if still_missing:
            return False, f"安装后仍缺少依赖: {', '.join(still_missing)}"

        self._log_ok("后端依赖安装完成")
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
        out = _strip_ansi(stdout or "").strip()
        err = _strip_ansi(stderr or "").strip()
        if out:
            parts.append("[stdout]")
            parts.append(out)
        if err:
            parts.append("[stderr]")
            parts.append(err)
        return "\n".join(parts)

    def _write_env_direct(self, env: str):
        """fallback：直接写最小 .env（会保留原 .env 中 REJECTED_DETAILED_CACHE 等键）。"""
        return _write_backend_env_preserved_file(env)

    def _start_backend(self) -> bool:
        try:
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PYTHONUNBUFFERED": "1",
            }
            self._log(
                "  [后端启动参数] "
                f"APP_ENV={env.get('APP_ENV', '?')} "
                f"LOG_LEVEL={env.get('LOG_LEVEL', '?')} "
                f"UIX_DETAIL_TRACE={env.get('UIX_DETAIL_TRACE', '?')} "
                f"METRIC_SOURCE_MODE={env.get('METRIC_SOURCE_MODE', '?')}",
                tag="dim",
            )
            p = subprocess.Popen(
                [PYTHON, "-m", "uvicorn", "app.main:app",
                 "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
                 "--log-level", "info",
                 "--access-log"],
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
            self._log_error(f"启动后端进程失败: {e}")
            return False

    def _start_frontend(self):
        try:
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PYTHONUNBUFFERED": "1",
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
            self._log_error(f"启动前端进程失败: {e}")

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
                    line = _strip_ansi(raw.decode("utf-8", errors="replace").rstrip())
                except Exception:
                    line = repr(raw)
                if line:
                    tag = "error" if ("[ERROR]" in line or "ERROR:" in line or "Traceback" in line) else ""
                    warn = "[WARN]" in line or "WARNING:" in line
                    self._log(f"  {prefix} {line}", tag=tag or ("warn" if warn else ""))
        except Exception:
            pass


# ── 工具 ─────────────────────────────────────────────────────────────────────
import re as _re

# ANSI 转义序列（颜色、光标移动等）；sub-process 输出到非 TTY 时这些转义
# 不会被终端解释，只会作为噪音显示。启动器统一 strip 后再写日志 / GUI。
_ANSI_ESCAPE = _re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(text: str) -> str:
    if not text:
        return text
    return _ANSI_ESCAPE.sub("", text)


# pip 包名 → import 名映射（少数不一致的常见情况）
_IMPORT_NAME_MAP = {
    "python-dotenv": "dotenv",
    "python-multipart": "multipart",
    "clickhouse-connect": "clickhouse_connect",
    "pymysql": "pymysql",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
}


def _parse_requirements(path: Path) -> list[tuple[str, str]]:
    """解析 requirements.txt → [(pkg_name, import_name), ...]

    - 跳过空行、注释、带 ``-r`` 的子文件、URL 形式
    - 去掉版本约束、extras（如 ``uvicorn[standard]==0.24.0``）
    - 不识别的包默认 import 名 = 包名（去掉非字母数字的下划线化）
    """
    out: list[tuple[str, str]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # 去掉 inline 注释
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            # 不支持 url / git+ / 本地 path
            if "://" in line or line.startswith("./") or line.startswith("../"):
                continue
            # 去掉 extras 与版本约束
            m = _re.match(r"^([A-Za-z0-9_.\-]+)", line)
            if not m:
                continue
            pkg = m.group(1).lower()
            import_name = _IMPORT_NAME_MAP.get(pkg, pkg.replace("-", "_"))
            out.append((pkg, import_name))
    except Exception:
        pass
    return out


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


# ─────────────────────────────────────────────────────────────────────────────
# Console 模式（无 GUI 兜底）
# ─────────────────────────────────────────────────────────────────────────────
class ConsoleLauncher:
    """无 GUI 启动器：所有日志直接打 stdout，并同步落到 launcher-*.log

    用途：
        1. Tkinter 库不可用（精简 Python / 容器内）
        2. 内网排障，需要 ssh 远程执行
        3. 想要把整段输出 pipe 到文件分析
    """

    def __init__(self, env: str):
        self.env = env
        self._procs: list[subprocess.Popen] = []
        self._stop_requested = False

    # ── 输出 ─────────────────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        _write_log_file(msg)
        try:
            print(msg, flush=True)
        except Exception:
            sys.stdout.write(msg + "\n")

    def _log_ok(self, msg: str) -> None:
        self._log(f"  [OK] {msg}")

    def _log_warn(self, msg: str) -> None:
        for line in str(msg).splitlines() or [""]:
            self._log(f"  [WARN] {line}")

    def _log_error(self, msg: str) -> None:
        sep = "─" * 60
        self._log(sep)
        for i, line in enumerate(str(msg).splitlines() or [""]):
            prefix = "  [ERROR] " if i == 0 else "           "
            self._log(prefix + line)
        self._log(sep)

    # ── 复用 LauncherApp 的子流程实现（直接调静态方法版） ─────────────────
    def _format_subprocess_output(self, title: str, stdout: str, stderr: str) -> str:
        parts = [f"{title} 执行失败"]
        out = _strip_ansi(stdout or "").strip()
        err = _strip_ansi(stderr or "").strip()
        if out:
            parts.append("[stdout]")
            parts.append(out)
        if err:
            parts.append("[stderr]")
            parts.append(err)
        return "\n".join(parts)

    def _ensure_backend_runtime(self):
        if not BACKEND_REQUIREMENTS.exists():
            return False, f"requirements.txt 不存在: {BACKEND_REQUIREMENTS}"
        required = _parse_requirements(BACKEND_REQUIREMENTS)
        missing = [(pkg, mod) for pkg, mod in required if importlib.util.find_spec(mod) is None]
        if not missing:
            self._log_ok(f"后端依赖已就绪 ({len(required)} 个包)")
            return True, None
        self._log(f"  [INFO] 缺少依赖: {', '.join(p for p, _ in missing)}")
        self._log("  [INFO] pip install -r requirements.txt ...")
        try:
            r = subprocess.run(
                [PYTHON, "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600,
            )
        except Exception as e:
            return False, str(e)
        if r.returncode != 0:
            return False, self._format_subprocess_output("pip install", r.stdout, r.stderr)
        still = [pkg for pkg, mod in required if importlib.util.find_spec(mod) is None]
        if still:
            return False, f"安装后仍缺少: {', '.join(still)}"
        self._log_ok("后端依赖安装完成")
        return True, None

    def _ensure_frontend_dist(self):
        if FRONTEND_DIST.exists():
            self._log_ok("前端 dist 已就绪")
            return True, None
        self._log("  [INFO] 前端 dist 不存在，尝试自动构建...")
        npm = shutil.which("npm")
        node = shutil.which("node")
        if not npm or not node:
            return False, "未找到预编译 dist，且系统未安装 Node.js/npm"
        frontend_dir = ROOT / "src" / "frontend"
        try:
            install = subprocess.run(
                [npm, "install", "--prefer-offline"], cwd=str(frontend_dir),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=900,
            )
            if install.returncode != 0:
                return False, self._format_subprocess_output("npm install", install.stdout, install.stderr)
            build = subprocess.run(
                [npm, "run", "build"], cwd=str(frontend_dir),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=900,
            )
            if build.returncode != 0:
                return False, self._format_subprocess_output("npm run build", build.stdout, build.stderr)
        except Exception as e:
            return False, str(e)
        if not FRONTEND_DIST.exists():
            return False, "前端构建结束后仍未生成 dist/index.html"
        self._log_ok("前端 dist 构建完成")
        return True, None

    def _switch_env(self, env: str):
        switch_script = SCRIPTS / "switch_env.py"
        if not switch_script.exists():
            return self._write_env_direct(env)
        try:
            r = subprocess.run(
                [PYTHON, str(switch_script), env],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            for line in _strip_ansi(r.stdout or "").splitlines():
                if line.strip():
                    self._log(f"    {line.strip()}")
            for line in _strip_ansi(r.stderr or "").splitlines():
                if line.strip():
                    self._log(f"    [stderr] {line.strip()}")
            if r.returncode != 0:
                self._log_warn(f"switch_env.py exit={r.returncode}，使用最小 .env 继续")
                return self._write_env_direct(env)
            return True, None
        except Exception as e:
            self._log_warn(f"switch_env.py 异常: {e}，使用最小 .env 继续")
            return self._write_env_direct(env)

    def _write_env_direct(self, env: str):
        return _write_backend_env_preserved_file(env)

    def _stream(self, p: subprocess.Popen, prefix: str):
        try:
            for raw in p.stdout:
                try:
                    line = _strip_ansi(raw.decode("utf-8", errors="replace").rstrip())
                except Exception:
                    line = repr(raw)
                if line:
                    self._log(f"  {prefix} {line}")
        except Exception:
            pass

    def _spawn(self, args: list[str], cwd: Path, prefix: str) -> subprocess.Popen:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8",
               "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
        p = subprocess.Popen(
            args, cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False,
        )
        self._procs.append(p)
        threading.Thread(target=self._stream, args=(p, prefix), daemon=True).start()
        return p

    def _wait_backend(self, timeout: int = 30) -> bool:
        url = f"http://127.0.0.1:{BACKEND_PORT}/health"
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop_requested:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def stop(self):
        self._stop_requested = True
        for p in self._procs:
            try:
                p.terminate()
            except Exception:
                pass
        self._procs.clear()

    def run(self) -> int:
        self._log("=" * 60)
        self._log(f"  UIX Console Launcher  |  env={self.env.upper()}")
        self._log(f"  日志文件: {LOG_PATH}")
        self._log("=" * 60)

        self._log("  [1/5] 检查运行依赖...")
        ok, err = self._ensure_backend_runtime()
        if not ok:
            self._log_error(f"后端依赖检查失败:\n{err}")
            return 2

        ok, err = self._ensure_frontend_dist()
        if not ok:
            self._log_error(f"前端构建产物检查失败:\n{err}")
            return 2

        self._log(f"  [2/5] 切换环境配置 → {self.env}...")
        ok, err = self._switch_env(self.env)
        if not ok:
            self._log_error(f"环境切换失败:\n{err}")
            return 2
        self._log_ok(f".env 已更新 (APP_ENV={self.env})")

        self._log("  [3/5] 启动后端 (port 8000)...")
        if _port_open(BACKEND_PORT):
            self._log("  [INFO] 端口 8000 被占用，正在释放...")
            _free_port(BACKEND_PORT)
            for _ in range(6):
                if not _port_open(BACKEND_PORT):
                    break
                time.sleep(0.5)
        try:
            self._spawn(
                [PYTHON, "-m", "uvicorn", "app.main:app",
                 "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
                 "--log-level", "info", "--access-log"],
                BACKEND, "[后端]",
            )
        except Exception as e:
            self._log_error(f"后端进程启动失败: {e}")
            return 3

        self._log("  [4/5] 等待后端 /health 就绪 (最多 30s)...")
        if not self._wait_backend(timeout=30):
            self._log_error(
                "后端 /health 30 秒内无 200 响应。\n"
                "排障建议：\n"
                "  1) 上方 [后端] 行有没有 traceback / 配置加载失败？\n"
                "  2) 数据库连不上？(local 环境需要 docker-compose up -d)\n"
                "  3) 端口 8000 是否被其它进程占用？\n"
                f"日志文件: {LOG_PATH}"
            )
            self.stop()
            return 4
        self._log_ok("后端就绪")

        self._log("  [5/5] 启动前端服务 (port 3000)...")
        if _port_open(FRONTEND_PORT):
            self._log("  [INFO] 端口 3000 被占用，正在释放...")
            _free_port(FRONTEND_PORT)
            for _ in range(6):
                if not _port_open(FRONTEND_PORT):
                    break
                time.sleep(0.5)
        try:
            self._spawn(
                [PYTHON, str(SCRIPTS / "serve_frontend.py"), str(FRONTEND_PORT)],
                ROOT, "[前端]",
            )
        except Exception as e:
            self._log_error(f"前端进程启动失败: {e}")
            self.stop()
            return 5

        time.sleep(2)
        if not _port_open(FRONTEND_PORT):
            self._log_error(
                "前端端口 3000 未响应。\n"
                "排障建议：\n"
                "  1) 上方 [前端] 行是否有 Python 报错？\n"
                "  2) src/frontend/dist/index.html 是否存在？\n"
                f"日志文件: {LOG_PATH}"
            )
            self.stop()
            return 6

        self._log_ok("前端就绪")
        self._log("─" * 60)
        self._log_ok(f"访问: http://localhost:{FRONTEND_PORT}")
        self._log(f"  [INFO] 按 Ctrl+C 停止全部服务")
        self._log(f"  [INFO] 完整日志: {LOG_PATH}")
        try:
            while True:
                time.sleep(1)
                # 检查任一子进程是否意外退出
                for p in list(self._procs):
                    if p.poll() is not None:
                        self._log_warn(f"子进程 PID={p.pid} 意外退出，exit_code={p.returncode}")
                        self._procs.remove(p)
                if not self._procs:
                    self._log_error("所有子进程都已退出")
                    return 7
        except KeyboardInterrupt:
            self._log("\n  [INFO] 收到 Ctrl+C，正在停止服务...")
            self.stop()
            self._log_ok("已停止")
            return 0


# ── 主入口 ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="UIX 一键启动器（默认 GUI；--console 走纯命令行）",
    )
    parser.add_argument(
        "--console", action="store_true",
        help="不启动 Tkinter GUI，所有日志直接打印到终端（适合 Tk 不可用 / ssh 排障 / 流水线）",
    )
    parser.add_argument(
        "--env", choices=ENVS, default=None,
        help="console 模式下的运行环境；不传则用 .env 当前值（默认 local）",
    )
    args = parser.parse_args()

    # ── Console 模式 ──
    if args.console or not HAS_TK:
        if not HAS_TK and not args.console:
            print("[launcher] Tkinter 不可用，自动降级到 console 模式", flush=True)
        env = args.env or _current_env()
        rc = ConsoleLauncher(env=env).run()
        sys.exit(rc)

    # ── GUI 模式 ──
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
