"""
诊断 API - PRD1 版本
基于 PRD1 诊断引擎提供诊断分析接口
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.schemas.reject_errors import SuccessResponse
from pydantic import BaseModel, Field
from app.core.diagnosis_engine_prd1_v2 import DiagnosisEnginePRD1

router = APIRouter()


class DiagnosisRequest(BaseModel):
    """诊断请求"""
    errorCode: str = Field(..., description="错误代码，如 'COWA拒片-对准倍率超限'")
    waferId: Optional[int] = Field(None, description="Wafer ID")
    layer: Optional[str] = Field(None, description="层级")
    machine: Optional[str] = Field(None, description="机台编号")

    # 诊断参数
    magnification: Optional[float] = Field(None, description="倍率值 (ppm)")
    deviation: Optional[float] = Field(None, description="上片偏差值")
    rotation: Optional[float] = Field(None, description="旋转值")
    layer_avg_deviation: Optional[float] = Field(None, description="层级平均偏差")
    layer_avg_rotation: Optional[float] = Field(None, description="层级平均旋转")
    mcc: Optional[float] = Field(None, description="MCC 值")
    wq: Optional[float] = Field(None, description="WQ 值")

    class Config:
        json_schema_extra = {
            "example": {
                "errorCode": "COWA拒片-对准倍率超限",
                "waferId": 5,
                "layer": "L1",
                "machine": "C1",
                "magnification": 120.5,
                "deviation": 0.8,
                "rotation": 2.3
            }
        }


@router.post("/analyze")
async def analyze_diagnosis(request: DiagnosisRequest):
    """
    执行故障诊断分析

    基于 PRD1 诊断流程：
    1. 倍率检查
    2. 偏差检查
    3. 旋转检查
    4. 标记对准检查
    5. 其他检查
    """
    try:
        result = DiagnosisEnginePRD1.analyze(
            error_code=request.errorCode,
            params=request.model_dump()
        )

        if 'error' in result:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": 30002,
                    "message": "未知的错误代码",
                    "details": result['error']
                }
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": 30003,
                "message": "诊断分析失败",
                "details": str(e)
            }
        )
