# -*- coding: utf-8 -*-
"""
诊断引擎 (Diagnosis Engine)

核心执行器：加载规则 → 获取指标值 → 遍历决策树 → 输出诊断结果。

流程：
1. 根据 reject_reason_id 匹配诊断场景 (diagnosis_scene)
2. 从 metrics.json 配置的数据源获取各指标实际值
3. 从 start_node 开始，按 rules.json steps 的条件分支逐步推进
4. 到达叶子节点后，读取 result.rootCause 和 result.system
5. 汇总路径上所有指标的 {name, value, unit, status, threshold}

当前仅支持 COARSE_ALIGN_FAILED (reject_reason_id=6) 的诊断。
"""
import logging
import re
import ast
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from app.engine.rule_loader import RuleLoader
from app.engine.metric_fetcher import MetricFetcher, DEFAULT_FALLBACK_WINDOW_MINUTES
from app.engine.actions import call_action

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rootCause": self.root_cause,
            "system": self.system,
            "errorField": self.error_field,
            "metrics": self.metrics,
            "trace": self.trace,
            "isDiagnosed": self.is_diagnosed,
        }


class DiagnosisEngine:
    """
    诊断引擎

    对一条拒片故障记录执行基于 rules.json 的决策树推理，
    输出 rootCause、system、errorField 和详细 metrics 列表。
    """

    # 当前支持诊断的拒片原因 ID
    SUPPORTED_REJECT_REASONS = {6}  # COARSE_ALIGN_FAILED

    def __init__(
        self,
        time_window_minutes: int = DEFAULT_FALLBACK_WINDOW_MINUTES,
    ):
        """
        Args:
            time_window_minutes: metrics.json 未配置 duration 时的回退窗口（分钟），默认 5
        """
        self.time_window_minutes = time_window_minutes
        self.rule_loader = RuleLoader()
        # 最近一次诊断用到的 MetricFetcher 实例，service 层读取 source_log 用
        self._last_fetcher: Optional[MetricFetcher] = None

    @classmethod
    def can_diagnose(cls, reject_reason_id: int) -> bool:
        """判断某个拒片原因是否支持自动诊断"""
        return reject_reason_id in cls.SUPPORTED_REJECT_REASONS

    def diagnose(
        self,
        source_record: Dict[str, Any],
        reference_time: Optional[datetime] = None,
    ) -> DiagnosisResult:
        """
        执行诊断

        Args:
            source_record: 源表记录字典，必须包含：
                - id, equipment, chuck_id, lot_id, wafer_id
                - wafer_product_start_time (datetime)
                - reject_reason (int)
                - wafer_transaction_X, wafer_transaction_y, wafer_rotation (可选)
            reference_time: 分析基准时间 T；未传则使用 wafer_product_start_time

        Returns:
            DiagnosisResult 诊断结果
        """
        result = DiagnosisResult()
        reject_reason_id = source_record.get("reject_reason")

        # 1. 匹配诊断场景
        scene = self.rule_loader.get_scene_by_reject_reason(reject_reason_id)
        if scene is None:
            logger.info("reject_reason_id=%s 无匹配诊断场景", reject_reason_id)
            return result

        logger.info(
            "开始诊断: failure_id=%s, scene=%s (%s)",
            source_record.get("id"),
            scene.get("id"),
            scene.get("phenomenon"),
        )

        # 2. 获取所有相关指标值
        metric_ids = self.rule_loader.get_all_scene_metric_ids(scene)
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
        )
        self._last_fetcher = fetcher

        # 优先从源记录直接取值（Tx, Ty, Rw）
        metric_values = fetcher.fetch_from_source_record(source_record, metric_ids)

        logger.info("获取到 %d/%d 个指标值", sum(1 for v in metric_values.values() if v is not None), len(metric_ids))

        # 3. 遍历决策树
        start_node = str(scene.get("start_node", "1"))
        root_cause, system, trace, abnormal_metrics = self._walk_tree(
            start_node, metric_values
        )

        result.root_cause = root_cause
        result.system = system
        result.trace = trace
        result.is_diagnosed = root_cause is not None

        # 防御性兜底：如果有 rootCause 但 system 为空，赋默认值
        if result.root_cause and not result.system:
            result.system = "待确认"
            logger.warning(
                "诊断到 rootCause=%s 但 system 为空，使用默认值",
                result.root_cause,
            )

        # 4. 构建 metrics 列表（每个涉及的指标及其状态）
        result.metrics = self._build_metrics_list(metric_ids, metric_values)

        # 5. 构建 errorField（触发异常判断的指标）
        error_fields = [m["name"] for m in result.metrics if m["status"] == "ABNORMAL"]
        result.error_field = ", ".join(error_fields) if error_fields else ""

        logger.info(
            "诊断完成: rootCause=%s, system=%s, errorField=%s, trace=%s",
            result.root_cause, result.system, result.error_field, result.trace,
        )

        return result

    # ── 决策树遍历 ──────────────────────────────────────────────────────────

    def _walk_tree(
        self,
        start_node: str,
        metric_values: Dict[str, Optional[float]],
    ) -> Tuple[Optional[str], Optional[str], List[str], List[str]]:
        """
        遍历 rules.json 的 steps 决策树

        Args:
            start_node: 起始节点 ID
            metric_values: 各指标的实际值

        Returns:
            (root_cause, system, trace_path, abnormal_metric_ids)
        """
        trace = []
        abnormal_metrics = []
        current_node = start_node
        max_steps = 50  # 防止死循环

        # context = metric_values 的副本 + actions/branch-set 动态追加的变量
        context: Dict[str, Any] = dict(metric_values)

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
                return (
                    step_result.get("rootCause"),
                    step_result.get("system"),
                    trace,
                    abnormal_metrics,
                )

            # 如果 next 为空，视为终止节点
            next_branches = step.get("next", [])
            if not next_branches:
                logger.info("步骤 %s 无后续分支，诊断终止", current_node)
                desc = step.get("description", "")
                if "人工处理" in desc:
                    return ("需要人工处理", None, trace, abnormal_metrics)
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

            # 如果 target 是列表（并行检查），选择异常指标优先的子节点
            if isinstance(next_node, list):
                selected = self._select_parallel_node(next_node, context)
                current_node = str(selected)
                logger.info("并行节点 %s → 选中 %s", next_node, current_node)
            else:
                current_node = str(next_node)

        return (None, None, trace, abnormal_metrics)

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
        按 details.results 声明规范 action 输出字段。

        - 若未声明 results，则保留 action 全量返回字段。
        - 若声明了 results(dict)，只接收声明内字段，避免脏字段污染上下文。
        """
        if not outputs:
            return {}

        declared = detail_item.get("results")
        if not isinstance(declared, dict) or not declared:
            return outputs

        normalized = {k: outputs[k] for k in declared.keys() if k in outputs}
        missing = [k for k in declared.keys() if k not in outputs]
        if missing:
            logger.warning(
                "步骤 %s action '%s' 缺少声明输出字段: %s",
                step.get("id"),
                detail_item.get("action"),
                ",".join(missing),
            )
        return normalized

    @staticmethod
    def _extract_condition_var(condition: str) -> Optional[str]:
        """从 condition 字符串提取 {var_name} 中的变量名。

        例: '-2<{mean_Tx}<2' → 'mean_Tx'
             '{Mwx_0} > 1.0' → 'Mwx_0'
        """
        m = re.search(r'\{(\w+)\}', condition)
        return m.group(1) if m else None

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
                matched, parsed_var, parsed_operator, parsed_limit, parsed_value = (
                    self._eval_condition_by_text(condition, context, metric_id)
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

    def _eval_condition_by_text(
        self,
        condition: str,
        context: Dict[str, Any],
        fallback_metric_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], str, Any, Any]:
        """
        直接解析 condition 文本（无 operator/limit 时）。

        支持：
        - 区间表达式: -300<{mean_Rw}<300
        - 比较表达式: {model_type} == '88um' / normal_count==3 / n_88um≤8
        - 空串条件: 视为无条件命中
        """
        expr = (condition or "").strip()
        if not expr:
            return True, fallback_metric_id, "", None, None

        normalized = expr.replace("≤", "<=").replace("≥", ">=")

        # 1) 区间表达式: low < {var} < high
        range_match = re.match(
            r"^\s*(-?\d+(?:\.\d+)?)\s*<\s*\{?([A-Za-z_]\w*)\}?\s*<\s*(-?\d+(?:\.\d+)?)\s*$",
            normalized,
        )
        if range_match:
            low = float(range_match.group(1))
            var_name = range_match.group(2)
            high = float(range_match.group(3))
            value = context.get(var_name)
            if value is None:
                return False, var_name, "between", [low, high], None
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return False, var_name, "between", [low, high], value
            return low < numeric_value < high, var_name, "between", [low, high], numeric_value

        # 2) 单变量比较表达式
        compare_match = re.match(
            r"^\s*\{?([A-Za-z_]\w*)\}?\s*(==|=|!=|<=|>=|<|>)\s*(.+)\s*$",
            normalized,
        )
        if compare_match:
            var_name = compare_match.group(1)
            operator = compare_match.group(2)
            rhs_raw = compare_match.group(3).strip()
            left_value = context.get(var_name)
            if left_value is None:
                return False, var_name, operator, rhs_raw, None

            right_value = self._parse_condition_literal(rhs_raw)
            return (
                self._eval_comparison(left_value, operator, right_value),
                var_name,
                operator,
                right_value,
                left_value,
            )

        logger.warning("无法解析 condition 表达式: %s", condition)
        return False, fallback_metric_id, "", None, None

    @staticmethod
    def _parse_condition_literal(token: str) -> Any:
        """解析条件字面量，支持数字、布尔、引号字符串。"""
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

    @staticmethod
    def _eval_comparison(left: Any, operator: str, right: Any) -> bool:
        """评估比较表达式，优先按数值比较，失败后回退为字符串比较。"""
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

    def _select_parallel_node(
        self,
        targets: list,
        context: Dict[str, Any],
    ) -> Any:
        """
        从并行目标节点列表中选择应该追踪的节点

        优先选择指标值异常（不在正常范围内）的子节点，
        因为异常路径才会到达有 rootCause 的叶子节点。

        Args:
            targets: 并行目标节点 ID 列表（如 ["22", "23", "24"]）
            context: 当前执行上下文

        Returns:
            选中的节点 ID
        """
        first_abnormal = None
        first_normal = None

        for target_id in targets:
            step = self.rule_loader.get_step(str(target_id))
            if step is None:
                continue

            metric_id = step.get("metric_id")
            value = context.get(metric_id) if metric_id else None

            if value is None:
                continue

            # 在该步骤的分支中查找 "between" 条件（正常范围）
            is_normal = True
            for branch in step.get("next", []):
                op = branch.get("operator", "")
                limit = branch.get("limit")
                if op == "between" and isinstance(limit, list) and len(limit) == 2:
                    if not (float(limit[0]) < value < float(limit[1])):
                        is_normal = False
                    break

            if not is_normal and first_abnormal is None:
                first_abnormal = target_id
                logger.info(
                    "并行节点 %s: 指标 %s=%s 异常（超出正常范围）",
                    target_id, metric_id, value,
                )
            elif is_normal and first_normal is None:
                first_normal = target_id

        # 优先返回异常节点，其次正常节点，最后兜底第一个
        return first_abnormal or first_normal or targets[0]

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
            elif operator == "≤":
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
        if operator in (">", "<", ">=", "<=", "≤"):
            return True
        return False

    # ── 构建指标列表 ────────────────────────────────────────────────────────

    # 场景触发条件识别字段：仅用于判断是否进入诊断场景，不作为诊断指标展示
    _SCENE_TRIGGER_FIELDS = {
        "Coarse Alignment Failed",
        "Mwx out of range,CGG6_check_parameter_ranges",
    }

    def _build_metrics_list(
        self,
        metric_ids: List[str],
        metric_values: Dict[str, Optional[float]],
    ) -> List[Dict[str, Any]]:
        """
        构建接口3返回的 metrics 数组

        对每个指标，从 rules.json 查找阈值条件，
        评估 status (NORMAL/ABNORMAL)。

        排除规则：
        1. 场景触发条件识别字段（_SCENE_TRIGGER_FIELDS）：仅用于触发诊断，不展示
        2. 无实际值的指标：值为 None 则跳过
        3. 不在 metrics.json 中的指标：无元数据则跳过

        Args:
            metric_ids: 指标 ID 列表
            metric_values: 指标实际值

        Returns:
            [{name, value, unit, status, threshold: {operator, limit}}]
        """
        metrics = []

        # 只展示有实际值且在 metrics.json 中有定义的指标
        for mid in metric_ids:
            # 排除触发条件识别字段
            if mid in self._SCENE_TRIGGER_FIELDS:
                continue

            meta = self.rule_loader.get_metric_meta(mid)
            if meta is None:
                continue

            value = metric_values.get(mid)
            if value is None:
                continue

            unit = meta.get("unit", "") or ""

            # 查找阈值（从 rules.json 步骤中找）
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
                "value": round(value, 6),
                "unit": unit,
                "status": status,
                "type": metric_type,
                "threshold": threshold_info or {"operator": "-", "limit": 0},
            })

        # 排序：诊断指标在前（ABNORMAL 置顶），建模参数在后
        metrics.sort(key=lambda x: (
            0 if x["type"] == "diagnostic" and x["status"] == "ABNORMAL" else
            1 if x["type"] == "diagnostic" else
            2
        ))

        return metrics

    # output_* 是 MetricFetcher 的内部别名，rules.json 中用的是原始名
    _METRIC_ALIAS_MAP = {
        "output_Tx": "Tx",
        "output_Ty": "Ty",
        "output_Rw": "Rw",
        # output_Mw 不做别名映射，rules.json step 21 直接用 "output_Mw" 作为 metric_id
    }

    def _find_threshold(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """
        从 rules.json steps 中查找指标的阈值条件

        查找优先级：
        1. 优先返回 between 条件（正常范围，如 -20 < Tx < 20）
        2. 其次返回第一个有 operator+limit 的分支（如 n_88um ≤ 8）

        对于 output_Tx/Ty/Rw/Mw 等别名，自动映射到 rules.json 中的原始名。

        Args:
            metric_id: 指标 ID

        Returns:
            {"operator": str, "limit": float/list} 或 None
        """
        # 别名映射：output_Tx → Tx 等
        lookup_id = self._METRIC_ALIAS_MAP.get(metric_id, metric_id)

        for step in self.rule_loader.steps:
            if step.get("metric_id") != lookup_id:
                continue

            branches = step.get("next", [])

            # 优先：step 中若同时存在 > 和 < 两个边界（如 Mwx_0），
            # 取它们的 [lo, hi] 作为正常范围，而不是 between（between 在此是分支路径，非正常范围）
            upper_limit = None  # 来自 > 条件的上边界
            lower_limit = None  # 来自 < 条件的下边界
            for branch in branches:
                op = branch.get("operator", "")
                limit = branch.get("limit")
                if op == ">" and limit is not None:
                    upper_limit = float(limit)
                elif op == "<" and limit is not None:
                    lower_limit = float(limit)
            if upper_limit is not None and lower_limit is not None:
                # 同时有上下界 → 正常范围是 [lower, upper]
                return {"operator": "between", "limit": [lower_limit, upper_limit]}

            # 次优：单独 between 分支（如 output_Mw between [-20, 20]）
            for branch in branches:
                op = branch.get("operator", "")
                limit = branch.get("limit")
                if op == "between" and isinstance(limit, list):
                    return {"operator": "between", "limit": limit}

            # 末选：第一个有 operator 的分支（≤、≥ 等，如 n_88um ≤ 8）
            for branch in branches:
                op = branch.get("operator", "")
                limit = branch.get("limit")
                condition = branch.get("condition", "")
                if op and limit is not None and condition != "else":
                    return {"operator": op, "limit": limit}

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
            if operator == "between":
                if isinstance(limit, list) and len(limit) == 2:
                    return float(limit[0]) <= value <= float(limit[1])
            elif operator == "≤" or operator == "<=":
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
