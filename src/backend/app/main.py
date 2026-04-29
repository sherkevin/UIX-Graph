# -*- coding: utf-8 -*-
import os
import sys
import logging
import traceback
import json
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pathlib import Path

# ── 确保 stdout/stderr UTF-8（Windows 兼容） ─────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 加载 src/backend/.env（由 scripts/switch_env.py 生成或手动复制 .env.example）
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.handler import reject_errors
from app.utils import detail_trace

# ── 日志配置 ──────────────────────────────────────────────────────────────────
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


def _load_frontend_api_url() -> str:
    """读取当前 APP_ENV 下的 frontend_api_url（用于健康检查与部署排障）。"""
    app_env = os.environ.get("APP_ENV", "local")
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "connections.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        env_cfg = cfg.get(app_env) or cfg.get("local") or {}
        return str(env_cfg.get("frontend_api_url") or "")
    except Exception as exc:
        logger.warning("读取 frontend_api_url 失败: %s", exc)
        return ""


# ── CORS 配置（须在 lifespan 日志前就绪）──────────────────────────────────────
_cors_env = os.environ.get("CORS_ORIGINS", "")
if _cors_env.strip():
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
    ]

logger.info("CORS allow_origins: %s", _cors_origins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """替代已弃用的 @app.on_event('startup')（FastAPI / Starlette 推荐写法）。"""
    detail_trace.info(
        "应用启动 | APP_ENV=%s | LOG_LEVEL=%s | UIX_DETAIL_TRACE=%s | CORS=%s",
        os.environ.get("APP_ENV", "local"),
        _log_level,
        os.environ.get("UIX_DETAIL_TRACE", "1"),
        _cors_env or "default_local",
    )
    yield


app = FastAPI(
    title="SXEE-LITHO-RCA API",
    description="光刻机拒片根因分析系统 API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    query_text = str(request.url.query or "")
    detail_trace.info(
        "HTTP 请求进入 | %s %s | query=%s",
        request.method,
        request.url.path,
        detail_trace.preview(query_text, 300),
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        detail_trace.error(
            "HTTP 请求异常 | %s %s | 耗时=%.1f ms | error=%s",
            request.method,
            request.url.path,
            (time.perf_counter() - t0) * 1000,
            detail_trace.preview(exc, 300),
        )
        raise

    detail_trace.info(
        "HTTP 请求完成 | %s %s | status=%s | 耗时=%.1f ms",
        request.method,
        request.url.path,
        getattr(response, "status_code", "?"),
        (time.perf_counter() - t0) * 1000,
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──────────────────────────────────────────────────────────────────
# 主线:拒片故障管理
app.include_router(reject_errors.router, prefix="/api/v1/reject-errors", tags=["拒片故障管理"])


# ── 全局错误 Handler（所有报错实时打印到日志/启动窗口） ───────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 请求参数校验失败 — 详细打印到日志"""
    body = None
    try:
        body = await request.body()
        body = body.decode("utf-8", errors="replace")
    except Exception:
        pass
    logger.error(
        "请求校验失败 [422] %s %s\n  body: %s\n  errors: %s",
        request.method, request.url, body, exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 4xx/5xx — 打印到日志"""
    if exc.status_code >= 500:
        logger.error("HTTP 错误 [%s] %s %s — %s", exc.status_code, request.method, request.url, exc.detail)
    else:
        logger.warning("HTTP 错误 [%s] %s %s — %s", exc.status_code, request.method, request.url, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未捕获异常 — 完整堆栈打印到日志"""
    logger.error(
        "未捕获异常 [500] %s %s\n%s",
        request.method, request.url, traceback.format_exc()
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {type(exc).__name__}: {exc}"},
    )


@app.get("/")
async def root():
    return {"message": "SXEE-LITHO-RCA API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "appEnv": os.environ.get("APP_ENV", "local"),
        "frontendApiUrl": _load_frontend_api_url(),
    }
