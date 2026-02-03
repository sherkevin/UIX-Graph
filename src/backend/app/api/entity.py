"""
实体详情 API
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.models.database import get_db, FaultRecordDB
from app.core.path_finder import PathFinder

router = APIRouter()


@router.get("/{entity_id}")
def get_entity_detail(entity_id: str):
    """
    获取实体详细信息

    支持的entity_id格式：
    - phenomenon_1
    - subsystem_WS 硅片台
    - component_Chuck 1
    - param_1_rotation_mean
    - rootcause_上片旋转机械超限
    """
    db = next(get_db())

    try:
        detail = PathFinder.get_entity_detail(entity_id, db)

        if not detail:
            raise HTTPException(status_code=404, detail=f"实体 {entity_id} 不存在")

        return detail
    finally:
        db.close()


@router.get("/{entity_id}/timeseries")
def get_entity_timeseries(
    entity_id: str,
    time_range: Optional[str] = Query("7d", description="时间范围: 1d, 7d, 30d")
):
    """
    获取实体时间序列数据（模拟数据）

    示例：
    - GET /api/entity/component_Chuck 1/timeseries?time_range=7d
    """
    days_map = {"1d": 1, "7d": 7, "30d": 30}
    days = days_map.get(time_range, 7)

    timeseries = PathFinder.generate_mock_timeseries(entity_id, days)
    return timeseries
