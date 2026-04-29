"""
rules 条件表达式解析与求值工具
"""
import ast
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


SUPPORTED_COMPARISON_OPERATORS = {"<", ">", "<=", ">=", "==", "!="}


def normalize_condition_text(condition: str) -> str:
    return (condition or "").strip()


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
        if any(ch in raw for ch in (".", "e", "E")):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def extract_vars_from_definition(condition: Any) -> List[str]:
    if isinstance(condition, dict):
        if "compare" in condition and isinstance(condition["compare"], dict):
            left = condition["compare"].get("left")
            return [str(left)] if left is not None else []
        result: List[str] = []
        for key in ("all_of", "any_of"):
            for item in condition.get(key, []) or []:
                for name in extract_vars_from_definition(item):
                    if name not in result:
                        result.append(name)
        if "not" in condition:
            for name in extract_vars_from_definition(condition.get("not")):
                if name not in result:
                    result.append(name)
        return result
    return extract_condition_vars(str(condition))


_extract_vars_from_definition = extract_vars_from_definition


def extract_condition_vars(condition: str) -> List[str]:
    expr = normalize_condition_text(condition)
    if not expr:
        return []
    return _collect_vars_from_boolean_expr(expr)


def _collect_vars_from_boolean_expr(expr: str) -> List[str]:
    text_expr = _strip_outer_parentheses(expr)
    result: List[str] = []
    or_parts = _split_top_level_boolean(text_expr, "OR")
    if len(or_parts) > 1:
        for part in or_parts:
            for var_name in _collect_vars_from_boolean_expr(part):
                if var_name not in result:
                    result.append(var_name)
        return result
    and_parts = _split_top_level_boolean(text_expr, "AND")
    if len(and_parts) > 1:
        for part in and_parts:
            for var_name in _collect_vars_from_boolean_expr(part):
                if var_name not in result:
                    result.append(var_name)
        return result
    signature = parse_condition_signature(text_expr)
    if not signature:
        return []
    if signature.get("type") == "range":
        var_name = signature.get("var")
        return [str(var_name)] if isinstance(var_name, str) else []
    if signature.get("type") == "comparison":
        vars_found: List[str] = []
        left_var = signature.get("var")
        right_var = signature.get("rhs_var")
        if isinstance(left_var, str):
            vars_found.append(left_var)
        if isinstance(right_var, str) and right_var not in vars_found:
            vars_found.append(right_var)
        return vars_found
    return []


def _strip_outer_parentheses(expr: str) -> str:
    text_expr = expr.strip()
    while text_expr.startswith("(") and text_expr.endswith(")"):
        depth = 0
        closes_at_end = True
        for idx, ch in enumerate(text_expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text_expr) - 1:
                    closes_at_end = False
                    break
        if depth != 0 or not closes_at_end:
            break
        text_expr = text_expr[1:-1].strip()
    return text_expr


def _split_top_level_boolean(expr: str, op: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    i = 0
    op_text = f" {op} "
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and expr[i:i + len(op_text)].lower() == op_text.lower():
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            i += len(op_text)
            continue
        buf.append(ch)
        i += 1
    last = "".join(buf).strip()
    if last:
        parts.append(last)
    return parts


def eval_comparison(left: Any, operator: str, right: Any) -> bool:
    # ClickHouse/MySQL 窗口类指标常返回 list；与 true/false 比较时不能走 str(left)==str(right)，
    # 否则 [True,True]==true 会变成 "[True, True]"=="True" 恒为假，导致场景触发永远不命中。
    if isinstance(left, list) and isinstance(right, bool):
        any_truthy = any(bool(x) for x in left)
        if operator == "==":
            return any_truthy if right else (not any_truthy)
        if operator == "!=":
            return (not any_truthy) if right else any_truthy
    try:
        left_num = float(left)
        right_num = float(right)
        if operator == "==":
            return abs(left_num - right_num) < 1e-9
        if operator == "!=":
            return abs(left_num - right_num) >= 1e-9
        if operator == "<":
            return left_num < right_num
        if operator == "<=":
            return left_num <= right_num
        if operator == ">":
            return left_num > right_num
        if operator == ">=":
            return left_num >= right_num
        return False
    except (TypeError, ValueError):
        left_str = str(left)
        right_str = str(right)
        if operator == "==":
            return left_str == right_str
        if operator == "!=":
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

    if re.search(r"(?i)\b(?:and|or)\b", expr):
        return None

    range_match = re.match(
        r"^\s*(-?\d+(?:\.\d+)?)\s*<\s*\{([^}]+)\}\s*<\s*(-?\d+(?:\.\d+)?)\s*$",
        expr,
    )
    if range_match:
        var_name = (range_match.group(2) or "").strip()
        return {
            "type": "range",
            "var": var_name,
            "operator": "between",
            "limit": [float(range_match.group(1)), float(range_match.group(3))],
        }

    compare_match = re.match(
        r"^\s*\{([^}]+)\}\s*(==|!=|<=|>=|<|>)\s*(.+)\s*$",
        expr,
    )
    if compare_match:
        var_name = (compare_match.group(1) or "").strip()
        rhs_token = compare_match.group(3).strip()
        rhs_var_match = re.match(r"^\{([^}]+)\}$", rhs_token)
        return {
            "type": "comparison",
            "var": var_name,
            "operator": compare_match.group(2),
            "rhs": parse_condition_literal(rhs_token) if rhs_var_match is None else None,
            "rhs_var": rhs_var_match.group(1).strip() if rhs_var_match else None,
        }
    return None


def evaluate_condition_text(
    condition: str,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], str, Any, Any]:
    signature = parse_condition_signature(condition)
    if signature is None:
        expr = normalize_condition_text(condition)
        if expr:
            snippet = expr if len(expr) <= 200 else expr[:200] + "..."
            logger.warning(
                "condition 无法解析为原子表达式（将视为不匹配）: %r fallback_metric_id=%s",
                snippet,
                fallback_metric_id,
            )
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
        rhs_var_name = signature.get("rhs_var")
        rhs_value = context.get(rhs_var_name) if rhs_var_name else signature.get("rhs")
        left_value = context.get(var_name)
        if left_value is None:
            return False, var_name, operator, rhs_value, None
        if rhs_var_name and rhs_value is None:
            return False, var_name, operator, rhs_var_name, left_value
        return (
            eval_comparison(left_value, operator, rhs_value),
            var_name,
            operator,
            rhs_value,
            left_value,
        )

    return False, fallback_metric_id, "", None, None


def evaluate_condition_definition(
    condition: Any,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], str, Any, Any]:
    if isinstance(condition, str):
        return evaluate_condition_text(condition, context, fallback_metric_id)
    if not isinstance(condition, dict):
        return False, fallback_metric_id, "", None, None
    if "compare" in condition and isinstance(condition["compare"], dict):
        spec = condition["compare"]
        left_name = str(spec.get("left", "")).strip()
        operator = str(spec.get("operator", spec.get("op", ""))).strip()
        right = spec.get("right")
        value = context.get(left_name)
        if not left_name:
            return False, fallback_metric_id, "", None, None
        if value is None:
            return False, left_name, operator, right, None
        return eval_comparison(value, operator, right), left_name, operator, right, value
    if "all_of" in condition:
        results = [evaluate_condition_definition(item, context, fallback_metric_id) for item in condition.get("all_of", []) or []]
        matched = bool(results) and all(item[0] for item in results)
        return matched, None, "all_of", None, None
    if "any_of" in condition:
        results = [evaluate_condition_definition(item, context, fallback_metric_id) for item in condition.get("any_of", []) or []]
        matched = any(item[0] for item in results)
        return matched, None, "any_of", None, None
    if "not" in condition:
        matched, _, _, _, _ = evaluate_condition_definition(condition.get("not"), context, fallback_metric_id)
        return (not matched), None, "not", None, None
    return False, fallback_metric_id, "", None, None


def validate_boolean_condition_text(condition: str) -> bool:
    expr = normalize_condition_text(condition)
    if not expr:
        return True
    return _validate_boolean_expr(expr)


def _validate_boolean_expr(expr: str) -> bool:
    text_expr = _strip_outer_parentheses(expr)
    if not text_expr:
        return True
    if _has_invalid_parentheses(text_expr):
        return False
    or_parts = _split_top_level_boolean(text_expr, "OR")
    if len(or_parts) > 1:
        return all(_validate_boolean_expr(part) for part in or_parts)
    and_parts = _split_top_level_boolean(text_expr, "AND")
    if len(and_parts) > 1:
        return all(_validate_boolean_expr(part) for part in and_parts)
    return parse_condition_signature(text_expr.strip()) is not None


def _has_invalid_parentheses(expr: str) -> bool:
    depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def validate_condition_definition(condition: Any) -> bool:
    if isinstance(condition, str):
        return validate_boolean_condition_text(condition)
    if not isinstance(condition, dict):
        return False
    if "compare" in condition and isinstance(condition["compare"], dict):
        spec = condition["compare"]
        operator = str(spec.get("operator", spec.get("op", ""))).strip()
        return (
            bool(spec.get("left"))
            and operator in SUPPORTED_COMPARISON_OPERATORS
            and "right" in spec
        )
    if "all_of" in condition:
        items = condition.get("all_of", []) or []
        return bool(items) and all(validate_condition_definition(item) for item in items)
    if "any_of" in condition:
        items = condition.get("any_of", []) or []
        return bool(items) and all(validate_condition_definition(item) for item in items)
    if "not" in condition:
        return validate_condition_definition(condition.get("not"))
    return False


def evaluate_boolean_condition_text(
    condition: str,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str] = None,
) -> bool:
    """评估由简单比较条件通过 AND/OR 组合而成的布尔表达式（支持括号）。"""
    expr = normalize_condition_text(condition)
    if not expr:
        return True
    return _evaluate_boolean_expr(expr, context, fallback_metric_id)


def _evaluate_boolean_expr(
    expr: str,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str],
) -> bool:
    text_expr = _strip_outer_parentheses(expr)
    if not text_expr:
        return True

    or_parts = _split_top_level_boolean(text_expr, "OR")
    if len(or_parts) > 1:
        return any(_evaluate_boolean_expr(part, context, fallback_metric_id) for part in or_parts)

    and_parts = _split_top_level_boolean(text_expr, "AND")
    if len(and_parts) > 1:
        return all(_evaluate_boolean_expr(part, context, fallback_metric_id) for part in and_parts)

    return evaluate_condition_text(text_expr, context, fallback_metric_id)[0]


def explain_top_level_and_parts(
    condition: str,
    context: Dict[str, Any],
) -> List[Tuple[str, bool]]:
    """
    将顶层 AND 拆成子句并分别求值，供场景触发排障日志使用。
    若无法拆分（无顶层 AND），则整句求值一次。
    """
    expr = normalize_condition_text(condition)
    if not expr:
        return []
    text_expr = _strip_outer_parentheses(expr)
    parts = _split_top_level_boolean(text_expr, "AND")
    if len(parts) <= 1:
        return [(condition, evaluate_boolean_condition_text(condition, context))]
    out: List[Tuple[str, bool]] = []
    for part in parts:
        p = part.strip()
        if p:
            out.append((p, evaluate_boolean_condition_text(p, context)))
    return out


def evaluate_boolean_condition_definition(
    condition: Any,
    context: Dict[str, Any],
    fallback_metric_id: Optional[str] = None,
) -> bool:
    if isinstance(condition, str):
        return evaluate_boolean_condition_text(condition, context, fallback_metric_id)
    matched, _, _, _, _ = evaluate_condition_definition(condition, context, fallback_metric_id)
    return matched
