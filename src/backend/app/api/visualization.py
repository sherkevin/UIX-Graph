"""
可视化 API
提供知识图谱数据
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.models.database import get_db, FaultRecordDB
from app.core.graph_builder import GraphBuilder
from app.schemas.ontology import KnowledgeGraph

router = APIRouter()


@router.get("/graph/{case_id}", response_model=KnowledgeGraph)
def get_graph_by_case(case_id: str, db: Session = Depends(get_db)):
    """获取单个案例的知识图谱"""
    # 验证案例是否存在
    record = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == case_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="案例不存在")

    graph_data = GraphBuilder.build_graph(case_id=case_id)
    return graph_data


@router.get("/graph", response_model=KnowledgeGraph)
def get_merged_graph(db: Session = Depends(get_db)):
    """获取所有案例的合并知识图谱"""
    graph_data = GraphBuilder.build_graph()
    return graph_data
