"""
内置 Action 函数
"""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
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


def _transpose(m: List[List[float]]) -> List[List[float]]:
    return [list(col) for col in zip(*m)]


def _matmul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
        for i in range(len(a))
    ]


def _matvec(a: List[List[float]], v: List[float]) -> List[float]:
    return [sum(a[i][k] * v[k] for k in range(len(v))) for i in range(len(a))]


def _solve_linear_system(a: List[List[float]], b: List[float]) -> List[float]:
    """高斯消元解 Ax=b，A 为方阵。"""
    n = len(a)
    aug = [row[:] + [b[i]] for i, row in enumerate(a)]

    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(aug[r][i]))
        if abs(aug[pivot][i]) < 1e-12:
            raise ValueError("singular matrix")
        aug[i], aug[pivot] = aug[pivot], aug[i]

        factor = aug[i][i]
        for j in range(i, n + 1):
            aug[i][j] /= factor

        for r in range(n):
            if r == i:
                continue
            f = aug[r][i]
            for c in range(i, n + 1):
                aug[r][c] -= f * aug[i][c]

    return [aug[i][n] for i in range(n)]


def _least_squares(a: List[List[float]], b: List[float]) -> List[float]:
    at = _transpose(a)
    ata = _matmul(at, a)
    atb = _matvec(at, b)
    return _solve_linear_system(ata, atb)


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
    a1: List[List[float]] = []
    b1: List[float] = []
    for i in range(min(len(mark_scan), len(mark_data))):
        md_x, md_y = mark_data[i]
        ms_x, ms_y = mark_scan[i]
        a1.append([1.0, 0.0, md_x, -md_y])
        b1.append(ms_x * msx - e_wsx - md_x)
        a1.append([0.0, 1.0, md_y, md_x])
        b1.append(ms_y * msy - e_wsy - md_y)

    cwx, cwy, mw, rw = _least_squares(a1, b1)
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

    msx = _to_float(ctx.get("Msx"), 1.0)
    msy = _to_float(ctx.get("Msy"), 1.0)
    e_wsx = _to_float(ctx.get("e_ws_x"), 0.0)
    e_wsy = _to_float(ctx.get("e_ws_y"), 0.0)
    s_x = _to_float(ctx.get("Sx"), 0.0)
    s_y = _to_float(ctx.get("Sy"), 0.0)
    d_x = _to_float(ctx.get("D_x"), 0.0)
    d_y = _to_float(ctx.get("D_y"), 0.0)

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

    last = {"output_Tx": _to_float(ctx.get("Tx"), 0.0), "output_Ty": _to_float(ctx.get("Ty"), 0.0), "output_Mw": 9999.0, "output_Rw": _to_float(ctx.get("Rw"), 0.0)}
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
    return {"mean_Tx": _query_monthly_mean("wafer_translation_x", Tx, **ctx)}


@register("calculate_monthly_mean_Ty")
def calculate_monthly_mean_Ty(Ty: Optional[float] = None, **ctx) -> dict:
    return {"mean_Ty": _query_monthly_mean("wafer_translation_y", Ty, **ctx)}


@register("calculate_monthly_mean_Rw")
def calculate_monthly_mean_Rw(Rw: Optional[float] = None, **ctx) -> dict:
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
    model_type = str(ctx.get("model_type", "")).lower()
    if "8um" in model_type:
        return _build_model(8.0, **ctx)
    return _build_model(88.0, **ctx)


# ── 模型类型判断 ────────────────────────────────────────────────────────────

@register("determine_model_type")
def determine_model_type(**ctx) -> dict:
    mwx0 = ctx.get("Mwx_0")
    try:
        value = float(mwx0)
    except (TypeError, ValueError):
        return {}

    if value > 1.0001 or value < 0.9999:
        return {"model_type": "88um"}
    if (1.00002 < value < 1.0001) or (0.9999 < value < 0.99998):
        return {"model_type": "8um"}
    return {"model_type": "unknown"}


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
