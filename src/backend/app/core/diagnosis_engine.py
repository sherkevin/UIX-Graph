"""统一诊断配置驱动的 /diagnosis API 适配器。"""
from typing import Dict, Any, List, Optional

from app.diagnosis.service import DiagnosisService
from app.models.database import SessionLocal, FaultRecordDB


class DiagnosisEngine:
    """兼容旧 `/api/diagnosis/*` 接口的统一适配器。"""

    PIPELINE_ID = "ontology_api"

    @classmethod
    def analyze(
        cls,
        case_id: Optional[str] = None,
        phenomenon: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            if case_id:
                record = db.query(FaultRecordDB).filter(FaultRecordDB.case_id == case_id).first()
                if record:
                    phenomenon = record.phenomenon
                    params = record.get_params_dict()
            if not params:
                return {
                    "case_id": case_id or "UNKNOWN",
                    "root_cause": "无法确定",
                    "confidence": 0,
                    "category": "未知",
                    "reasoning": ["缺少参数信息"],
                }

            source_record = {"case_id": case_id or "UNKNOWN", "phenomenon": phenomenon, "params": params, **params}
            diagnosis = DiagnosisService.get_engine(cls.PIPELINE_ID).diagnose(
                source_record=source_record,
                params=params,
            )
            return {
                "case_id": case_id or "UNKNOWN",
                "root_cause": diagnosis.root_cause or "未知原因",
                "confidence": diagnosis.confidence,
                "category": diagnosis.category or diagnosis.system or "待分析",
                "reasoning": diagnosis.reasoning or ["未找到匹配的诊断规则"],
            }
        finally:
            db.close()

    @classmethod
    def get_rules(cls) -> List[Dict[str, Any]]:
        return DiagnosisService.list_pipeline_rules(cls.PIPELINE_ID)
