# -*- coding: utf-8 -*-
"""
拒片故障管理模块 - Handler 层（Controller 层）
负责 HTTP 请求解析、参数校验、响应封装，不含业务逻辑

时间语义说明：
  接口 1 (metadata)：startTime/endTime 过滤 lo_batch_equipment_performance.lot_start_time / lot_end_time
  接口 2 (search)  ：startTime/endTime 过滤 lo_batch_equipment_performance.wafer_product_start_time
  接口 3 (metrics) ：requestTime 作为诊断基准时间 T，影响指标时间窗 [T-duration, T]
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.reject_errors import (
    MetadataResponse,
    SearchRequest,
    SearchResponse,
    DetailResponse,
)
from app.service.reject_error_service import RejectErrorService
from app.utils import detail_trace

logger = logging.getLogger(__name__)

_TS_MIN = 946_684_800_000   # 2000-01-01 (ms)
_TS_MAX = 4_102_444_800_000  # 2100-01-01 (ms)

router = APIRouter()


@router.get("/metadata", response_model=MetadataResponse)
async def get_metadata(
    equipment: str = Query(..., description="机台名称，必须在枚举白名单内"),
    startTime: Optional[int] = Query(None, description="查询起始时间（13 位时间戳）"),
    endTime: Optional[int] = Query(None, description="查询结束时间（13 位时间戳）")
):
    """
    接口 1：获取筛选元数据

    用于页面初始化时获取 Chuck、Lot、Wafer 的分层可选数据。

    **时间字段语义**：startTime/endTime 对应 `lo_batch_equipment_performance.lot_start_time / lot_end_time`，
    与接口 2 中的 wafer_product_start_time 不同，两者均为 13 位毫秒时间戳。

    - **equipment**: 机台名称，必须在枚举白名单内
    - **startTime**: 查询起始时间（可选，13 位时间戳），过滤 lot_start_time
    - **endTime**: 查询结束时间（可选，13 位时间戳），过滤 lot_end_time
    """
    logger.info("[Handler] GET /metadata | equipment=%s startTime=%s endTime=%s", equipment, startTime, endTime)
    t0 = time.perf_counter()
    detail_trace.info(
        "HTTP 接口1 metadata | equipment=%s | startTime=%s | endTime=%s",
        equipment,
        startTime,
        endTime,
    )
    try:
        data = RejectErrorService.get_metadata(
            equipment=equipment,
            start_time=startTime,
            end_time=endTime
        )
        logger.info("[Handler] GET /metadata | equipment=%s -> %d chucks", equipment, len(data))
        detail_trace.info(
            "HTTP 接口1 成功 | equipment=%s | chucks=%s | 耗时=%.1fms",
            equipment,
            len(data),
            (time.perf_counter() - t0) * 1000,
        )
        return MetadataResponse(data=data)
    except ValueError as e:
        logger.warning("[Handler] GET /metadata | equipment=%s ValueError: %s", equipment, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_reject_errors(request: SearchRequest):
    """
    接口 2：查询拒片故障记录

    根据 Chuck、Lot、Wafer 等条件查询记录，支持分页和排序。

    ### 筛选条件说明
    - **chucks**: Chuck ID 列表，不传或 null 表示不限制，空数组 [] 表示查无结果
    - **lots**: Lot ID 列表，不传或 null 表示不限制，空数组 [] 表示查无结果
    - **wafers**: Wafer ID 列表 (1-25)，不传或 null 表示不限制，空数组 [] 表示查无结果

    ### 空数组筛选条件处理规则
    - `null` 或字段未传：不限制 / 默认全选
    - `[]` 空数组：用户明确清空筛选，直接返回空结果，不查 DB
    """
    logger.info(
        "[Handler] POST /search | equipment=%s page=%d/%d chucks=%s lots=%s wafers=%s start=%s end=%s",
        request.equipment, request.pageNo, request.pageSize,
        request.chucks, request.lots, request.wafers,
        request.startTime, request.endTime
    )
    t0 = time.perf_counter()
    detail_trace.info(
        "HTTP 接口2 search | equipment=%s | page=%s/%s | chucks=%s | lots=%s | wafers=%s | start=%s | end=%s | order=%s/%s",
        request.equipment,
        request.pageNo,
        request.pageSize,
        request.chucks,
        request.lots,
        request.wafers,
        request.startTime,
        request.endTime,
        request.sortedBy,
        request.orderedBy,
    )
    try:
        records, pagination_meta = RejectErrorService.search_reject_errors(
            equipment=request.equipment,
            page_no=request.pageNo,
            page_size=request.pageSize,
            chucks=request.chucks,
            lots=request.lots,
            wafers=request.wafers,
            start_time=request.startTime,
            end_time=request.endTime,
            order_by=request.sortedBy,
            order_dir=request.orderedBy
        )
        logger.info("[Handler] POST /search | equipment=%s -> %d records total=%s",
                    request.equipment, len(records), pagination_meta.get("total"))
        detail_trace.info(
            "HTTP 接口2 成功 | equipment=%s | 本页条数=%s | total=%s | 耗时=%.1fms",
            request.equipment,
            len(records),
            pagination_meta.get("total"),
            (time.perf_counter() - t0) * 1000,
        )
        return SearchResponse(data=records, meta=pagination_meta)
    except ValueError as e:
        logger.warning("[Handler] POST /search | equipment=%s ValueError: %s", request.equipment, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{failure_id}/metrics", response_model=DetailResponse)
async def get_failure_metrics(
    failure_id: int,
    pageNo: int = Query(1, ge=1, description="页码，从 1 开始"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    requestTime: Optional[int] = Query(
        None,
        description=(
            "分析基准时间 T（13 位毫秒时间戳，可选）。\n"
            "未传时 T = 该条记录的 wafer_product_start_time。\n"
            "传入且与发生时间相等时走缓存；传入且不等时绕过缓存读写，以传入值为准计算时间窗。"
        ),
    ),
):
    """
    接口 3：获取拒片故障详情（含指标数据）

    根据拒片故障记录 ID，获取该条故障的详细报错字段及所有关联的检测指标数据。

    ### 状态判定与排序
    - **ABNORMAL**: 指标值超出阈值范围，排序在最前
    - **NORMAL**: 指标值在阈值范围内，排序在后

    ### 缓存行为
    - 内网无 `rejected_detailed_records` 表时：在进程环境设 `REJECTED_DETAILED_CACHE=0`（或 false），
      不访问该表；每次按源表 + 诊断引擎现算
    - `REJECTED_DETAILED_CACHE` 未关闭且 `requestTime` 未传、或与 `wafer_product_start_time` 的毫秒时间戳相同：
      可读写 `rejected_detailed_records` 缓存
    - `requestTime` 与发生时间不同：绕过缓存，直接按 T 计算并返回，不写入缓存

    ### 分页逻辑
    后端在内存中对排序好的指标数组进行切割，返回当前页数据。
    """
    # requestTime 极值校验（防止传入 0 或溢出值导致 500）
    if requestTime is not None and not (_TS_MIN <= requestTime <= _TS_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"requestTime 超出合法范围（{_TS_MIN} ~ {_TS_MAX} 毫秒时间戳）"
        )

    t0 = time.perf_counter()
    detail_trace.info(
        "HTTP 接口3 进入 | failure_id=%s pageNo=%s pageSize=%s requestTime_ms=%s",
        failure_id,
        pageNo,
        pageSize,
        requestTime,
    )
    try:
        detail_data, pagination_meta = RejectErrorService.get_failure_details(
            failure_id=failure_id,
            page_no=pageNo,
            page_size=pageSize,
            request_time_ms=requestTime,
        )
    except Exception as e:
        logger.exception("接口 3 内部错误: failure_id=%s", failure_id)
        detail_trace.error(
            "HTTP 接口3 异常 | failure_id=%s | error=%s",
            failure_id,
            e,
        )
        raise HTTPException(status_code=500, detail="诊断引擎内部错误，请查看服务日志")

    if detail_data is None:
        detail_trace.info(
            "HTTP 接口3 未找到记录 | failure_id=%s | 总耗时=%.1f ms",
            failure_id,
            (time.perf_counter() - t0) * 1000,
        )
        raise HTTPException(status_code=404, detail=f"未找到故障记录：{failure_id}")

    ms = (time.perf_counter() - t0) * 1000
    detail_trace.info(
        "HTTP 接口3 成功 | failure_id=%s | metrics条数(本页)=%s | meta.total=%s | 总耗时=%.1f ms",
        failure_id,
        len((detail_data or {}).get("metrics") or []),
        (pagination_meta or {}).get("total"),
        ms,
    )
    return DetailResponse(data=detail_data, meta=pagination_meta)
