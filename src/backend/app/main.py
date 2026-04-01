# -*- coding: utf-8 -*-
import os
import sys
import logging
import traceback
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
app.include_router(reject_errors.router, prefix="/api/v1/reject-errors", tags=["拒片故障管理"])
app.include_router(ontology.router,      prefix="/api/ontology",          tags=["本体管理"])
app.include_router(knowledge.router,     prefix="/api/knowledge",          tags=["知识库"])
app.include_router(diagnosis.router,     prefix="/api/diagnosis",          tags=["诊断"])
app.include_router(visualization.router, prefix="/api/visualization",      tags=["可视化"])
app.include_router(propagation.router,   prefix="/api/propagation",        tags=["传播分析"])
app.include_router(entity.router,        prefix="/api/entity",             tags=["实体"])
app.include_router(full_graph.router,    prefix="/api/graph",              tags=["全图"])


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
    return {"status": "healthy"}
