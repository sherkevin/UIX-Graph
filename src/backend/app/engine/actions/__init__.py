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
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Callable] = {}


def register(name: str):
    """装饰器：注册 action 函数"""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = fn
        return fn
    return decorator


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
        return {}

    # 从 context 中按 params 声明的 key 取值，作为 kwargs 传入
    kwargs = dict(context)  # 把整个 context 都传进去，函数按需用 **context 接收
    if params:
        for key in params:
            kwargs.setdefault(key, context.get(key))

    try:
        result = fn(**kwargs)
        return result or {}
    except Exception as exc:
        logger.warning("[Action] '%s' 执行异常: %s", name, exc, exc_info=True)
        return {}


# ── 加载内置函数 ────────────────────────────────────────────────────────────
from . import builtin  # noqa: E402, F401
