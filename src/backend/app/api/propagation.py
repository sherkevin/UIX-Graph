"""
故障传播路径 API
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.models.database import get_db, FaultRecordDB
from app.core.path_finder import PathFinder

router = APIRouter()


@router.get("/test")
def test_endpoint():
    """测试endpoint是否工作"""
    db = next(get_db())
    try:
        records = db.query(FaultRecordDB).all()
        record_ids = [{"id": r.id, "case_id": r.case_id} for r in records]
        return {"status": "ok", "message": "Propagation routes are working", "records": record_ids}
    finally:
        db.close()


@router.get("/{case_id}")
def get_propagation_path(
    case_id: str,
    start_node: Optional[str] = Query(None, description="起始节点ID")
):
    """
    获取故障传播路径

    示例请求：
    - GET /api/propagation/CASE_001
    - GET /api/propagation/CASE_001?start_node=component_Chuck 2
    """
    db = next(get_db())

    # 验证案例存在
    record = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == case_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail=f"案例 {case_id} 不存在")

    db.close()

    # 查找传播路径
    try:
        path_data = PathFinder.find_propagation_path(case_id, start_node)
        return path_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"路径查找失败: {str(e)}")
