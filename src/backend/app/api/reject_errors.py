"""
拒片故障管理 API
基于 PRD1.md 规范实现
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.schemas.reject_errors import (
    RejectErrorSearchRequest,
    RejectErrorRecord,
    MetadataResponse,
    MetaInfo
)
from app.services.mock_data_service import mock_data_service

router = APIRouter()


@router.get("/metadata", response_model=MetadataResponse)
async def get_metadata():
    """
    获取筛选元数据
    用于页面初始化时获取 Chunk、Lot、Wafer 的可选列表
    """
    try:
        data = mock_data_service.get_metadata()
        return {
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取元数据失败: {str(e)}")


@router.post("/search")
async def search_reject_errors(request: RejectErrorSearchRequest):
    """
    查询拒片故障记录
    支持多维度筛选、分页与排序

    筛选逻辑：
    - 所有条件为 AND 关系
    - 若 chunks/lots/wafers 为空数组 [] 或 null，则视为忽略该条件（全选）
    """
    try:
        # 参数验证
        if request.wafers:
            invalid_wafers = [w for w in request.wafers if w < 1 or w > 25]
            if invalid_wafers:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": 30001,
                        "message": "Wafer ID 超出范围",
                        "details": f"无效的 Wafer ID: {invalid_wafers}，有效范围为 1-25"
                    }
                )

        # 查询数据
        result = mock_data_service.generate_mock_reject_errors(
            machine=request.machine,
            chunks=request.chunks if request.chunks else None,
            lots=request.lots if request.lots else None,
            wafers=request.wafers if request.wafers else None,
            errorCode=request.errorCode,
            startTime=request.startTime,
            endTime=request.endTime,
            pageNo=request.pageNo,
            pageSize=request.pageSize,
            sortedBy=request.sortedBy,
            orderedBy=request.orderedBy
        )

        # 检查是否有数据
        if result["total"] == 0:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": 30002,
                    "message": "查询不到相关的拒片记录",
                    "details": "请调整筛选条件后重试"
                }
            )

        return {
            "data": result["records"],
            "meta": {
                "total": result["total"],
                "pageNo": request.pageNo,
                "pageSize": request.pageSize
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": 30003,
                "message": "数据库查询超时",
                "details": str(e)
            }
        )
