"""
诊断推理 API
提供故障诊断分析功能
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.core.diagnosis_engine import DiagnosisEngine
from app.schemas.ontology import DiagnosisRequest, DiagnosisResult

router = APIRouter()


@router.post("/analyze", response_model=DiagnosisResult)
def analyze_diagnosis(request: DiagnosisRequest):
    """分析故障记录（提供参数或案例ID）"""
    result = DiagnosisEngine.analyze(
        case_id=request.case_id,
        phenomenon=request.phenomenon,
        params=request.params
    )
    return result


@router.get("/analyze/{case_id}", response_model=DiagnosisResult)
def analyze_by_case_id(case_id: str):
    """根据案例ID进行分析"""
    result = DiagnosisEngine.analyze(case_id=case_id)
    return result


@router.get("/rules")
def get_diagnosis_rules():
    """获取所有诊断规则"""
    rules = DiagnosisEngine.get_rules()
    return {"rules": rules}
