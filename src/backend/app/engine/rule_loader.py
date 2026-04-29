import logging
from typing import Dict, List, Any, Optional
from app.diagnosis.config_store import DiagnosisConfigStore
from app.engine.condition_evaluator import extract_vars_from_definition

logger = logging.getLogger(__name__)

class RuleLoader:
    """
    统一诊断配置视图。

    基于 DiagnosisConfigStore 暴露当前 pipeline 的场景、步骤和指标元数据，
    兼容历史调用方的读取方式。
    """

    def __init__(self, pipeline_id: str = "reject_errors") -> None:
        self.pipeline_id = pipeline_id
        self.store = DiagnosisConfigStore()
        bundle = self.store.get_pipeline(pipeline_id)
        self.rules_version = bundle.get("version", "unknown")
        self.diagnosis_scenes = bundle.get("diagnosis_scenes", [])
        self.steps = bundle.get("steps", [])
        self.steps_map = bundle.get("steps_map", {})
        self.metrics_meta = bundle.get("metrics", {})
        self.default_scene_id = bundle.get("default_scene_id")
        logger.info(
            "RuleLoader 初始化完成: pipeline=%s scenes=%d steps=%d metrics=%d",
            pipeline_id,
            len(self.diagnosis_scenes),
            len(self.steps),
            len(self.metrics_meta),
        )

    # ── 查询接口 ────────────────────────────────────────────────────────────

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """根据 step_id 获取步骤定义"""
        return self.steps_map.get(str(step_id))

    def get_metric_meta(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """根据 metric_id 获取指标元数据"""
        return self.metrics_meta.get(metric_id)

    def get_all_scene_metric_ids(self, scene: Dict[str, Any]) -> List[str]:
        """
        获取诊断场景涉及的所有 metric_id

        遍历 scene 的 start_node 所引出的所有 steps，
        收集每个 step 的 metric_id 以及 params 中的指标。

        Args:
            scene: 诊断场景字典

        Returns:
            去重后的 metric_id 列表
        """
        metric_ids = set()

        # 场景触发条件涉及的指标
        for mid in scene.get("metric_id", []):
            metric_ids.add(mid)

        # BFS 遍历所有 steps
        visited = set()
        queue = [str(scene.get("start_node", "1"))]

        while queue:
            sid = queue.pop(0)
            if sid in visited:
                continue
            visited.add(sid)

            step = self.get_step(sid)
            if step is None:
                continue

            # 收集当前步骤的 metric_id
            step_metric = step.get("metric_id")
            if step_metric:
                metric_ids.add(step_metric)

            # 收集 params 中的指标（建模步骤，兼容新旧格式）
            params = self.get_step_params(step)
            for param_name in params.keys():
                metric_ids.add(param_name)
            for raw_value in params.values():
                for var_name in extract_vars_from_definition(raw_value):
                    metric_ids.add(var_name)

            # 收集 details 中的输出 results（新格式建模步骤的输出指标）
            output_results = self.get_step_output_results(step)
            for result_key in output_results.keys():
                metric_ids.add(result_key)

            # 遍历 next 分支（显式 "next": null 时 .get("next", []) 仍为 None，需 or []）
            for branch in step.get("next") or []:
                target = branch.get("target")
                if target is None:
                    continue
                if isinstance(target, list):
                    for t in target:
                        queue.append(str(t))
                else:
                    queue.append(str(target))

                # 旧格式：分支的 results 中的输出指标
                results = branch.get("results", {})
                for result_key in results.keys():
                    metric_ids.add(result_key)
                for var_name in extract_vars_from_definition(branch.get("condition")):
                    metric_ids.add(var_name)

        return list(metric_ids)

    # ── 新旧格式兼容辅助 ────────────────────────────────────────────────────

    @staticmethod
    def get_step_result(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从 step 中提取 result（兼容新旧两种格式）。
        旧格式：step["result"]
        新格式：step["details"][0]["result"] 或 step["details"][0]["results"]（rootCause 在其中）
        """
        # 旧格式
        if step.get("result"):
            return step["result"]
        # 新格式
        details = step.get("details") or []
        if details and isinstance(details, list):
            d = details[0] if details else {}
            if d.get("result"):
                return d["result"]
            # Node 99 用 "results" 而非 "result"
            results = d.get("results") or {}
            if "rootCause" in results:
                return results
        return None

    @staticmethod
    def get_step_params(step: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 step 中提取建模 params（兼容新旧两种格式）。
        旧格式：step["params"]
        新格式：step["details"][0]["params"]
        """
        if step.get("params"):
            return step["params"]
        details = step.get("details") or []
        if details and isinstance(details, list):
            return (details[0] or {}).get("params") or {}
        return {}

    @staticmethod
    def get_step_output_results(step: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 step 中提取建模输出 results（兼容新旧两种格式）。
        旧格式：next[0]["results"]
        新格式：step["details"][0]["results"]
        """
        details = step.get("details") or []
        if details and isinstance(details, list):
            return (details[0] or {}).get("results") or {}
        return {}

    def get_leaf_nodes(self) -> List[Dict[str, Any]]:
        """获取所有叶子节点（有 result 字段的步骤，兼容新旧格式）"""
        return [s for s in self.steps if self.get_step_result(s)]

    def reload(self) -> None:
        """强制重新加载配置文件"""
        self.store.reload()
        bundle = self.store.get_pipeline(self.pipeline_id)
        self.rules_version = bundle.get("version", "unknown")
        self.diagnosis_scenes = bundle.get("diagnosis_scenes", [])
        self.steps = bundle.get("steps", [])
        self.steps_map = bundle.get("steps_map", {})
        self.metrics_meta = bundle.get("metrics", {})
        self.default_scene_id = bundle.get("default_scene_id")
