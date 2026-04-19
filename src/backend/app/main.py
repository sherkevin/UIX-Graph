# -*- coding: utf-8 -*-
import os
import sys
import logging
import traceback
import json
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
from app.handler import (
    reject_errors, ontology, knowledge,
    diagnosis, visualization, propagation, full_graph, entity
)

# ── 日志配置 ──────────────────────────────────────────────────────────────────
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
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

app = FastAPI(
    title="SMEE-LITHO-RCA API",
    description="光刻机拒片根因分析系统 API",
    version="1.0.0"
)

# ── CORS 配置（由环境变量 CORS_ORIGINS 控制，逗号分隔多个来源） ───────────────
_cors_env = os.environ.get("CORS_ORIGINS", "")
if _cors_env.strip():
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    # 默认：本地开发白名单
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
    ]

logger.info("CORS allow_origins: %s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──────────────────────────────────────────────────────────────────
# 主线(stage3/stage4):拒片故障管理始终注册
app.include_router(reject_errors.router, prefix="/api/v1/reject-errors", tags=["拒片故障管理"])

# 老路由(图谱 / 本体 / 传播):前端 src/frontend/ 已不再调用,但内网可能存在
# 第三方客户端、Postman 集合或运维脚本仍在使用。默认 LEGACY_ROUTES_ENABLED=true
# 保持向后兼容;内网部署若已确认无人调用,可在 .env 设 LEGACY_ROUTES_ENABLED=false
# 关闭它们,30 天观察访问日志,确认无 404 后再在后续 PR 中物理删除 handler/core/测试。
_legacy_enabled = os.environ.get("LEGACY_ROUTES_ENABLED", "true").strip().lower() not in (
    "0", "false", "no", "off",
)
logger.info("Legacy routes enabled: %s", _legacy_enabled)
if _legacy_enabled:
    app.include_router(ontology.router,      prefix="/api/ontology",      tags=["本体管理"])
    app.include_router(knowledge.router,     prefix="/api/knowledge",     tags=["知识库"])
    app.include_router(diagnosis.router,     prefix="/api/diagnosis",     tags=["诊断"])
    app.include_router(visualization.router, prefix="/api/visualization", tags=["可视化"])
    app.include_router(propagation.router,   prefix="/api/propagation",   tags=["传播分析"])
    app.include_router(entity.router,        prefix="/api/entity",        tags=["实体"])
    app.include_router(full_graph.router,    prefix="/api/graph",         tags=["全图"])


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
    return {"message": "SMEE-LITHO-RCA API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "appEnv": os.environ.get("APP_ENV", "local"),
        "frontendApiUrl": _load_frontend_api_url(),
    }
