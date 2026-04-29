"""
诊断 steps / scenes / metrics 静态校验器

设计目标:**配置驱动 fail-fast**——专家只改配置文档就要能跑;若配置写错,
服务启动时报错而非运行时静默拿空值。

校验层次:
  1. validate_metrics_metadata    metrics{} 字典,每个 metric 元数据
  2. validate_rules_config        diagnosis_scenes[] + steps[] + 引用一致性
"""
from typing import Any, Callable, Dict, List, Optional, Set

from app.engine.condition_evaluator import (
    extract_vars_from_definition,
    extract_condition_vars,
    validate_condition_definition,
)


# ────────────────────────────────────────────────────────────────────────────
# metric 元数据合法值集合
# 维护人:增加新枚举值时,**同步**更新 metric_fetcher.py 对应的处理分支;
# 否则配置写了通过校验,运行时 metric_fetcher 不识别仍然失败,违背 fail-fast。
# ────────────────────────────────────────────────────────────────────────────

VALID_SOURCE_KINDS: Set[str] = {
    "failure_record_field",   # 从故障主记录字段取(transform 可选)
    "request_param",          # 从请求 params 字段取
    "mysql_nearest_row",      # MySQL 时间窗口查询
    "clickhouse_window",      # ClickHouse 时间窗口查询
    "intermediate",           # 中间量,由 action 写入 context
    # 历史别名(metric_fetcher 自动归一化,允许在配置里使用)
    "mysql",                  # → mysql_nearest_row
    "clickhouse",             # → clickhouse_window
}

VALID_ROLES: Set[str] = {
    "diagnostic",      # 默认,会进入接口 3 metrics 列表展示
    "trigger_only",    # 仅用于场景触发判断,不展示
    "internal",        # 中间量(如 *_history 窗口列表),仅供 action 用
    "derived",         # 由 _backfill_metrics_from_steps 自动补全的派生项
}

VALID_LINKING_MODES: Set[str] = {
    "time_window_only",
    "exact_keys",
}

VALID_LINKING_OPERATORS: Set[str] = {
    "=", "==", "!=", ">", ">=", "<", "<=",
    "contains",   # MySQL: INSTR / ClickHouse: positionUTF8
    "in",         # 列表 IN (...)
}

VALID_FALLBACK_POLICIES: Set[str] = {
    "none",
    "nearest_in_window",
}

VALID_EXTRACTION_PREFIXES: Set[str] = {
    "",          # 空字符串 = 标量规范化
    "regex:",
    "json:",
    "jsonpath:",
}

VALID_TRANSFORM_TYPES: Set[str] = {
    "equals", "not_equals",
    "float", "int", "bool",
    "upper_equals", "lower_equals",
    "contains",
    "map",
}

VALID_DATA_TYPES: Set[str] = {
    "int", "integer",
    "float", "double", "number",
    "bool", "boolean",
    "str", "string", "text",
}

# DB 类必填字段
DB_SOURCE_KINDS: Set[str] = {
    "mysql_nearest_row", "clickhouse_window", "mysql", "clickhouse",
}

# 直接取字段类(必填 field)
DIRECT_FIELD_KINDS: Set[str] = {
    "failure_record_field", "request_param",
}


# ────────────────────────────────────────────────────────────────────────────
# metric 元数据校验
# ────────────────────────────────────────────────────────────────────────────

def _validate_one_metric(metric_id: str, meta: Any) -> List[str]:
    """对单个 metric 的元数据做静态校验,返回错误列表。"""
    if not isinstance(meta, dict):
        return [f"metric({metric_id}) 元数据必须是对象,实际为 {type(meta).__name__}"]

    errors: List[str] = []

    # 1. source_kind 合法性(且必填)
    raw_kind = meta.get("source_kind")
    if raw_kind is None or str(raw_kind).strip() == "":
        # 历史兼容:config_store._normalize_structured_pipeline 会默认填 'intermediate',
        # 所以此处仅警告级别:用 derived role 的占位指标允许不写
        if str(meta.get("role", "")).strip().lower() != "derived":
            errors.append(
                f"metric({metric_id}) 缺少 source_kind"
                f"(应为 {sorted(VALID_SOURCE_KINDS - {'mysql', 'clickhouse'})} 之一)"
            )
        return errors  # 后续字段校验依赖 source_kind,缺了直接返回
    kind = str(raw_kind).strip().lower()
    if kind not in VALID_SOURCE_KINDS:
        errors.append(
            f"metric({metric_id}) source_kind 非法: {raw_kind!r}"
            f";合法值: {sorted(VALID_SOURCE_KINDS - {'mysql', 'clickhouse'})}"
            f"(亦接受历史别名 mysql / clickhouse)"
        )
        return errors

    # 归一化(用于后续 DB/直接取值分支判断)
    normalized_kind = {"mysql": "mysql_nearest_row", "clickhouse": "clickhouse_window"}.get(kind, kind)

    # 2. role 合法性(可选,默认 diagnostic)
    if "role" in meta:
        role = str(meta.get("role", "")).strip().lower()
        if role and role not in VALID_ROLES:
            errors.append(
                f"metric({metric_id}) role 非法: {meta.get('role')!r};"
                f"合法值: {sorted(VALID_ROLES)}"
            )

    # 3. data_type 合法性(可选)
    if meta.get("data_type") is not None:
        dt = str(meta.get("data_type")).strip().lower()
        if dt and dt not in VALID_DATA_TYPES:
            errors.append(
                f"metric({metric_id}) data_type 非法: {meta.get('data_type')!r};"
                f"合法值: {sorted(VALID_DATA_TYPES)}"
            )

    # 4. transform 校验(可选)
    transform = meta.get("transform")
    if transform is not None:
        if not isinstance(transform, dict):
            errors.append(f"metric({metric_id}) transform 必须是对象")
        else:
            t_type = str(transform.get("type", "")).strip().lower()
            if not t_type:
                errors.append(f"metric({metric_id}) transform 缺少 type")
            elif t_type not in VALID_TRANSFORM_TYPES:
                errors.append(
                    f"metric({metric_id}) transform.type 非法: {transform.get('type')!r};"
                    f"合法值: {sorted(VALID_TRANSFORM_TYPES)}"
                )
            elif t_type == "map":
                # map 类型需要 mapping 字典
                if not isinstance(transform.get("mapping"), dict):
                    errors.append(
                        f"metric({metric_id}) transform.type='map' 需要 mapping 字典"
                    )

    # 5. extraction_rule prefix 合法性(可选)
    extraction = meta.get("extraction_rule")
    if extraction is not None and extraction != "":
        ext_str = str(extraction)
        # 检查前缀是否在合法集合中(空字符串单独处理)
        prefix_ok = any(
            ext_str == "" or ext_str.startswith(prefix)
            for prefix in VALID_EXTRACTION_PREFIXES
            if prefix  # 跳过空字符串
        )
        if not prefix_ok:
            errors.append(
                f"metric({metric_id}) extraction_rule 前缀非法: {ext_str[:40]!r};"
                f"合法前缀: {sorted(p for p in VALID_EXTRACTION_PREFIXES if p)} 或空字符串"
            )

    # 6. fallback.policy 合法性(可选)
    fallback = meta.get("fallback")
    if fallback is not None:
        if not isinstance(fallback, dict):
            errors.append(f"metric({metric_id}) fallback 必须是对象")
        else:
            policy = str(fallback.get("policy", "")).strip().lower()
            if policy and policy not in VALID_FALLBACK_POLICIES:
                errors.append(
                    f"metric({metric_id}) fallback.policy 非法: {fallback.get('policy')!r};"
                    f"合法值: {sorted(VALID_FALLBACK_POLICIES)}"
                )

    # 7. linking 合法性(可选,DB 类常用)
    linking = meta.get("linking")
    if linking is not None:
        if not isinstance(linking, dict):
            errors.append(f"metric({metric_id}) linking 必须是对象")
        else:
            mode = str(linking.get("mode", "")).strip().lower()
            if mode and mode not in VALID_LINKING_MODES:
                errors.append(
                    f"metric({metric_id}) linking.mode 非法: {linking.get('mode')!r};"
                    f"合法值: {sorted(VALID_LINKING_MODES)}"
                )
            for field_name in ("keys", "filters"):
                items = linking.get(field_name) or []
                if items and not isinstance(items, list):
                    errors.append(
                        f"metric({metric_id}) linking.{field_name} 必须是数组"
                    )
                    continue
                for idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        errors.append(
                            f"metric({metric_id}) linking.{field_name}[{idx}] 必须是对象"
                        )
                        continue
                    target = str(item.get("target", "")).strip()
                    if not target:
                        errors.append(
                            f"metric({metric_id}) linking.{field_name}[{idx}] 缺少 target(列名)"
                        )
                    op = str(item.get("operator", "=")).strip()
                    if op and op not in VALID_LINKING_OPERATORS:
                        errors.append(
                            f"metric({metric_id}) linking.{field_name}[{idx}] operator 非法: {op!r};"
                            f"合法值: {sorted(VALID_LINKING_OPERATORS)}"
                        )
                    # source 与 value 二选一(且不能同时缺失)
                    has_source = "source" in item and str(item.get("source", "")).strip()
                    has_value = "value" in item
                    if not has_source and not has_value:
                        errors.append(
                            f"metric({metric_id}) linking.{field_name}[{idx}] 必须提供 source(取上下文)或 value(字面量)"
                        )

    # 8. DB 类 source_kind 必填 table_name + column_name
    if normalized_kind in DB_SOURCE_KINDS:
        if not str(meta.get("table_name", "")).strip():
            errors.append(
                f"metric({metric_id}) source_kind={kind} 必须提供 table_name"
            )
        if not str(meta.get("column_name", "")).strip():
            errors.append(
                f"metric({metric_id}) source_kind={kind} 必须提供 column_name"
            )
        # duration 应能转成 int(可选,但配错容易走默认窗口)
        dur = meta.get("duration")
        if dur is not None:
            try:
                int(str(dur).strip())
            except (TypeError, ValueError):
                errors.append(
                    f"metric({metric_id}) duration 必须是整数(单位:天),实际: {dur!r}"
                )

    # 9. 直接取字段类必填 field
    if normalized_kind in DIRECT_FIELD_KINDS:
        if not str(meta.get("field", "")).strip():
            errors.append(
                f"metric({metric_id}) source_kind={kind} 必须提供 field"
                f"(对应{'故障记录' if normalized_kind == 'failure_record_field' else '请求 params'}中的键名)"
            )

    # 10. mock_range 字段校验(post-stage4 Bug #5 fix)
    #     mock_value 类型不限(任何 JSON 字面量都可),不强校验。
    if "mock_range" in meta:
        mock_range = meta.get("mock_range")
        if not isinstance(mock_range, list) or len(mock_range) != 2:
            errors.append(
                f"metric({metric_id}) mock_range 必须是长度为 2 的数组 [low, high]"
            )
        else:
            try:
                low, high = float(mock_range[0]), float(mock_range[1])
                if low > high:
                    errors.append(
                        f"metric({metric_id}) mock_range[0]={low} > [1]={high},应为 [low, high]"
                    )
            except (TypeError, ValueError):
                errors.append(
                    f"metric({metric_id}) mock_range 元素必须是数字,实际: {mock_range}"
                )

    return errors


def _validate_alias_references(metrics: Dict[str, Any]) -> List[str]:
    """
    跨 metric 校验 alias_of 引用关系:
    
    - alias_of 必须是字符串
    - 不能自指 (alias_of != 自身 metric_id)
    - 引用的目标必须存在于本 pipeline 的 metrics 字典中
    - 不允许形成循环(A alias_of B, B alias_of A)
    
    用于 post-stage4 Bug #3 fix(_METRIC_ALIAS_MAP 配置化)的字段校验。
    """
    errors: List[str] = []
    metric_ids = set(metrics.keys())

    # 1. 类型 + 自指 + 目标存在
    alias_pairs: List[tuple] = []
    for mid, meta in metrics.items():
        if not isinstance(meta, dict):
            continue
        if "alias_of" not in meta:
            continue
        target = meta.get("alias_of")
        if not isinstance(target, str) or not target.strip():
            errors.append(
                f"metric({mid}) alias_of 必须是非空字符串,实际: {target!r}"
            )
            continue
        target = target.strip()
        if target == mid:
            errors.append(f"metric({mid}) alias_of 不能自指")
            continue
        if target not in metric_ids:
            errors.append(
                f"metric({mid}) alias_of 指向 {target!r},但该 metric 不存在"
            )
            continue
        alias_pairs.append((mid, target))

    # 2. 简单循环检测(每条 alias 链跳一次,看是否回到起点)
    alias_dict = {a: b for a, b in alias_pairs}
    for start in alias_dict:
        seen = {start}
        cur = alias_dict.get(start)
        while cur is not None and cur in alias_dict:
            if cur in seen:
                errors.append(
                    f"metric alias 形成循环: {' -> '.join(list(seen) + [cur])}"
                )
                break
            seen.add(cur)
            cur = alias_dict.get(cur)

    return errors


def validate_metrics_metadata(metrics: Optional[Dict[str, Any]]) -> List[str]:
    """
    校验 metrics{} 字典(每个 metric 的元数据)。

    Args:
        metrics: pipeline 的 metrics 字典,key=metric_id,value=元数据

    Returns:
        错误列表;空表示通过。
    """
    if not metrics:
        return []
    if not isinstance(metrics, dict):
        return [f"metrics 必须是对象,实际为 {type(metrics).__name__}"]

    errors: List[str] = []
    for metric_id, meta in metrics.items():
        if not isinstance(metric_id, str) or not metric_id.strip():
            errors.append(f"metric_id 必须是非空字符串,实际: {metric_id!r}")
            continue
        errors.extend(_validate_one_metric(metric_id, meta))

    # 跨 metric 校验:alias_of 引用一致性
    errors.extend(_validate_alias_references(metrics))

    return errors


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

    # ── metric 元数据深度校验(fail-fast for config-driven goal) ──
    errors.extend(validate_metrics_metadata(metrics))

    if not isinstance(steps, list) or not steps:
        errors.append("rules.steps 不能为空")
        return errors

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
            used_vars = extract_vars_from_definition(condition)
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
                    used_names = extract_vars_from_definition(condition)
                for vn in used_names:
                    if vn not in allowed_pipeline_vars:
                        errors.append(
                            f"step({sid}) next[{idx}] condition 引用未知变量 {vn!r}"
                            "（须为 metrics 键、某 step.metric_id、scene.metric_id 或某分支 set 键）"
                        )

    return errors
