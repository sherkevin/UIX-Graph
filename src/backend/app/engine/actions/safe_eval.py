# -*- coding: utf-8 -*-
"""
safe_eval action — 让专家在配置里直接写算术/比较/布尔表达式,无需新 Python 代码。

设计动机:
    项目目标是「专家只改配置文档就能扩展功能」。但当专家想加一个新的中间量计算
    (例如 `tx_plus_ty = Tx + Ty`)时,过去必须在 src/backend/app/engine/actions/
    里写一个新的 Python 函数 + @register。这违反了配置驱动原则。
    
    safe_eval action 让以下配置直接生效:
    
        {
          "id": 50,
          "details": [{
            "action": "safe_eval",
            "description": "计算 Tx²+Ty² 作为综合偏差",
            "params": {
              "expr": "Tx ** 2 + Ty ** 2",
              "out": "tx_ty_sum_sq"
            },
            "results": {"tx_ty_sum_sq": ""}
          }],
          "next": [{"target": "60", "condition": "{tx_ty_sum_sq} < 800"}]
        }

安全性:
    用 Python ast 模块解析表达式,**白名单**校验 AST 节点。任何不在白名单的语法
    都拒绝。这意味着以下都不可能:
    - import / open / exec / eval / __builtins__ / 属性访问 (.foo)
    - 函数调用(连 abs/min/max 都禁,要用必须显式列入下面的 SAFE_FUNCS)
    - 列表/字典/集合字面量构造
    - lambda / 推导式 / 生成器
    - 赋值 / del / global / nonlocal
    
    如此即便专家写错或恶意配置,也只会算出 None/抛 ValueError,不会执行任意代码。

允许的语法:
    - 数字字面量与 True/False/None
    - 字符串字面量(供 == 比较用,不可拼接)
    - 变量名 → 从 context 读取(metric_id 或 detail.results 写入的 key)
    - 算术: + - * / // % **
    - 一元: - +
    - 比较: < <= > >= == != (含链式 a < b < c)
    - 布尔: and / or / not
    - 三目: x if cond else y
    - 安全函数: abs / min / max / round / int / float
"""
from __future__ import annotations

import ast
import logging
import math
import operator as op
from typing import Any, Callable, Dict, Optional

from . import register

logger = logging.getLogger(__name__)


# 白名单:允许的二元算术
_BIN_OPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}

# 白名单:允许的一元
_UNARY_OPS: Dict[type, Callable[[Any], Any]] = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: op.not_,
}

# 白名单:允许的比较
_CMP_OPS: Dict[type, Callable[[Any, Any], bool]] = {
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
}

# 白名单:允许的布尔(短路求值)
_BOOL_OPS = {ast.And, ast.Or}

# 白名单:允许的内置函数
_SAFE_FUNCS: Dict[str, Callable[..., Any]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
    # 数学常用
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,  # 注意:这里作为函数调用,但 _eval 中作为 Name 单独处理
}

# 数学常量(作为名字访问)
_SAFE_CONSTANTS: Dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
    "nan": math.nan,
    "True": True,
    "False": False,
    "None": None,
}


class SafeEvalError(ValueError):
    """专家配置写错或表达式不安全时抛出。"""


def _eval_node(node: ast.AST, ctx: Dict[str, Any]) -> Any:
    """递归 walk AST,只对白名单节点求值。"""
    # 字面量(数字/字符串/True/False/None)
    if isinstance(node, ast.Constant):
        return node.value

    # 变量名 → 优先 ctx,然后 SAFE_CONSTANTS
    if isinstance(node, ast.Name):
        name = node.id
        if name in ctx:
            return ctx[name]
        if name in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name]
        raise SafeEvalError(
            f"safe_eval: 表达式引用了未知变量 {name!r}"
            f";应是 metric_id / details.results 写入的 key 之一,或 {sorted(_SAFE_CONSTANTS)}"
        )

    # 二元算术
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise SafeEvalError(f"safe_eval: 不允许的二元运算 {op_type.__name__}")
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        return _BIN_OPS[op_type](left, right)

    # 一元
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise SafeEvalError(f"safe_eval: 不允许的一元运算 {op_type.__name__}")
        operand = _eval_node(node.operand, ctx)
        return _UNARY_OPS[op_type](operand)

    # 比较(含链式 a < b < c)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        for cmp_op, comparator in zip(node.ops, node.comparators):
            op_type = type(cmp_op)
            if op_type not in _CMP_OPS:
                raise SafeEvalError(f"safe_eval: 不允许的比较运算 {op_type.__name__}")
            right = _eval_node(comparator, ctx)
            if not _CMP_OPS[op_type](left, right):
                return False
            left = right
        return True

    # 布尔运算(短路)
    if isinstance(node, ast.BoolOp):
        op_type = type(node.op)
        if op_type not in _BOOL_OPS:
            raise SafeEvalError(f"safe_eval: 不允许的布尔运算 {op_type.__name__}")
        if op_type is ast.And:
            value: Any = True
            for v in node.values:
                value = _eval_node(v, ctx)
                if not value:
                    return value
            return value
        if op_type is ast.Or:
            value = False
            for v in node.values:
                value = _eval_node(v, ctx)
                if value:
                    return value
            return value

    # 三目 x if cond else y
    if isinstance(node, ast.IfExp):
        cond = _eval_node(node.test, ctx)
        return _eval_node(node.body if cond else node.orelse, ctx)

    # 函数调用(只允许 _SAFE_FUNCS 中的)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise SafeEvalError(
                "safe_eval: 函数调用只允许直接通过名字调用安全函数"
                "(禁止属性访问 / 高阶函数)"
            )
        fn_name = node.func.id
        if fn_name not in _SAFE_FUNCS:
            raise SafeEvalError(
                f"safe_eval: 不允许的函数 {fn_name!r}"
                f";白名单: {sorted(set(_SAFE_FUNCS) - set(_SAFE_CONSTANTS))}"
            )
        if node.keywords:
            raise SafeEvalError(
                "safe_eval: 函数调用不支持关键字参数(只允许位置参数)"
            )
        args = [_eval_node(a, ctx) for a in node.args]
        return _SAFE_FUNCS[fn_name](*args)

    # 不允许的节点
    raise SafeEvalError(
        f"safe_eval: 不允许的语法节点 {type(node).__name__}"
        f"(常见禁用项:属性访问 .foo、订阅 a[i]、列表/字典字面量、推导式、lambda)"
    )


def safe_arithmetic_eval(expr: str, ctx: Dict[str, Any]) -> Any:
    """
    在 ctx 上下文中安全求值 expr,只允许白名单语法。
    
    Args:
        expr: 表达式字符串(如 "Tx ** 2 + Ty ** 2"、"Mwx_0 > 1.0001 and Tx > 20")
        ctx:  变量上下文,通常是 diagnosis_engine 当前 context
    
    Returns:
        求值结果(数字 / 布尔 / None / 字符串)
    
    Raises:
        SafeEvalError: 语法不允许或引用未知变量
        SyntaxError:   表达式本身语法错(由 ast.parse 抛出)
    """
    if not isinstance(expr, str) or not expr.strip():
        raise SafeEvalError("safe_eval: expr 必须是非空字符串")
    tree = ast.parse(expr, mode="eval")  # 这里 SyntaxError 自然透传
    return _eval_node(tree.body, ctx)


@register("safe_eval")
def safe_eval_action(
    expr: Optional[str] = None,
    out: Optional[str] = None,
    **ctx: Any,
) -> Dict[str, Any]:
    """
    诊断引擎可调用的 safe_eval action。
    
    config 用法示例:
    
        {
          "action": "safe_eval",
          "description": "计算 Tx 与 Ty 的平方和",
          "params": {
            "expr": "Tx ** 2 + Ty ** 2",
            "out": "tx_ty_sum_sq"
          },
          "results": {"tx_ty_sum_sq": ""}
        }
    
    params 约定:
        expr: 必填,表达式字符串(变量名直接写,不用 {} 包裹——因为 params
              binding 已经把上下文 ctx 全部透传给我们)
        out:  必填,结果写入 context 的 key 名;通常等于 details.results 中
              声明的 key
    """
    if not expr:
        logger.warning("safe_eval: 缺少 params.expr,跳过")
        return {}
    if not out:
        logger.warning("safe_eval: 缺少 params.out(结果写入哪个 key),跳过")
        return {}
    
    try:
        value = safe_arithmetic_eval(expr, ctx)
    except SafeEvalError as exc:
        logger.warning("safe_eval 求值失败 expr=%r: %s", expr, exc)
        return {}
    except SyntaxError as exc:
        logger.warning("safe_eval 表达式语法错误 expr=%r: %s", expr, exc.msg)
        return {}
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        logger.warning("safe_eval 运行时错误 expr=%r: %s: %s", expr, type(exc).__name__, exc)
        return {}
    
    return {out: value}
