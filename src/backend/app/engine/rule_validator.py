"""
诊断 steps / scenes 静态校验器
"""
from typing import Any, Callable, Dict, List, Set

from app.engine.condition_evaluator import (
    _extract_vars_from_definition,
    validate_condition_definition,
)


SUPPORTED_OPERATORS = {">", "<", ">=", "<=", "==", "!="}


def validate_rules_config(
    rules_data: Dict[str, Any],
    action_exists: Callable[[str], bool],
) -> List[str]:
    """
    返回错误列表；空列表表示通过。
    """
    errors: List[str] = []
    scenes = rules_data.get("diagnosis_scenes") or []
    steps = rules_data.get("steps") or []

    if not isinstance(steps, list) or not steps:
        return ["rules.steps 不能为空"]

    step_ids = [str(s.get("id")) for s in steps if "id" in s]
    if len(step_ids) != len(set(step_ids)):
        errors.append("steps 存在重复 id")

    step_id_set: Set[str] = set(step_ids)

    for scene in scenes:
        scene_id = scene.get("id")
        start_node = str(scene.get("start_node", "")).strip()
        if not start_node or start_node not in step_id_set:
            errors.append(f"scene(id={scene_id}) start_node 无效: {start_node}")

        scene_metric_ids = scene.get("metric_id") or []
        if isinstance(scene_metric_ids, str):
            scene_metric_ids = [scene_metric_ids]
        if not isinstance(scene_metric_ids, list):
            errors.append(f"scene(id={scene_id}) metric_id 必须是非空数组或字符串")
            scene_metric_ids = []

        trigger_conditions = scene.get("trigger_condition") or []
        if isinstance(trigger_conditions, str):
            trigger_conditions = [trigger_conditions]
        if trigger_conditions and not isinstance(trigger_conditions, list):
            errors.append(f"scene(id={scene_id}) trigger_condition 必须是数组或字符串")
            trigger_conditions = []

        for idx, condition in enumerate(trigger_conditions):
            if condition is None or condition == "":
                errors.append(f"scene(id={scene_id}) trigger_condition[{idx}] 不能为空")
                continue
            if not validate_condition_definition(condition):
                errors.append(f"scene(id={scene_id}) trigger_condition[{idx}] 无法解析: {condition}")
                continue
            used_vars = _extract_vars_from_definition(condition)
            missing_vars = [var for var in used_vars if var not in scene_metric_ids]
            if missing_vars:
                errors.append(
                    f"scene(id={scene_id}) trigger_condition[{idx}] 引用了未声明 metric_id: {','.join(missing_vars)}"
                )

    for step in steps:
        sid = str(step.get("id"))
        details = step.get("details") or []
        if details is not None and not isinstance(details, list):
            errors.append(f"step({sid}) details 必须是数组或 null")
            continue

        for item in details:
            if not isinstance(item, dict):
                errors.append(f"step({sid}) details 项必须是对象")
                continue
            action = item.get("action")
            if action and not action_exists(str(action)):
                errors.append(f"step({sid}) action 未注册: {action}")

        next_branches = step.get("next") or []
        if next_branches is not None and not isinstance(next_branches, list):
            errors.append(f"step({sid}) next 必须是数组或 null")
            continue

        for idx, branch in enumerate(next_branches):
            if not isinstance(branch, dict):
                errors.append(f"step({sid}) next[{idx}] 必须是对象")
                continue

            target = branch.get("target")
            if target is None:
                errors.append(f"step({sid}) next[{idx}] 缺少 target")
            elif isinstance(target, list):
                for t in target:
                    if str(t) not in step_id_set:
                        errors.append(f"step({sid}) next[{idx}] target 不存在: {t}")
            else:
                if str(target) not in step_id_set:
                    errors.append(f"step({sid}) next[{idx}] target 不存在: {target}")

            condition = branch.get("condition")
            operator = (branch.get("operator") or "").strip()
            limit = branch.get("limit")

            if condition == "else":
                continue

            if operator:
                if operator not in SUPPORTED_OPERATORS:
                    errors.append(f"step({sid}) next[{idx}] operator 不支持: {operator}")
                if operator != "else" and limit is None:
                    errors.append(f"step({sid}) next[{idx}] operator={operator} 缺少 limit")
                continue

            # 无 operator 的条件必须可解析（空串代表无条件跳转）
            if condition:
                if not validate_condition_definition(condition):
                    errors.append(f"step({sid}) next[{idx}] condition 无法解析: {condition}")

    return errors
