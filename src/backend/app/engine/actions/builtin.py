"""
内置 Action 函数（桩实现）

说明：
  - 当前所有函数均为桩实现（passthrough），等待真实算法替换。
  - 真实实现到位后，只需修改对应函数体，引擎无需改动。
  - 新增函数：直接在此文件追加，或新建 .py 文件并在 __init__.py 末尾 import。

桩实现策略：
  - calculate_monthly_mean_*  → 直接返回原始指标值作为 mean（不做月均值）
  - build_*_model             → no-op（模型输出已由 ClickHouse 预计算存入 DB）
  - determine_model_type      → no-op（model_type 由 branch 的 set 字段注入）
  - increment_counter         → 计数器累加
"""
from typing import Any, Optional
from . import register


# ── 月均值计算（桩：直接透传原始值）─────────────────────────────────────────

@register("calculate_monthly_mean_Tx")
def calculate_monthly_mean_Tx(Tx: Optional[float] = None, **ctx) -> dict:
    return {"mean_Tx": float(Tx) if Tx is not None else 0.0}


@register("calculate_monthly_mean_Ty")
def calculate_monthly_mean_Ty(Ty: Optional[float] = None, **ctx) -> dict:
    return {"mean_Ty": float(Ty) if Ty is not None else 0.0}


@register("calculate_monthly_mean_Rw")
def calculate_monthly_mean_Rw(Rw: Optional[float] = None, **ctx) -> dict:
    return {"mean_Rw": float(Rw) if Rw is not None else 0.0}


# ── 建模步骤（桩：no-op，输出值已在 ClickHouse 中）──────────────────────────

@register("build_88um_model")
def build_88um_model(**ctx) -> dict:
    return {}


@register("build_8um_model")
def build_8um_model(**ctx) -> dict:
    return {}


@register("build_model")
def build_model(**ctx) -> dict:
    return {}


# ── 模型类型判断（桩：no-op，model_type 由 branch set 注入）────────────────

@register("determine_model_type")
def determine_model_type(**ctx) -> dict:
    return {}


# ── 计数器（用于并行路径的累计计数）────────────────────────────────────────

@register("increment_counter")
def increment_counter(
    counter_name: str = "normal_count",
    increment: Any = 1,
    **ctx,
) -> dict:
    current = ctx.get(counter_name, 0) or 0
    try:
        return {counter_name: current + int(increment)}
    except (TypeError, ValueError):
        return {counter_name: current}


# ── 通用透传（未知 action 的兜底）────────────────────────────────────────────
# 如果规则文件里出现新的 action 名，可在此注册通用 passthrough 避免警告

@register("passthrough")
def passthrough(**ctx) -> dict:
    return {}
