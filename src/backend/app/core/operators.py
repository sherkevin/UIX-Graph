"""
诊断算子库
包含数据源函数 (data_source) 和逻辑推理函数 (s2t)
"""
import random
from datetime import datetime
from typing import Dict, Any, List


# ============================================================================
# 数据源函数 (Mock Data Source Functions)
# ============================================================================

def get_wafer_rotation_mean() -> float:
    """获取晶圆旋转平均误差"""
    # 模拟数据：随机返回 200-400 urad 之间的值
    return round(random.uniform(200, 400), 2)


def get_wafer_rotation_sigma() -> float:
    """获取晶圆旋转3倍标准差"""
    # 模拟数据：随机返回 250-450 urad 之间的值
    return round(random.uniform(250, 450), 2)


def get_vacuum_sensor_state() -> str:
    """获取真空吸附状态"""
    # 模拟数据：随机返回 "High" 或 "Low"
    return random.choice(["High", "Low"])


def aggregate_inputs() -> Dict[str, Any]:
    """聚合多个输入值（用于 RULE_LOGIC 节点）"""
    # 这个函数在实际运行时会被诊断引擎动态调用
    # 返回空字典，实际值由引擎注入
    return {}


# ============================================================================
# 逻辑推理函数 (S2T Reasoning Functions)
# ============================================================================

def op_gt_300(val: float) -> bool:
    """判断 rotation_mean > 300"""
    return val > 300


def op_gt_350(val: float) -> bool:
    """判断 rotation_3sigma > 350"""
    return val > 350


def op_pass_value(val: Any) -> Any:
    """直接传递值（不进行判断）"""
    return val


def op_rule_vac_low_and_rot_gt_100(inputs: Dict[str, Any]) -> bool:
    """
    联合判断规则：vacuum_level == "Low" AND rotation_mean > 100

    Args:
        inputs: 字典，包含 IND_VAC_LEVEL 和 IND_ROT_MEAN 的值（节点ID）

    Returns:
        bool: 如果满足条件返回 True
    """
    # 支持两种键名：节点ID 或 参数名
    vacuum_level = inputs.get("IND_VAC_LEVEL") or inputs.get("vacuum_level")
    rotation_mean = inputs.get("IND_ROT_MEAN") or inputs.get("rotation_mean")

    if vacuum_level is None or rotation_mean is None:
        return False

    try:
        # rotation_mean 可能是字符串，需要转换为 float
        rot_val = float(rotation_mean) if isinstance(rotation_mean, str) else rotation_mean
        return vacuum_level == "Low" and rot_val > 100
    except (ValueError, TypeError):
        return False


# ============================================================================
# 算子注册表 (Operator Registry)
# ============================================================================

DATA_SOURCE_FUNCTIONS: Dict[str, callable] = {
    "get_wafer_rotation_mean": get_wafer_rotation_mean,
    "get_wafer_rotation_sigma": get_wafer_rotation_sigma,
    "get_vacuum_sensor_state": get_vacuum_sensor_state,
    "aggregate_inputs": aggregate_inputs,
}

S2T_FUNCTIONS: Dict[str, callable] = {
    "op_gt_300": op_gt_300,
    "op_gt_350": op_gt_350,
    "op_pass_value": op_pass_value,
    "op_rule_vac_low_and_rot_gt_100": op_rule_vac_low_and_rot_gt_100,
}


def get_data_source_function(name: str) -> callable:
    """获取数据源函数"""
    if name not in DATA_SOURCE_FUNCTIONS:
        raise ValueError(f"Unknown data source function: {name}")
    return DATA_SOURCE_FUNCTIONS[name]


def get_s2t_function(name: str) -> callable:
    """获取 S2T 推理函数"""
    if name not in S2T_FUNCTIONS:
        raise ValueError(f"Unknown s2t function: {name}")
    return S2T_FUNCTIONS[name]


def list_available_data_sources() -> List[str]:
    """列出所有可用的数据源函数"""
    return list(DATA_SOURCE_FUNCTIONS.keys())


def list_available_s2t_functions() -> List[str]:
    """列出所有可用的 S2T 函数"""
    return list(S2T_FUNCTIONS.keys())
