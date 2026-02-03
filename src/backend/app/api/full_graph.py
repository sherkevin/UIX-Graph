"""
全图谱 API
提供包含所有节点和边的大图谱数据
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.core.full_graph_builder import FullGraphBuilder

router = APIRouter()


@router.get("/full-graph")
def get_full_graph():
    """
    获取全量图谱（包含所有案例的节点和边）

    Returns:
        {
            "nodes": [{id, label, type, properties, cases}],
            "edges": [{id, source, target, relation, cases}],
            "stats": {total_nodes, total_edges, total_cases}
        }
    """
    db = next(get_db())

    try:
        graph_data = FullGraphBuilder.build_full_graph(db)
        return graph_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建图谱失败: {str(e)}")
    finally:
        db.close()


@router.get("/subgraph/{case_id}")
def get_subgraph_nodes(case_id: str):
    """
    获取某个案例相关的所有节点ID（用于前端高亮）

    Args:
        case_id: 案例ID

    Returns:
        {
            "case_id": "CASE_001",
            "node_ids": ["node1", "node2", ...]
        }
    """
    db = next(get_db())

    try:
        node_ids = FullGraphBuilder.get_subgraph_nodes(case_id, db)
        return {
            "case_id": case_id,
            "node_ids": node_ids
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取子图节点失败: {str(e)}")
    finally:
        db.close()
