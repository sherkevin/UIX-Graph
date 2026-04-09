from typing import Any, Dict, List

from app.diagnosis.config_store import DiagnosisConfigStore
from app.engine.diagnosis_engine import DiagnosisEngine


class DiagnosisService:
    """统一诊断服务工厂。"""

    _engines: Dict[str, DiagnosisEngine] = {}

    @classmethod
    def get_engine(cls, pipeline_id: str) -> DiagnosisEngine:
        if pipeline_id not in cls._engines:
            cls._engines[pipeline_id] = DiagnosisEngine(pipeline_id=pipeline_id)
        return cls._engines[pipeline_id]

    @classmethod
    def reload(cls) -> None:
        DiagnosisConfigStore().reload()
        cls._engines = {}

    @classmethod
    def list_pipeline_rules(cls, pipeline_id: str) -> List[Dict[str, Any]]:
        pipeline = DiagnosisConfigStore().get_pipeline(pipeline_id)
        rules: List[Dict[str, Any]] = []
        for step in pipeline.get("steps", []):
            result = cls._extract_step_result(step)
            if result is None:
                continue
            rules.append(
                {
                    "name": step.get("description") or result.get("rootCause") or str(step.get("id")),
                    "root_cause": result.get("rootCause", ""),
                    "category": result.get("category") or result.get("system") or "",
                }
            )
        return rules

    @staticmethod
    def _extract_step_result(step: Dict[str, Any]) -> Any:
        """从步骤中提取 rootCause 结果字典，兼容三种格式：
        1. step.result（structured pipeline 格式）
        2. step.details[n].result（legacy 单数格式）
        3. step.details[n].results（legacy 复数格式）
        """
        result = step.get("result")
        if isinstance(result, dict) and result.get("rootCause"):
            return result
        for detail in step.get("details") or []:
            if not isinstance(detail, dict):
                continue
            for key in ("result", "results"):
                r = detail.get(key)
                if isinstance(r, dict) and r.get("rootCause"):
                    return r
        return None
