# -*- coding: utf-8 -*-
"""
诊断引擎 (Diagnosis Engine)

核心执行器：加载规则 → 获取指标值 → 遍历决策树 → 输出诊断结果。

流程：
1. 根据 diagnosis_scenes.trigger_condition 匹配诊断场景
2. 从 pipeline 配置中的 metrics 定义获取各指标实际值
3. 从 start_node 开始，按 pipeline steps 的条件分支逐步推进
4. 到达叶子节点后，读取 result.rootCause 和 result.system
5. 汇总路径上所有指标的 {name, value, unit, status, threshold}

当前按 pipeline 配置中的 diagnosis_scenes.trigger_condition 动态匹配诊断场景。
"""
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from app.engine.rule_loader import RuleLoader
from app.engine.metric_fetcher import MetricFetcher, DEFAULT_FALLBACK_WINDOW_MINUTES
from app.engine.actions import call_action
from app.engine.condition_evaluator import (
    evaluate_boolean_condition_definition,
    evaluate_boolean_condition_text,
    evaluate_condition_definition,
    evaluate_condition_text,
    parse_condition_signature,
)

logger = logging.getLogger(__name__)


class DiagnosisResult:
    """诊断结果数据类"""

    def __init__(self):
        self.root_cause: Optional[str] = None
        self.system: Optional[str] = None
        self.error_field: str = ""          # 触发异常的指标 ID，逗号分隔
        self.metrics: List[Dict[str, Any]] = []  # [{name, value, unit, status, threshold}]
        self.trace: List[str] = []          # 诊断路径 step_id 列表
        self.is_diagnosed: bool = False     # 是否成功完成诊断
        self.category: Optional[str] = None
        self.reasoning: List[str] = []
        self.confidence: int = 0
        self.scene_id: Optional[Any] = None
        self.scene_module: Optional[str] = None
        self.scene_description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rootCause": self.root_cause,
            "system": self.system,
            "errorField": self.error_field,
            "metrics": self.metrics,
            "trace": self.trace,
            "isDiagnosed": self.is_diagnosed,
            "category": self.category,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "sceneId": self.scene_id,
            "sceneModule": self.scene_module,
            "sceneDescription": self.scene_description,
        }


class DiagnosisEngine:
    """
    诊断引擎

    对一条拒片故障记录执行基于 pipeline 配置的决策树推理，
    输出 rootCause、system、errorField 和详细 metrics 列表。
    """

    def __init__(
        self,
        time_window_minutes: int = DEFAULT_FALLBACK_WINDOW_MINUTES,
        pipeline_id: str = "reject_errors",
    ):
        """
        Args:
            time_window_minutes: 指标未配置 duration 时的回退窗口（分钟），默认 5
        """
        self.time_window_minutes = time_window_minutes
        self.pipeline_id = pipeline_id
        self.rule_loader = RuleLoader(pipeline_id=pipeline_id)
        # 最近一次诊断用到的 MetricFetcher 实例，service 层读取 source_log 用
        self._last_fetcher: Optional[MetricFetcher] = None

    @classmethod
    def can_diagnose(cls, reject_reason_id: int) -> bool:
        """只要存在配置场景，就允许进入场景触发判断。"""
        return True

    def diagnose(
        self,
        source_record: Dict[str, Any],
        reference_time: Optional[datetime] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> DiagnosisResult:
        """
        执行诊断

        Args:
            source_record: 源表记录字典，必须包含：
                - id, equipment, chuck_id, lot_id, wafer_index
                - wafer_product_start_time (datetime)
                - reject_reason (int)
                - wafer_transaction_X, wafer_transaction_y, wafer_rotation (可选)
            reference_time: 分析基准时间 T；未传则使用 wafer_product_start_time

        Returns:
            DiagnosisResult 诊断结果
        """
        result = DiagnosisResult()
        ref = reference_time
        if ref is None:
            ref = source_record.get("wafer_product_start_time")
        if isinstance(ref, str):
            ref = datetime.fromisoformat(ref)

        fetcher = MetricFetcher(
            equipment=source_record.get("equipment", ""),
            reference_time=ref,
            chuck_id=source_record.get("chuck_id"),
            fallback_duration_minutes=self.time_window_minutes,
            pipeline_id=self.pipeline_id,
            params=params,
            source_record=source_record,
        )
        self._last_fetcher = fetcher

        reject_reason_id = source_record.get("reject_reason")

        # 1. 匹配诊断场景（由 trigger_condition 驱动）
        scene = self._select_scene(source_record, fetcher)
        if scene is None:
            logger.info("reject_reason_id=%s 无匹配诊断场景", reject_reason_id)
            return result
        result.scene_id = scene.get("id")
        result.scene_module = scene.get("module")
        result.scene_description = scene.get("description")

        logger.info(
            "开始诊断: failure_id=%s, scene=%s (%s)",
            source_record.get("id"),
            scene.get("id"),
            scene.get("phenomenon"),
        )

        # 2. 获取所有相关指标值
        metric_ids = self.rule_loader.get_all_scene_metric_ids(scene)

        # 优先从源记录直接取值（Tx, Ty, Rw）
        metric_values = fetcher.fetch_from_source_record(source_record, metric_ids)

        logger.info("获取到 %d/%d 个指标值", sum(1 for v in metric_values.values() if v is not None), len(metric_ids))

        # 3. 遍历决策树
        start_node = str(scene.get("start_node", "1"))
        root_cause, system, trace, abnormal_metrics, final_context = self._walk_tree(
            start_node,
            metric_values,
            base_context={
                "equipment": source_record.get("equipment"),
                "chuck_id": source_record.get("chuck_id"),
                "lot_id": source_record.get("lot_id"),
                "wafer_index": source_record.get("wafer_index"),
                "reference_time": ref,
            },
        )

        result.root_cause = root_cause
        result.system = system
        result.trace = trace
        result.is_diagnosed = root_cause is not None
        leaf_result = final_context.get("__leaf_result__", {}) if isinstance(final_context, dict) else {}
        if isinstance(leaf_result, dict):
            result.category = leaf_result.get("category")
            result.reasoning = list(leaf_result.get("reasoning") or [])
            result.confidence = int(leaf_result.get("confidence") or (85 if result.is_diagnosed else 0))

        # 防御性兜底：如果有 rootCause 但 system 为空，赋默认值
        if result.root_cause and not result.system:
            result.system = "待确认"
            logger.warning(
                "诊断到 rootCause=%s 但 system 为空，使用默认值",
                result.root_cause,
            )

        # 4. 构建 metrics 列表（每个涉及的指标及其状态）
        result.metrics = self._build_metrics_list(metric_ids, final_context)

        # 5. 构建 errorField（触发异常判断的指标）
        error_fields = [m["name"] for m in result.metrics if m["status"] == "ABNORMAL"]
        result.error_field = ", ".join(error_fields) if error_fields else ""

        logger.info(
            "诊断完成: rootCause=%s, system=%s, errorField=%s, trace=%s",
            result.root_cause, result.system, result.error_field, result.trace,
        )

        return result

    def _select_scene(
        self,
        source_record: Dict[str, Any],
        fetcher: MetricFetcher,
    ) -> Optional[Dict[str, Any]]:
        """按 diagnosis_scenes.trigger_condition 顺序返回首个匹配场景。"""
        for scene in self.rule_loader.diagnosis_scenes:
            trigger_metric_ids = scene.get("metric_id") or []
            if isinstance(trigger_metric_ids, str):
                trigger_metric_ids = [trigger_metric_ids]
            if scene.get("default") and not trigger_metric_ids and not scene.get("trigger_condition"):
                return scene
            trigger_values = fetcher.fetch_from_source_record(source_record, trigger_metric_ids)

            trigger_conditions = scene.get("trigger_condition") or []
            if isinstance(trigger_conditions, str):
                trigger_conditions = [trigger_conditions]

            if not trigger_conditions:
                if trigger_metric_ids and all(trigger_values.get(mid) for mid in trigger_metric_ids):
                    return scene
                continue

            for condition in trigger_conditions:
                if evaluate_boolean_condition_definition(condition, trigger_values):
                    logger.info(
                        "匹配场景 scene=%s trigger_condition=%s values=%s",
                        scene.get("id"),
                        condition,
                        trigger_values,
                    )
                    return scene
        return None

    # ── 决策树遍历 ──────────────────────────────────────────────────────────

    def _walk_tree(
        self,
        start_node: str,
        metric_values: Dict[str, Optional[float]],
        base_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str], List[str], List[str], Dict[str, Any]]:
        """
        遍历 pipeline 的 steps 决策树

        Args:
            start_node: 起始节点 ID
            metric_values: 各指标的实际值

        Returns:
            (root_cause, system, trace_path, abnormal_metric_ids, final_context)
        """
        # context = 源记录上下文 + metric_values + actions/branch-set 动态追加变量
        context: Dict[str, Any] = dict(base_context or {})
        context.update(metric_values)
        return self._walk_subtree(start_node, context, [], [], max_steps=50)

    def _walk_subtree(
        self,
        start_node: str,
        context: Dict[str, Any],
        trace: List[str],
        abnormal_metrics: List[str],
        max_steps: int = 50,
    ) -> Tuple[Optional[str], Optional[str], List[str], List[str], Dict[str, Any]]:
        """执行单条子路径；若 target 为列表，则按独立分支顺序依次执行并共享 context。"""
        current_node = start_node

        for _ in range(max_steps):
            step = self.rule_loader.get_step(current_node)
            if step is None:
                logger.warning("步骤 %s 不存在，诊断中断", current_node)
                break

            trace.append(current_node)

            # 执行 details 中的 action 函数（顺序串行），更新 context
            context = self._execute_details(step, context)

            # 检查是否为叶子节点（有 result，兼容新旧格式）
            step_result = self.rule_loader.get_step_result(step)
            if step_result:
                context["__leaf_result__"] = step_result
                return (
                    step_result.get("rootCause"),
                    step_result.get("system"),
                    trace,
                    abnormal_metrics,
                    context,
                )

            # 如果 next 为空，视为终止节点
            next_branches = step.get("next", [])
            if not next_branches:
                logger.info("步骤 %s 无后续分支，诊断终止", current_node)
                desc = step.get("description", "")
                if "人工处理" in desc:
                    return ("需要人工处理", None, trace, abnormal_metrics, context)
                break

            # 评估分支条件，返回 (next_node, chosen_branch)
            next_node, chosen_branch = self._evaluate_branches(
                step, next_branches, context, abnormal_metrics
            )

            if next_node is None:
                logger.warning("步骤 %s 所有分支均不满足", current_node)
                break

            # 将 branch 的 set 字段注入 context（如 model_type）
            if chosen_branch and chosen_branch.get("set"):
                context.update(chosen_branch["set"])
                logger.debug("步骤 %s set context: %s", current_node, chosen_branch["set"])

            if isinstance(next_node, list):
                logger.info("多目标节点 %s → 执行全部子分支并汇总结果", next_node)
                chosen_result = None
                for child in next_node:
                    root_cause, system, child_trace, child_abnormal_metrics, context = self._walk_subtree(
                        str(child),
                        context,
                        [],
                        [],
                        max_steps=max_steps,
                    )
                    trace.extend(child_trace)
                    for metric_name in child_abnormal_metrics:
                        if metric_name not in abnormal_metrics:
                            abnormal_metrics.append(metric_name)
                    if (root_cause is not None or system is not None) and chosen_result is None:
                        chosen_result = (root_cause, system)
                if chosen_result is not None:
                    return chosen_result[0], chosen_result[1], trace, abnormal_metrics, context
                return (None, None, trace, abnormal_metrics, context)
            else:
                current_node = str(next_node)

        return (None, None, trace, abnormal_metrics, context)

    def _execute_details(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        按顺序执行 step.details 中的 action 函数，将 results 合并到 context。

        Args:
            step:    当前步骤
            context: 当前执行上下文（in-place 修改后返回）

        Returns:
            更新后的 context
        """
        details = step.get("details") or []
        for item in details:
            action_name = item.get("action")
            if not action_name:
                continue
            params = item.get("params") or {}
            outputs = call_action(action_name, params, context)
            normalized_outputs = self._normalize_action_outputs(step, item, outputs)
            if normalized_outputs:
                context.update(normalized_outputs)
                logger.debug(
                    "步骤 %s action '%s' outputs: %s",
                    step.get("id"), action_name, normalized_outputs,
                )
        return context

    @staticmethod
    def _normalize_action_outputs(
        step: Dict[str, Any],
        detail_item: Dict[str, Any],
        outputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        action 输出默认全部进入 context。

        results 声明仅作为契约校验，而不是白名单过滤。
        """
        if not outputs:
            return {}

        declared = detail_item.get("results")
        if not isinstance(declared, dict) or not declared:
            return outputs

        missing = [k for k in declared.keys() if k not in outputs]
        if missing:
            logger.warning(
                "步骤 %s action '%s' 缺少声明输出字段: %s",
                step.get("id"),
                detail_item.get("action"),
                ",".join(missing),
            )
        return outputs

    @staticmethod
    def _extract_condition_var(condition: Any) -> Optional[str]:
        """从 condition 字符串提取 {var_name} 中的变量名。

        例: '-2<{mean_Tx}<2' → 'mean_Tx'
             '{Mwx_0} > 1.0' → 'Mwx_0'
        """
        if isinstance(condition, dict):
            compare = condition.get("compare")
            if isinstance(compare, dict) and compare.get("left"):
                return str(compare.get("left"))
            return None
        m = re.search(r"\{([^}]+)\}", str(condition))
        return m.group(1).strip() if m else None

    def _evaluate_branches(
        self,
        step: Dict[str, Any],
        branches: List[Dict[str, Any]],
        context: Dict[str, Any],
        abnormal_metrics: List[str],
    ) -> Tuple[Optional[Any], Optional[Dict]]:
        """
        评估步骤的分支条件，返回 (next_node_id, chosen_branch)。

        变量查找规则（优先级从高到低）：
          1. condition 字符串中的 {var_name}
          2. step.metric_id
        都在 context 中查找，context 包含 metric_values + action outputs + set注入

        Args:
            step:             当前步骤
            branches:         分支列表
            context:          当前执行上下文
            abnormal_metrics: 异常指标列表（会被修改）

        Returns:
            (next_node_id, chosen_branch_dict) 或 (None, None)
        """
        metric_id = step.get("metric_id")
        else_branch = None
        else_branch_obj = None
        matched_branches: List[Tuple[Any, Dict[str, Any], Optional[str], str, Any, Any]] = []

        for branch in branches:
            condition = branch.get("condition", "")
            operator = branch.get("operator", "")
            limit = branch.get("limit")
            target = branch.get("target")

            # else 分支留到最后
            if condition == "else" or (not operator and not condition):
                else_branch = target
                else_branch_obj = branch
                continue

            # 优先从 condition 字符串提取变量名，回退到 metric_id
            var_name = self._extract_condition_var(condition) or metric_id
            value = context.get(var_name) if var_name else None

            if operator:
                if value is None:
                    continue
                matched = self._eval_condition(value, operator, limit)
            else:
                matched, parsed_var, parsed_operator, parsed_limit, parsed_value = evaluate_condition_definition(
                    condition, context, metric_id
                )
                if parsed_var:
                    var_name = parsed_var
                if parsed_operator:
                    operator = parsed_operator
                    limit = parsed_limit
                if parsed_value is not None:
                    value = parsed_value

            if matched:
                matched_branches.append((target, branch, var_name, operator, limit, value))

        # next 分支是独立条件：应只命中 1 条
        if len(matched_branches) == 1:
            target, branch, var_name, operator, limit, value = matched_branches[0]
            if var_name and self._is_abnormal_branch(operator, limit, value):
                abnormal_metrics.append(var_name)
            return target, branch

        # 若命中多条，说明规则配置冲突（不依赖 next 顺序），中断并回退到 else（若存在）
        if len(matched_branches) > 1:
            matched_targets = [str(item[0]) for item in matched_branches]
            logger.error(
                "步骤 %s 命中多个 next 分支(条件冲突): targets=%s",
                step.get("id"),
                ",".join(matched_targets),
            )
            if else_branch is not None:
                return else_branch, else_branch_obj
            return None, None

        # 所有条件都不满足，走 else
        if else_branch is not None:
            return else_branch, else_branch_obj

        return None, None

    def _eval_condition(
        self, value: float, operator: str, limit: Any
    ) -> bool:
        """评估单个条件"""
        try:
            if operator == ">":
                return value > float(limit)
            elif operator == "<":
                return value < float(limit)
            elif operator == ">=":
                return value >= float(limit)
            elif operator == "<=":
                return value <= float(limit)
            elif operator == "between":
                if isinstance(limit, list) and len(limit) == 2:
                    return float(limit[0]) < value < float(limit[1])
            elif operator == "==" or operator == "=":
                return abs(value - float(limit)) < 1e-9
            else:
                logger.warning("未知操作符: %s", operator)
                return False
        except (TypeError, ValueError) as e:
            logger.warning("条件评估失败: value=%s, op=%s, limit=%s, error=%s", value, operator, limit, e)
            return False

    def _is_abnormal_branch(
        self, operator: str, limit: Any, value: float
    ) -> bool:
        """
        判断当前分支是否代表"异常"路径

        简单启发式：如果条件是极端值比较，视为异常。
        """
        # between 条件通常是正常范围
        if operator == "between":
            return False
        # > 或 < 极限值通常是异常
        if operator in (">", "<", ">=", "<="):
            return True
        return False

    # ── 构建指标列表 ────────────────────────────────────────────────────────

    # 场景触发条件识别字段：仅用于判断是否进入诊断场景，不作为诊断指标展示
    def _build_metrics_list(
        self,
        metric_ids: List[str],
        metric_values: Dict[str, Optional[float]],
    ) -> List[Dict[str, Any]]:
        """
        构建接口3返回的 metrics 数组

        对每个指标，从最终执行上下文中读取值，并结合 pipeline steps 查找阈值条件，
        评估 status (NORMAL/ABNORMAL)。

        排除规则：
        1. 场景触发条件识别字段（_SCENE_TRIGGER_FIELDS）：仅用于触发诊断，不展示
        2. 无实际值的指标：值为 None 则跳过
        3. 不在 pipeline metrics 中的指标：无元数据则跳过

        Args:
            metric_ids: 指标 ID 列表
            metric_values: 指标实际值

        Returns:
            [{name, value, unit, status, threshold: {operator, limit}}]
        """
        metrics = []

        # 只展示有实际值且在 pipeline metrics 中有定义的指标
        for mid in metric_ids:
            meta = self.rule_loader.get_metric_meta(mid)
            if meta is None:
                continue
            if meta.get("role") == "trigger_only":
                continue

            value = metric_values.get(mid)
            if value is None:
                continue

            unit = meta.get("unit", "") or ""

            # 查找阈值（从 pipeline steps 中找）
            threshold_info = self._find_threshold(mid)

            # 有阈值 → 诊断指标；无阈值 → 建模输入参数
            metric_type = "diagnostic" if threshold_info else "model_param"

            # 判定 status（仅诊断指标才有意义）
            status = "NORMAL"
            if threshold_info:
                op = threshold_info["operator"]
                limit_val = threshold_info["limit"]
                if not self._is_within_normal_range(value, op, limit_val):
                    status = "ABNORMAL"

            metrics.append({
                "name": mid,
                "value": round(value, 6) if isinstance(value, (int, float)) else value,
                "unit": unit,
                "status": status,
                "type": metric_type,
                "approximate": bool(meta.get("approximate")),
                "threshold": threshold_info or {"operator": "-", "limit": 0},
            })

        # 排序：诊断指标在前（ABNORMAL 置顶），建模参数在后
        metrics.sort(key=lambda x: (
            0 if x["type"] == "diagnostic" and x["status"] == "ABNORMAL" else
            1 if x["type"] == "diagnostic" else
            2
        ))

        return metrics

    # output_* 是 MetricFetcher 的内部别名，pipeline steps 中用的是原始名
    _METRIC_ALIAS_MAP = {
        "output_Tx": "Tx",
        "output_Ty": "Ty",
        "output_Rw": "Rw",
        # output_Mw 不做别名映射，pipeline step 21 直接用 "output_Mw" 作为 metric_id
    }

    def _find_threshold(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """
        从 pipeline steps 中查找指标的阈值条件

        查找优先级：
        1. 优先返回 between 条件（正常范围，如 -20 < Tx < 20）
        2. 其次返回第一个有 operator+limit 的分支（如 n_88um ≤ 8）

        对于 output_Tx/Ty/Rw/Mw 等别名，自动映射到 pipeline 中的原始名。

        Args:
            metric_id: 指标 ID

        Returns:
            {"operator": str, "limit": float/list} 或 None
        """
        # 别名映射：output_Tx → Tx 等
        lookup_id = self._METRIC_ALIAS_MAP.get(metric_id, metric_id)

        for step in self.rule_loader.steps:
            step_metric_id = step.get("metric_id")
            branches = step.get("next", [])
            parsed_branches = []
            for branch in branches:
                condition = str(branch.get("condition", "")).strip()
                if not condition or condition == "else":
                    continue
                signature = parse_condition_signature(condition)
                if not signature:
                    continue
                sig_type = signature.get("type")
                if sig_type == "range":
                    parsed_branches.append(
                        {
                            "var": signature.get("var"),
                            "operator": "between",
                            "limit": signature.get("limit"),
                            "condition": condition,
                        }
                    )
                    continue
                if sig_type == "comparison":
                    rhs_var = signature.get("rhs_var")
                    rhs_value = signature.get("rhs")
                    if rhs_var is not None or rhs_value is None:
                        continue
                    parsed_branches.append(
                        {
                            "var": signature.get("var"),
                            "operator": signature.get("operator"),
                            "limit": rhs_value,
                            "condition": condition,
                        }
                    )

            branch_refs_lookup = any(str(item.get("var")) == lookup_id for item in parsed_branches)
            if step_metric_id != lookup_id and not branch_refs_lookup:
                continue

            valid_branches = []
            for branch in parsed_branches:
                op = str(branch.get("operator", "")).strip()
                limit = branch.get("limit")
                condition = str(branch.get("condition", "")).strip()
                branch_var = str(branch.get("var", "")).strip()
                if branch_refs_lookup and branch_var != lookup_id:
                    continue
                if op and limit is not None:
                    valid_branches.append(
                        {
                            "operator": op,
                            "limit": limit,
                            "condition": condition,
                        }
                    )

            if not valid_branches:
                continue

            between_branches = [b for b in valid_branches if b.get("operator", "") == "between"]
            comparison_branches = [
                b for b in valid_branches if b.get("operator", "") in {">", "<", ">=", "<=", "==", "!="}
            ]

            # Mwx_0 这类“多个有效区间/边界共同组成正常条件”的步骤，不能错误折叠成单个 between。
            if len(between_branches) > 1 or (between_branches and comparison_branches):
                conditions = [
                    {"operator": b.get("operator", ""), "limit": b.get("limit")}
                    for b in valid_branches
                ]
                display = " or ".join(
                    str(b.get("condition", "")).strip() for b in valid_branches if b.get("condition")
                )
                return {"operator": "any_of", "limit": conditions, "display": display}

            # 次优：单独 between 分支（如 output_Mw between [-20, 20]）
            for branch in valid_branches:
                op = branch.get("operator", "")
                limit = branch.get("limit")
                if op == "between" and isinstance(limit, list):
                    return {
                        "operator": "between",
                        "limit": limit,
                        "display": str(branch.get("condition", "")).strip() or None,
                    }

            # 末选：第一个有 operator 的分支（≤、≥ 等，如 n_88um ≤ 8）
            for branch in valid_branches:
                op = branch.get("operator", "")
                limit = branch.get("limit")
                condition = branch.get("condition", "")
                if op and limit is not None:
                    return {
                        "operator": op,
                        "limit": limit,
                        "display": str(condition).strip() or None,
                    }

        return None

    def _is_within_normal_range(
        self, value: float, operator: str, limit: Any
    ) -> bool:
        """
        判断值是否在正常范围内

        operator 表示"正常条件"，值满足该条件为 NORMAL，否则为 ABNORMAL。

        between [lo, hi] → lo <= value <= hi 为 NORMAL
        ≤ limit          → value <= limit 为 NORMAL（如 n_88um ≤ 8）
        < limit          → value < limit 为 NORMAL
        > limit          → value > limit 为 NORMAL
        >= limit         → value >= limit 为 NORMAL
        """
        try:
            if operator == "any_of":
                if isinstance(limit, list):
                    return any(
                        self._is_within_normal_range(
                            value,
                            str(item.get("operator", "")),
                            item.get("limit"),
                        )
                        for item in limit
                        if isinstance(item, dict)
                    )
            if operator == "between":
                if isinstance(limit, list) and len(limit) == 2:
                    return float(limit[0]) < value < float(limit[1])
            elif operator == "<=":
                return value <= float(limit)
            elif operator == "<":
                return value < float(limit)
            elif operator == ">":
                return value > float(limit)
            elif operator == ">=":
                return value >= float(limit)
        except (TypeError, ValueError):
            pass
        return True  # 默认正常
