"""
内置 Action 函数
"""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import register


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_float_list(value: Any) -> List[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                continue
        return result
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # 兼容 JSON 数组与逗号分隔文本
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return _to_float_list(parsed)
            except json.JSONDecodeError:
                pass
        if "," in text:
            return _to_float_list([part.strip() for part in text.split(",")])
        try:
            return [float(text)]
        except ValueError:
            return []
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _mean(values: Sequence[float], fallback: float) -> float:
    if not values:
        return fallback
    return sum(values) / len(values)


def _first_numeric(values: Any, fallback: float = 0.0) -> float:
    numeric_values = _to_float_list(values)
    if numeric_values:
        return numeric_values[0]
    return _to_float(values, fallback)


def _query_monthly_mean(column_name: str, current_value: Optional[float], **ctx) -> float:
    """
    查询某指标在当前基准时间前 30 天的均值。
    过滤口径：equipment + chuck_id + 时间窗口。
    """
    equipment = ctx.get("equipment")
    chuck_id = ctx.get("chuck_id")
    reference_time = ctx.get("reference_time")

    if not equipment or chuck_id is None:
        return _to_float(current_value, 0.0)

    if isinstance(reference_time, str):
        try:
            reference_time = datetime.fromisoformat(reference_time)
        except ValueError:
            reference_time = None
    if not isinstance(reference_time, datetime):
        reference_time = datetime.now()

    time_start = reference_time - timedelta(days=30)

    try:
        from app.ods.datacenter_ods import LoBatchEquipmentPerformance, SessionLocal

        db = SessionLocal()
        try:
            col = getattr(LoBatchEquipmentPerformance, column_name)
            rows = (
                db.query(col)
                .filter(
                    LoBatchEquipmentPerformance.equipment == equipment,
                    LoBatchEquipmentPerformance.chuck_id == str(chuck_id),
                    LoBatchEquipmentPerformance.wafer_product_start_time >= time_start,
                    LoBatchEquipmentPerformance.wafer_product_start_time <= reference_time,
                )
                .all()
            )
            values = [_to_float(item[0], None) for item in rows if item and item[0] is not None]
            values = [v for v in values if v is not None]
            return _mean(values, _to_float(current_value, 0.0))
        finally:
            db.close()
    except Exception:
        return _to_float(current_value, 0.0)


def _solve_b_wa_4param_pinv(
    mark_scan: List[Tuple[float, float]],
    mark_data: List[Tuple[float, float]],
    msx: float,
    msy: float,
    e_wsx: float,
    e_wsy: float,
) -> Tuple[float, float, float, float]:
    """
    COWA 双点标记 wafer 四参数线性解，与 MATLAB 一致::

        % 化简：M*cos(R)=1+dM, M*sin(R)=R
        a1 = [1 0 mark_data(i,1) -mark_data(i,2); 0 1 mark_data(i,2) mark_data(i,1); ...]
        b1 = [mark_scan(i,1)*Msx - e_wsx - mark_data(i,1); ...]
        B_wa_4par = pinv(a1) * b1

    返回 (BB_Cwx1, BB_Cwy1, BB_Mw1, BB_Rw1)，与 MATLAB B_wa_4par(1:4) 同序、同量纲（米 / 弧度）。
    使用 ``numpy.linalg.pinv`` 对应 MATLAB ``pinv``。
    """
    rows: List[List[float]] = []
    rhs: List[float] = []
    for i in range(min(len(mark_scan), len(mark_data))):
        md_x, md_y = mark_data[i]
        ms_x, ms_y = mark_scan[i]
        rows.append([1.0, 0.0, md_x, -md_y])
        rhs.append(ms_x * msx - e_wsx - md_x)
        rows.append([0.0, 1.0, md_y, md_x])
        rhs.append(ms_y * msy - e_wsy - md_y)
    if not rows:
        return 0.0, 0.0, 0.0, 0.0
    a_mat = np.asarray(rows, dtype=np.float64)
    b_vec = np.asarray(rhs, dtype=np.float64).reshape(-1, 1)
    x = np.linalg.pinv(a_mat) @ b_vec
    cwx, cwy, mw, rw = float(x[0, 0]), float(x[1, 0]), float(x[2, 0]), float(x[3, 0])
    return cwx, cwy, mw, rw


def _run_model_once(
    mark_scan: List[Tuple[float, float]],
    mark_data: List[Tuple[float, float]],
    msx: float,
    msy: float,
    e_wsx: float,
    e_wsy: float,
    s_x: float,
    s_y: float,
    d_x: float,
    d_y: float,
) -> Dict[str, float]:
    cwx, cwy, mw, rw = _solve_b_wa_4param_pinv(
        mark_scan, mark_data, msx, msy, e_wsx, e_wsy
    )
    # Tx/Ty/Mw/Rw 与 MATLAB 一致：*(1e6) 得到 nm 与 ppm/µrad 量级展示
    tx = (cwx - s_x - d_x) * 1e6
    ty = (cwy - s_y - d_y) * 1e6
    mw_ppm = mw * 1e6
    rw_urad = rw * 1e6
    return {"output_Tx": tx, "output_Ty": ty, "output_Mw": mw_ppm, "output_Rw": rw_urad}


def _build_model(amplitude_um: float, **ctx) -> Dict[str, Any]:
    ws_x = _to_float_list(ctx.get("ws_pos_x"))
    ws_y = _to_float_list(ctx.get("ws_pos_y"))
    mk_x = _to_float_list(ctx.get("mark_pos_x"))
    mk_y = _to_float_list(ctx.get("mark_pos_y"))

    if len(ws_x) < 2:
        ws_x = ws_x if ws_x else [_to_float(ctx.get("ws_pos_x"), 0.0)]
        ws_x = (ws_x + ws_x)[:2]
    if len(ws_y) < 2:
        ws_y = ws_y if ws_y else [_to_float(ctx.get("ws_pos_y"), 0.0)]
        ws_y = (ws_y + ws_y)[:2]
    if len(mk_x) < 2:
        mk_x = mk_x if mk_x else [_to_float(ctx.get("mark_pos_x"), 0.0)]
        mk_x = (mk_x + mk_x)[:2]
    if len(mk_y) < 2:
        mk_y = mk_y if mk_y else [_to_float(ctx.get("mark_pos_y"), 0.0)]
        mk_y = (mk_y + mk_y)[:2]

    mark_scan = [(ws_x[i], ws_y[i]) for i in range(2)]
    mark_data = [(mk_x[i], mk_y[i]) for i in range(2)]

    msx = _first_numeric(ctx.get("Msx"), 1.0)
    msy = _first_numeric(ctx.get("Msy"), 1.0)
    e_wsx = _first_numeric(ctx.get("e_ws_x"), _first_numeric(ctx.get("e_wsx"), 0.0))
    e_wsy = _first_numeric(ctx.get("e_ws_y"), _first_numeric(ctx.get("e_wsy"), 0.0))
    s_x = _first_numeric(ctx.get("Sx"), _first_numeric(ctx.get("S_x"), 0.0))
    s_y = _first_numeric(ctx.get("Sy"), _first_numeric(ctx.get("S_y"), 0.0))
    d_x = _first_numeric(ctx.get("D_x"), 0.0)
    d_y = _first_numeric(ctx.get("D_y"), 0.0)

    ops = [
        (0, "x", +amplitude_um),
        (0, "x", -amplitude_um),
        (0, "y", +amplitude_um),
        (0, "y", -amplitude_um),
        (1, "x", +amplitude_um),
        (1, "x", -amplitude_um),
        (1, "y", +amplitude_um),
        (1, "y", -amplitude_um),
    ]

    last = {
        "output_Tx": _first_numeric(ctx.get("Tx"), 0.0),
        "output_Ty": _first_numeric(ctx.get("Ty"), 0.0),
        "output_Mw": 9999.0,
        "output_Rw": _first_numeric(ctx.get("Rw"), 0.0),
    }
    history: List[Dict[str, float]] = []
    attempts = 0
    for mark_idx, axis, delta_um in ops:
        attempts += 1
        perturbed = [list(p) for p in mark_scan]
        perturbed[mark_idx][0 if axis == "x" else 1] += delta_um * 1e-6
        try:
            last = _run_model_once(
                mark_scan=[(p[0], p[1]) for p in perturbed],
                mark_data=mark_data,
                msx=msx,
                msy=msy,
                e_wsx=e_wsx,
                e_wsy=e_wsy,
                s_x=s_x,
                s_y=s_y,
                d_x=d_x,
                d_y=d_y,
            )
            history.append(last)
            if -20.0 < _to_float(last.get("output_Mw"), 9999.0) < 20.0:
                break
        except Exception:
            continue

    output = dict(last)
    output["n_88um"] = attempts
    output["model_history"] = history
    return output


# ── 月均值计算 ───────────────────────────────────────────────────────────────

@register("calculate_monthly_mean_Tx")
def calculate_monthly_mean_Tx(Tx: Optional[float] = None, **ctx) -> dict:
    values = _to_float_list(Tx)
    if values:
        return {"mean_Tx": _mean(values, 0.0)}
    return {"mean_Tx": _query_monthly_mean("wafer_translation_x", Tx, **ctx)}


@register("calculate_monthly_mean_Ty")
def calculate_monthly_mean_Ty(Ty: Optional[float] = None, **ctx) -> dict:
    values = _to_float_list(Ty)
    if values:
        return {"mean_Ty": _mean(values, 0.0)}
    return {"mean_Ty": _query_monthly_mean("wafer_translation_y", Ty, **ctx)}


@register("calculate_monthly_mean_Rw")
def calculate_monthly_mean_Rw(Rw: Optional[float] = None, **ctx) -> dict:
    values = _to_float_list(Rw)
    if values:
        return {"mean_Rw": _mean(values, 0.0)}
    return {"mean_Rw": _query_monthly_mean("wafer_rotation", Rw, **ctx)}


# ── 建模步骤 ────────────────────────────────────────────────────────────────

@register("build_88um_model")
def build_88um_model(**ctx) -> dict:
    return _build_model(88.0, **ctx)


@register("build_8um_model")
def build_8um_model(**ctx) -> dict:
    return _build_model(8.0, **ctx)


@register("build_model")
def build_model(**ctx) -> dict:
    """
    通用建模 action：
    - 优先使用上游传入的 model_type
    - 未传时根据 Mwx_0 自动判定
    """
    model_type = str(ctx.get("model_type", "")).lower().strip()

    if not model_type:
        determined = determine_model_type(**ctx).get("model_type", "unknown")
        model_type = str(determined).lower().strip()

    if model_type == "8um":
        out = _build_model(8.0, **ctx)
        out["model_type"] = "8um"
        return out

    if model_type == "88um":
        out = _build_model(88.0, **ctx)
        out["model_type"] = "88um"
        return out

    # 未知类型时，按 88um 兜底并标记 unknown，避免中断诊断链路
    out = _build_model(88.0, **ctx)
    out["model_type"] = "unknown"
    return out


# ── 模型类型判断 ────────────────────────────────────────────────────────────

@register("determine_model_type")
def determine_model_type(**ctx) -> dict:
    mwx0 = ctx.get("Mwx_0")
    if isinstance(mwx0, list):
        mwx0 = _first_numeric(mwx0, 0.0)
    try:
        value = float(mwx0)
    except (TypeError, ValueError):
        return {}

    if value > 1.0001 or value < 0.9999:
        return {"model_type": "88um"}
    if (1.00002 < value < 1.0001) or (0.9999 < value < 0.99998):
        return {"model_type": "8um"}
    return {"model_type": "unknown"}


@register("select_window_metric")
def select_window_metric(metric_name: str = "", values: Any = None, **ctx) -> dict:
    if not metric_name:
        return {}
    numeric_values = _to_float_list(values)
    if numeric_values:
        return {metric_name: numeric_values[0]}
    if isinstance(values, list):
        for item in values:
            if item is not None:
                return {metric_name: item}
        return {}
    if values is None:
        return {}
    return {metric_name: values}


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
