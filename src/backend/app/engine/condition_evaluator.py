"""
rules 条件表达式解析与求值工具
"""
import ast
import re
from typing import Any, Dict, Optional, Tuple


def normalize_condition_text(condition: str) -> str:
    return (condition or "").strip().replace("≤", "<=").replace("≥", ">=")


def parse_condition_literal(token: str) -> Any:
    raw = token.strip()
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return raw[1:-1]

    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def eval_comparison(left: Any, operator: str, right: Any) -> bool:
    normalized_op = "==" if operator == "=" else operator
    try:
        left_num = float(left)
        right_num = float(right)
        if normalized_op == "==":
            return abs(left_num - right_num) < 1e-9
        if normalized_op == "!=":
            return abs(left_num - right_num) >= 1e-9
        if normalized_op == "<":
            return left_num < right_num
        if normalized_op == "<=":
            return left_num <= right_num
        if normalized_op == ">":
            return left_num > right_num
        if normalized_op == ">=":
            return left_num >= right_num
        return False
    except (TypeError, ValueError):
        left_str = str(left)
        right_str = str(right)
        if normalized_op == "==":
            return left_str == right_str
        if normalized_op == "!=":
            return left_str != right_str
        return False


def parse_condition_signature(condition: str) -> Optional[Dict[str, Any]]:
    """
    解析 condition 文本结构，不依赖运行时 context。
    返回:
    - {"type":"always"}
    - {"type":"range","var":...,"operator":"between","limit":[lo,hi]}
    - {"type":"comparison","var":...,"operator":"==","rhs":...}
    """
    expr = normalize_condition_text(condition)
    if not expr:
        return {"type": "always"}
    if expr == "else":
        return {"type": "else"}

    range_match = re.match(
        r"^\s*(-?\d+(?:\.\d+)?)\s*<\s*\{?([A-Za-z_]\w*)\}?\s*<\s*(-?\d+(?:\.\d+)?)\s*$",
        expr,
    )
    if range_match:
        return {
            "type": "range",
            "var": range_match.group(2),
            "operator": "between",
            "limit": [float(range_match.group(1)), float(range_match.group(3))],
        }

    compare_match = re.match(
        r"^\s*\{?([A-Za-z_]\w*)\}?\s*(==|=|!=|<=|>=|<|>)\s*(.+)\s*$",
        expr,
    )
    if compare_match:
        return {
            "type": "comparison",
            "var": compare_match.group(1),
            "operator": compare_match.group(2),
            "rhs": parse_condition_literal(compare_match.group(3).strip()),
        }
    return None


def evaluate_condition_text(
    condition: str,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], str, Any, Any]:
    signature = parse_condition_signature(condition)
    if signature is None:
        return False, fallback_metric_id, "", None, None

    sig_type = signature["type"]
    if sig_type == "always":
        return True, fallback_metric_id, "", None, None
    if sig_type == "else":
        return False, fallback_metric_id, "", None, None

    if sig_type == "range":
        var_name = signature["var"]
        limits = signature["limit"]
        value = context.get(var_name)
        if value is None:
            return False, var_name, "between", limits, None
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return False, var_name, "between", limits, value
        return limits[0] < numeric_value < limits[1], var_name, "between", limits, numeric_value

    if sig_type == "comparison":
        var_name = signature["var"]
        operator = signature["operator"]
        rhs_value = signature["rhs"]
        left_value = context.get(var_name)
        if left_value is None:
            return False, var_name, operator, rhs_value, None
        return (
            eval_comparison(left_value, operator, rhs_value),
            var_name,
            operator,
            rhs_value,
            left_value,
        )

    return False, fallback_metric_id, "", None, None
