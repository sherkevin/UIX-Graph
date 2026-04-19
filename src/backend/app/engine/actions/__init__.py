"""
Action Function Registry

决策树 details 中的 action 函数注册表。
每个函数通过 @register("function_name") 装饰器注册后，
可由诊断引擎按名称调用。

使用方式：
    from .actions import call_action
    outputs = call_action("calculate_monthly_mean_Tx", params, context)

新增函数步骤：
    1. 在 actions/ 目录下创建 .py 文件（或在 builtin.py 里追加）
    2. 用 @register("函数名") 装饰
    3. 在本文件末尾 import 该模块

函数签名约定：
    def my_action(param1=None, param2=None, **context) -> dict:
        ...
        return {"output_key": value}

    - 所有参数都有默认值（None），函数永远不会因缺参而崩溃
    - 返回 dict，key 即 results 中的字段名
    - **context 接收当前上下文中的所有其他变量（供函数内部访问）
"""
import logging
import importlib
import pkgutil
import time
from typing import Any, Callable, Dict, Optional

from app.utils import detail_trace

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Callable] = {}
_AUTOLOADED = False


def register(name: str):
    """装饰器：注册 action 函数"""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = fn
        return fn
    return decorator


def has_action(name: str) -> bool:
    """判断 action 是否已注册。"""
    return name in _REGISTRY


def list_actions() -> Dict[str, Callable]:
    """返回 action 注册表副本（只读用途）。"""
    return dict(_REGISTRY)


def _resolve_params(
    params: Optional[Dict[str, Any]],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    解析 rules.details.params：
    - 值为空字符串/None：从 context 同名键取值
    - 值为 "{var_name}"：从 context[var_name] 取值
    - 其他：按字面量常量传入
    """
    if not params:
        return {}

    resolved: Dict[str, Any] = {}
    for key, raw_value in params.items():
        if raw_value is None or raw_value == "":
            resolved[key] = context.get(key)
            continue

        if isinstance(raw_value, str):
            token = raw_value.strip()
            if token.startswith("{") and token.endswith("}") and len(token) > 2:
                var_name = token[1:-1].strip()
                resolved[key] = context.get(var_name)
                continue

        resolved[key] = raw_value
    return resolved


def call_action(
    name: str,
    params: Optional[Dict[str, Any]],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    按名称调用已注册的 action 函数。

    Args:
        name:    action 名称（对应 details[i].action）
        params:  action 的 params 字段（入参声明）
        context: 当前执行上下文（包含 metric_values + 之前 action 的 outputs）

    Returns:
        action 的输出字典；未找到函数或执行出错时返回 {}
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        logger.warning("[Action] '%s' 未注册，跳过（可提供实现后注册）", name)
        detail_trace.warning("action 未注册 | name=%s", name)
        return {}

    # params 优先作为显式入参，context 作为额外上下文透传
    kwargs = dict(context)
    kwargs.update(_resolve_params(params, context))

    t0 = time.perf_counter()
    detail_trace.info(
        "action 调用 | name=%s | params_keys=%s",
        name,
        detail_trace.preview(list((params or {}).keys()), 120),
    )
    try:
        result = fn(**kwargs)
        ms = (time.perf_counter() - t0) * 1000
        detail_trace.info(
            "action 完成 | name=%s | 耗时=%.1fms | output_keys=%s",
            name,
            ms,
            detail_trace.preview(list((result or {}).keys()), 160),
        )
        return result or {}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        detail_trace.error(
            "action 异常 | name=%s | 耗时=%.1fms | error=%s",
            name,
            ms,
            detail_trace.preview(exc, 220),
        )
        logger.warning("[Action] '%s' 执行异常: %s", name, exc, exc_info=True)
        return {}


def _autoload_action_modules() -> None:
    """
    自动加载 actions 包内的所有模块（除 __init__）以完成 @register 注册。
    后续新增 action 文件无需修改本文件。
    """
    global _AUTOLOADED
    if _AUTOLOADED:
        return

    for module_info in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        module_name = module_info.name
        if module_name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module_name}")
    _AUTOLOADED = True


_autoload_action_modules()
