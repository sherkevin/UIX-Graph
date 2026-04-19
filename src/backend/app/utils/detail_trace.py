# -*- coding: utf-8 -*-
"""
拒片详情接口专用排障日志（写入标准日志，启动器可捕获 uvicorn 子进程输出）。

前缀统一为 [详情排障]，便于在内网日志中 grep。
"""
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("uix.detail")


def enabled() -> bool:
    return os.environ.get("UIX_DETAIL_TRACE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def preview(val: Any, max_len: int = 200) -> str:
    """截断 repr，避免把巨型 JSON 打进日志。"""
    try:
        s = repr(val)
    except Exception:
        s = f"<{type(val).__name__}>"
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _emit_stdout(message: str) -> None:
    """双写到 stdout，避免 uvicorn/logger 配置差异导致启动器看不到日志。"""
    try:
        print(message, file=sys.stdout, flush=True)
    except Exception:
        pass


def info(msg: str, *args: Any) -> None:
    if not enabled():
        return
    rendered = ("[详情排障] " + msg) % args if args else "[详情排障] " + msg
    logger.info(rendered)
    _emit_stdout(rendered)


def warning(msg: str, *args: Any) -> None:
    if not enabled():
        return
    rendered = ("[详情排障] " + msg) % args if args else "[详情排障] " + msg
    logger.warning(rendered)
    _emit_stdout(rendered)


def error(msg: str, *args: Any) -> None:
    if not enabled():
        return
    rendered = ("[详情排障] " + msg) % args if args else "[详情排障] " + msg
    logger.error(rendered)
    _emit_stdout(rendered)


@contextmanager
def span(name: str, **fields: Any) -> Iterator[None]:
    if not enabled():
        yield
        return
    suffix = ""
    if fields:
        parts = []
        for k, v in fields.items():
            try:
                parts.append(f"{k}={preview(v)}")
            except Exception:
                parts.append(f"{k}=?")
        suffix = " | " + " ".join(parts)
    t0 = time.perf_counter()
    start_msg = f"[详情排障] >> 开始 {name}{suffix}"
    logger.info(start_msg)
    _emit_stdout(start_msg)
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        end_msg = f"[详情排障] << 结束 {name} | 耗时={ms:.1f} ms"
        logger.info(end_msg)
        _emit_stdout(end_msg)
