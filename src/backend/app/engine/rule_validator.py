"""
诊断 steps / scenes 静态校验器
"""
from typing import Any, Callable, Dict, List, Optional, Set

from app.engine.condition_evaluator import (
    _extract_vars_from_definition,
    extract_condition_vars,
    validate_condition_definition,
)


def _pipeline_allowed_var_names(
    metrics: Dict[str, Any],
    scenes: List[Any],
    steps: List[Any],
) -> Set[str]:
    """Phase A：condition 中出现的变量须落在此集合（metrics 键 ∪ scene/step metric_id ∪ 分支 set 键）。"""
    names: Set[str] = set(metrics.keys())
    for scene in scenes:
        mids = scene.get("metric_id") or []
        if isinstance(mids, str):
            mids = [mids]
        if isinstance(mids, list):
            for mid in mids:
                names.add(str(mid))
    for step in steps:
        if not isinstance(step, dict):
            continue
        mid = step.get("metric_id")
        if mid:
            names.add(str(mid))
        for item in step.get("details") or []:
            if not isinstance(item, dict):
                continue
            res = item.get("results")
            if isinstance(res, dict):
                names.update(str(k) for k in res.keys())
        for br in step.get("next") or []:
            if not isinstance(br, dict):
                continue
            st = br.get("set")
            if isinstance(st, dict):
                names.update(str(k) for k in st.keys())
    return names


def validate_rules_config(
    rules_data: Dict[str, Any],
    action_exists: Callable[[str], bool],
    metrics: Optional[Dict[str, Any]] = None,
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

    allowed_pipeline_vars: Optional[Set[str]] = None
    if metrics is not None and isinstance(metrics, dict):
        allowed_pipeline_vars = _pipeline_allowed_var_names(metrics, scenes, steps)

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
            operator_raw = branch.get("operator")
            limit_raw = branch.get("limit")

            if operator_raw is not None and str(operator_raw).strip():
                errors.append(
                    f"step({sid}) next[{idx}] 已废弃 operator 字段，请在 condition 中写比较或区间表达式"
                    "（见 docs/stage3/rules_execution_spec.md）"
                )
            if limit_raw is not None:
                errors.append(
                    f"step({sid}) next[{idx}] 已废弃 limit 字段，请在 condition 中写比较或区间表达式"
                )

            if condition == "else":
                continue

            if condition is None or (isinstance(condition, str) and not str(condition).strip()):
                continue

            if not validate_condition_definition(condition):
                errors.append(f"step({sid}) next[{idx}] condition 无法解析: {condition}")
                continue

            if allowed_pipeline_vars is not None:
                if isinstance(condition, str):
                    used_names = extract_condition_vars(condition)
                else:
                    used_names = _extract_vars_from_definition(condition)
                for vn in used_names:
                    if vn not in allowed_pipeline_vars:
                        errors.append(
                            f"step({sid}) next[{idx}] condition 引用未知变量 {vn!r}"
                            "（须为 metrics 键、某 step.metric_id、scene.metric_id 或某分支 set 键）"
                        )

    return errors
