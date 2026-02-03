"""
知识图谱构建器
用于可视化故障诊断知识图谱
"""
from typing import List, Dict, Any, Optional
from app.models.database import SessionLocal, FaultRecordDB
import json


class GraphBuilder:
    """图谱构建器"""

    @staticmethod
    def build_graph(case_id: Optional[str] = None) -> Dict[str, Any]:
        """
        构建知识图谱

        Args:
            case_id: 案例ID，如果为None则构建所有案例的合并图谱

        Returns:
            包含 nodes 和 edges 的图谱数据
        """
        db = SessionLocal()
        try:
            nodes = []
            edges = []
            node_ids = set()

            if case_id:
                # 构建单个案例的图谱
                record = db.query(FaultRecordDB).filter(
                    FaultRecordDB.case_id == case_id
                ).first()

                if record:
                    nodes, edges = GraphBuilder._build_single_case_graph(
                        record, node_ids
                    )
            else:
                # 构建所有案例的合并图谱
                records = db.query(FaultRecordDB).all()
                for record in records:
                    case_nodes, case_edges = GraphBuilder._build_single_case_graph(
                        record, node_ids
                    )
                    nodes.extend(case_nodes)
                    edges.extend(case_edges)

            return {
                "nodes": nodes,
                "edges": edges
            }

        finally:
            db.close()

    @staticmethod
    def _build_single_case_graph(
        record: FaultRecordDB,
        existing_ids: set
    ) -> tuple[List[Dict], List[Dict]]:
        """为单个案例构建图谱"""
        nodes = []
        edges = []
        params = record.get_params_dict()

        # 1. 故障现象节点
        phenomenon_id = f"phenomenon_{record.id}"
        if phenomenon_id not in existing_ids:
            nodes.append({
                "id": phenomenon_id,
                "label": record.phenomenon,
                "type": "phenomenon",
                "properties": {"case_id": record.case_id}
            })
            existing_ids.add(phenomenon_id)

        # 2. 分系统节点
        if record.subsystem:
            subsystem_id = f"subsystem_{record.subsystem}"
            if subsystem_id not in existing_ids:
                nodes.append({
                    "id": subsystem_id,
                    "label": record.subsystem,
                    "type": "subsystem",
                    "properties": {}
                })
                existing_ids.add(subsystem_id)

            # 现象 -> 分系统
            edges.append({
                "source": phenomenon_id,
                "target": subsystem_id,
                "label": "Located_In",
                "relation_type": "located_in"
            })

        # 3. 部件节点
        if record.component:
            component_id = f"component_{record.component}"
            if component_id not in existing_ids:
                nodes.append({
                    "id": component_id,
                    "label": record.component,
                    "type": "component",
                    "properties": {}
                })
                existing_ids.add(component_id)

            # 分系统 -> 部件
            if record.subsystem:
                edges.append({
                    "source": subsystem_id,
                    "target": component_id,
                    "label": "Belongs_To",
                    "relation_type": "belongs_to"
                })

        # 4. 参数节点
        for key, value in params.items():
            param_id = f"param_{record.id}_{key}"
            if param_id not in existing_ids:
                nodes.append({
                    "id": param_id,
                    "label": f"{key}: {value}",
                    "type": "parameter",
                    "properties": {"key": key, "value": str(value)}
                })
                existing_ids.add(param_id)

            # 部件 -> 参数
            if record.component:
                edges.append({
                    "source": component_id,
                    "target": param_id,
                    "label": "Measured_At",
                    "relation_type": "measured_at"
                })

        # 5. 根因节点
        if record.potential_root_cause:
            rootcause_id = f"rootcause_{record.potential_root_cause}"
            if rootcause_id not in existing_ids:
                nodes.append({
                    "id": rootcause_id,
                    "label": record.potential_root_cause,
                    "type": "rootcause",
                    "properties": {
                        "confirmed": record.is_confirmed,
                        "confidence": record.confidence
                    }
                })
                existing_ids.add(rootcause_id)

            # 现象 -> 根因
            edges.append({
                "source": phenomenon_id,
                "target": rootcause_id,
                "label": "Explains",
                "relation_type": "explains"
            })

        return nodes, edges
