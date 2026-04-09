"""
拒片故障管理模块 - Pydantic Schema 定义
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime


# ============== 通用响应格式 ==============

class Meta(BaseModel):
    """分页元数据"""
    total: int = Field(..., description="数据总条数（接口 3 为诊断+建模参数合计）")
    pageNo: int = Field(..., description="当前页码")
    pageSize: int = Field(..., description="每页数量")
    totalPages: int = Field(..., description="总页数（接口 3 仅按诊断指标分页）")
    metricDiagnosticTotal: Optional[int] = Field(
        None, description="接口 3：有阈值/诊断类指标总数（不含 model_param）"
    )
    metricModelParamTotal: Optional[int] = Field(
        None, description="接口 3：建模参数项数（每页响应中均附带完整列表）"
    )


class CommonResponse(BaseModel):
    """通用响应格式"""
    data: Any
    meta: Optional[Meta] = None


# ============== 接口 1: 获取筛选元数据 ==============

class WaferInfo(BaseModel):
    """Wafer 信息"""
    lotId: Union[int, str] = Field(..., description="Lot ID（兼容整数与字符串格式）")
    lotName: str = Field(..., description="Lot 名称")
    availableWafers: List[Union[int, str]] = Field(..., description="可用的 Wafer ID 列表")


class ChuckInfo(BaseModel):
    """Chuck 信息"""
    chuckId: Union[int, str] = Field(..., description="Chuck ID（兼容整数与字符串格式）")
    chuckName: str = Field(..., description="Chuck 名称")
    availableLots: List[WaferInfo] = Field(..., description="下属的 Lot 列表")


class MetadataResponse(BaseModel):
    """元数据响应"""
    data: List[ChuckInfo]


# ============== 接口 2: 查询拒片故障记录 ==============

class SearchRequest(BaseModel):
    """搜索请求"""
    pageNo: int = Field(..., ge=1, description="页码，从 1 开始")
    pageSize: int = Field(..., ge=1, le=100, description="每页数量")
    equipment: str = Field(..., description="机台名称")
    chucks: Optional[List[Union[int, str]]] = Field(None, description="Chuck ID 列表（兼容整数与字符串格式）")
    lots: Optional[List[Union[int, str]]] = Field(None, description="Lot ID 列表（兼容整数与字符串格式）")
    wafers: Optional[List[Union[int, str]]] = Field(None, description="Wafer ID 列表（兼容整数与字符串格式）")
    startTime: Optional[int] = Field(None, description="查询起始时间（13 位时间戳）")
    endTime: Optional[int] = Field(None, description="查询结束时间（13 位时间戳）")
    sortedBy: str = Field(default="time", description="排序字段")
    orderedBy: str = Field(default="desc", description="排序方向：asc / desc")


class SearchRecord(BaseModel):
    """搜索记录"""
    id: int = Field(..., description="故障记录 ID（来自源表 lo_batch_equipment_performance.id）")
    failureId: int = Field(..., description="故障记录 ID，与 id 相同（保留字段，兼容后续读写分离扩展）")
    chuckId: Union[int, str] = Field(..., description="Chuck ID（兼容整数与字符串格式）")
    lotId: Union[int, str] = Field(..., description="Lot ID（兼容整数与字符串格式）")
    waferIndex: Union[int, str] = Field(..., description="Wafer ID（兼容整数与字符串格式）")
    rejectReason: str = Field(..., description="拒片原因值")
    rejectReasonId: int = Field(..., description="拒片原因 ID")
    rootCause: Optional[str] = Field(None, description="根本原因")
    time: int = Field(..., description="故障发生时间（13 位时间戳）")
    system: Optional[str] = Field(None, description="所属分系统")


class SearchResponse(BaseModel):
    """搜索响应"""
    data: List[SearchRecord]
    meta: Meta


# ============== 接口 3: 获取拒片故障详情 ==============

class ThresholdInfo(BaseModel):
    """阈值信息"""
    operator: str = Field(..., description="比较操作符，如 between / > / < 等")
    limit: Any = Field(..., description="阈值限制：单值、区间或复合条件")
    display: Optional[str] = Field(None, description="前端优先展示的规则原始条件文本")


class MetricInfo(BaseModel):
    """指标信息"""
    name: str = Field(..., description="指标名称")
    value: float = Field(..., description="指标值")
    unit: str = Field(..., description="单位")
    status: str = Field(..., description="状态：NORMAL / ABNORMAL")
    threshold: ThresholdInfo = Field(..., description="阈值信息")


class DetailResponse(BaseModel):
    """详情响应"""
    data: Dict[str, Any]
    meta: Meta
