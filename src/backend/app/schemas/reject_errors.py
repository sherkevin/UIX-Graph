"""
拒片故障管理模块的 Pydantic Schema
基于 PRD1.md 规范定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ========== 请求 Schema ==========

class RejectErrorSearchRequest(BaseModel):
    """拒片故障查询请求"""
    pageNo: int = Field(1, ge=1, description="页码，从1开始")
    pageSize: int = Field(20, ge=1, le=100, description="每页条数")
    machine: Optional[str] = Field(None, description="机台编号，如 C1, C2")
    chunks: Optional[List[str]] = Field(None, description="Chunk 列表，空数组或null表示不过滤")
    lots: Optional[List[str]] = Field(None, description="Lot 列表")
    wafers: Optional[List[int]] = Field(None, description="Wafer ID 数组，范围 1-25")
    errorCode: Optional[str] = Field(None, description="错误代码，精确匹配")
    startTime: Optional[int] = Field(None, description="查询起始时间，Unix时间戳（秒）")
    endTime: Optional[int] = Field(None, description="查询结束时间，Unix时间戳（秒）")
    sortedBy: Optional[str] = Field("occurredAt", description="排序字段")
    orderedBy: Optional[str] = Field("desc", description="排序方向，asc 或 desc")

    class Config:
        json_schema_extra = {
            "example": {
                "pageNo": 1,
                "pageSize": 20,
                "machine": "C1",
                "chunks": [],
                "lots": [],
                "wafers": [],
                "errorCode": None,
                "startTime": None,
                "endTime": None,
                "sortedBy": "occurredAt",
                "orderedBy": "desc"
            }
        }


# ========== 响应 Schema ==========

class RejectErrorRecord(BaseModel):
    """拒片故障记录"""
    id: int = Field(..., description="记录ID")
    chunk: str = Field(..., description="Chunk 编号")
    lotId: str = Field(..., description="Lot ID")
    waferIndex: int = Field(..., ge=1, le=25, description="Wafer 索引，1-25")
    errorCode: str = Field(..., description="错误代码")
    errorReason: str = Field(..., description="错误原因")
    occurredAt: int = Field(..., description="发生时间，Unix时间戳（秒）")
    system: str = Field(..., description="子系统，如 OPT, WSA, WS, WH")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 10245,
                "chunk": "Chunk 1",
                "lotId": "Lot A001",
                "waferIndex": 5,
                "errorCode": "MEASURE_FAILED",
                "errorReason": "Sensor calibration drift",
                "occurredAt": 1699596120,
                "system": "OPT"
            }
        }


class MetadataResponse(BaseModel):
    """筛选元数据响应"""
    availableMachines: List[str] = Field(..., description="可用机台列表")
    availableChunks: List[str] = Field(..., description="可用 Chunk 列表")
    availableLots: List[str] = Field(..., description="可用 Lot 列表")
    availableWafers: List[int] = Field(..., description="可用 Wafer ID 列表")
    waferRange: dict = Field(..., description="Wafer 范围，包含 min 和 max")

    class Config:
        json_schema_extra = {
            "example": {
                "availableMachines": ["C 1", "C 2"],
                "availableChunks": ["Chunk 1", "Chunk 2"],
                "availableLots": ["Lot A001", "Lot A002", "Lot B001"],
                "availableWafers": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25],
                "waferRange": {"min": 1, "max": 25}
            }
        }


class MetaInfo(BaseModel):
    """分页元数据"""
    total: int = Field(..., description="总记录数")
    pageNo: int = Field(..., description="当前页码")
    pageSize: int = Field(..., description="每页条数")


class SuccessResponse(BaseModel):
    """成功响应格式"""
    data: Any = Field(..., description="具体数据对象或数组")
    meta: Optional[MetaInfo] = Field(None, description="分页及元数据信息")


class ErrorResponse(BaseModel):
    """错误响应格式"""
    error: dict = Field(..., description="错误信息")


class ErrorDetail(BaseModel):
    """错误详情"""
    code: int = Field(..., description="业务错误码")
    message: str = Field(..., description="简短提示")
    details: Optional[str] = Field(None, description="详细调试信息")
