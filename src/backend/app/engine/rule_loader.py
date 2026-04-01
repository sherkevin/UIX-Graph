"""
规则加载器 (Rule Loader)

加载并解析 config/rules.json 和 config/metrics.json，
提供结构化的规则树和指标元数据。
"""
import json
import os
import logging
from typing import Dict, List, Any, Optional
from app.engine.actions import has_action
from app.engine.rule_validator import validate_rules_config

logger = logging.getLogger(__name__)

# ── 配置文件路径 ────────────────────────────────────────────────────────────
# 优先使用 UIX_ROOT（单文件 exe 解包目录），否则按源码相对路径回退。
_UIX_ROOT = os.environ.get("UIX_ROOT")
if _UIX_ROOT:
    _PROJECT_ROOT = _UIX_ROOT
    _CONFIG_DIR = os.path.join(_UIX_ROOT, "config")
else:
    # 从 src/backend/app/engine/ 向上 4 层到 UIX/
    _PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    _CONFIG_DIR = os.path.join(_PROJECT_ROOT, "config")

# 规则文件：优先使用 config/rules.json（主文件），回退到根目录 rejection_rules.json
_RULES_PATH_MAIN = os.path.join(_CONFIG_DIR, "rules.json")
_RULES_PATH_FALLBACK = os.path.join(_PROJECT_ROOT, "rejection_rules.json")
_RULES_PATH = _RULES_PATH_MAIN if os.path.exists(_RULES_PATH_MAIN) else _RULES_PATH_FALLBACK
_METRICS_PATH = os.path.join(_CONFIG_DIR, "metrics.json")
_RULES_STRICT = os.environ.get("RULES_STRICT", "1") != "0"


class RuleLoader:
    """
    单例式规则加载器

    一次性加载 rules.json 和 metrics.json，
    提供对 diagnosis_scenes、steps、metric 元数据的访问。
    """

    _instance: Optional["RuleLoader"] = None
    _loaded: bool = False

    # ---- 公共数据 ----
    rules_version: str = ""
    diagnosis_scenes: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []
    steps_map: Dict[str, Dict[str, Any]] = {}   # step_id (str) → step dict
    metrics_meta: Dict[str, Dict[str, Any]] = {}  # metric_id → metrics.json 节点

    def __new__(cls) -> "RuleLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._loaded:
            self._load()
            RuleLoader._loaded = True

    # ── 加载 ────────────────────────────────────────────────────────────────
    def _load(self) -> None:
        self._load_rules()
        self._load_metrics()
        logger.info(
            "RuleLoader 初始化完成: %d scenes, %d steps, %d metrics",
            len(self.diagnosis_scenes),
            len(self.steps),
            len(self.metrics_meta),
        )

    def _load_rules(self) -> None:
        """加载 rules.json"""
        if not os.path.exists(_RULES_PATH):
            logger.warning("rules.json 不存在: %s", _RULES_PATH)
            return

        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.rules_version = data.get("version", "unknown")
        self.diagnosis_scenes = data.get("diagnosis_scenes", [])
        self.steps = data.get("steps", [])

        validation_errors = validate_rules_config(data, action_exists=has_action)
        if validation_errors:
            msg = "rules.json 校验失败:\n- " + "\n- ".join(validation_errors)
            if _RULES_STRICT:
                raise ValueError(msg)
            logger.error(msg)

        # 构建 step_id → step 的映射（step id 可能是 int 或 str）
        self.steps_map = {}
        for step in self.steps:
            sid = str(step["id"])
            self.steps_map[sid] = step

        logger.info("rules.json 加载完成 (version=%s)", self.rules_version)

    def _load_metrics(self) -> None:
        """加载 metrics.json"""
        if not os.path.exists(_METRICS_PATH):
            logger.warning("metrics.json 不存在: %s", _METRICS_PATH)
            return

        with open(_METRICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 过滤掉空字典（如 "动态上片偏差": {}）
        self.metrics_meta = {k: v for k, v in data.items() if v}
        logger.info("metrics.json 加载完成: %d 指标定义", len(self.metrics_meta))

    # ── 查询接口 ────────────────────────────────────────────────────────────

    def get_scene_by_reject_reason(self, reject_reason_id: int) -> Optional[Dict[str, Any]]:
        """
        根据 reject_reason_id 查找匹配的诊断场景

        当前仅 COARSE_ALIGN_FAILED (reject_reason_id=6) 有对应诊断场景。

        Args:
            reject_reason_id: 拒片原因 ID

        Returns:
            匹配的 diagnosis_scene 字典，未找到则返回 None
        """
        # 当前映射：reject_reason_id=6 → scene id=1001 (COWA 倍率超限)
        REJECT_REASON_SCENE_MAP = {
            6: 1001,  # COARSE_ALIGN_FAILED → COWA 倍率超限
        }

        scene_id = REJECT_REASON_SCENE_MAP.get(reject_reason_id)
        if scene_id is None:
            return None

        for scene in self.diagnosis_scenes:
            if scene.get("id") == scene_id:
                return scene

        return None

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

            # 收集 details 中的输出 results（新格式建模步骤的输出指标）
            output_results = self.get_step_output_results(step)
            for result_key in output_results.keys():
                metric_ids.add(result_key)

            # 遍历 next 分支
            for branch in step.get("next", []):
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
        RuleLoader._loaded = False
        self._load()
        RuleLoader._loaded = True
