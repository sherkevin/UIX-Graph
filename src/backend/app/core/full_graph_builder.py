"""
全图谱构建器
构建包含所有案例节点和边的大图谱
"""
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from app.models.database import FaultRecordDB
import json


class FullGraphBuilder:
    """全图谱构建器 - 构建包含所有实体的大图谱"""

    @staticmethod
    def build_full_graph(db: Session) -> Dict[str, Any]:
        """
        构建包含所有案例的全量图谱

        Returns:
            {
                "nodes": [{id, label, type, properties, cases}],
                "edges": [{source, target, relation, cases}]
            }
        """
        # 获取所有故障记录
        records = db.query(FaultRecordDB).all()

        nodes = {}
        edges = {}

        # 现象节点映射
        phenomenon_map = {}  # phenomenon_name -> node_id
        subsystem_map = {}   # subsystem_name -> node_id
        component_map = {}   # component_name -> node_id
        rootcause_map = {}   # rootcause_name -> node_id

        for record in records:
            case_id = record.case_id

            # 1. 创建现象节点
            phenomenon_id = f"phenomenon_{record.id}"
            if phenomenon_id not in nodes:
                nodes[phenomenon_id] = {
                    "id": phenomenon_id,
                    "label": record.phenomenon,
                    "type": "phenomenon",
                    "properties": {
                        "case_id": case_id
                    },
                    "cases": [case_id]
                }
                phenomenon_map[record.phenomenon] = phenomenon_id
            else:
                if case_id not in nodes[phenomenon_id]["cases"]:
                    nodes[phenomenon_id]["cases"].append(case_id)

            # 2. 创建子系统节点
            if record.subsystem:
                subsystem_id = f"subsystem_{record.subsystem}"
                if subsystem_id not in nodes:
                    nodes[subsystem_id] = {
                        "id": subsystem_id,
                        "label": record.subsystem,
                        "type": "subsystem",
                        "properties": {},
                        "cases": [case_id]
                    }
                    subsystem_map[record.subsystem] = subsystem_id
                else:
                    if case_id not in nodes[subsystem_id]["cases"]:
                        nodes[subsystem_id]["cases"].append(case_id)

            # 3. 创建部件节点
            if record.component:
                component_id = f"component_{record.component}"
                if component_id not in nodes:
                    nodes[component_id] = {
                        "id": component_id,
                        "label": record.component,
                        "type": "component",
                        "properties": {
                            "subsystem": record.subsystem
                        },
                        "cases": [case_id]
                    }
                    component_map[record.component] = component_id
                else:
                    if case_id not in nodes[component_id]["cases"]:
                        nodes[component_id]["cases"].append(case_id)

            # 4. 创建根因节点
            if record.potential_root_cause:
                rootcause_id = f"rootcause_{record.potential_root_cause}"
                if rootcause_id not in nodes:
                    nodes[rootcause_id] = {
                        "id": rootcause_id,
                        "label": record.potential_root_cause,
                        "type": "rootcause",
                        "properties": {
                            "is_confirmed": record.is_confirmed,
                            "confidence": record.confidence
                        },
                        "cases": [case_id]
                    }
                    rootcause_map[record.potential_root_cause] = rootcause_id
                else:
                    if case_id not in nodes[rootcause_id]["cases"]:
                        nodes[rootcause_id]["cases"].append(case_id)

            # 5. 创建参数节点
            params = record.get_params_dict()
            for param_key, param_value in params.items():
                param_id = f"param_{record.id}_{param_key}"
                nodes[param_id] = {
                    "id": param_id,
                    "label": param_key,
                    "type": "parameter",
                    "properties": {
                        "value": param_value,
                        "unit": FullGraphBuilder._extract_unit(param_value)
                    },
                    "cases": [case_id]
                }

                # 参数 → 部件
                if record.component:
                    edge_id = f"param_{param_key}_component_{record.component}"
                    if edge_id not in edges:
                        edges[edge_id] = {
                            "id": edge_id,
                            "source": param_id,
                            "target": component_map[record.component],
                            "relation": "measured_at",
                            "cases": [case_id]
                        }
                    else:
                        if case_id not in edges[edge_id]["cases"]:
                            edges[edge_id]["cases"].append(case_id)

            # 6. 创建关系边
            # 现象 → 子系统
            if record.subsystem:
                edge_id = f"phenomenon_{record.id}_subsystem_{record.subsystem}"
                if edge_id not in edges:
                    edges[edge_id] = {
                        "id": edge_id,
                        "source": phenomenon_id,
                        "target": subsystem_map[record.subsystem],
                        "relation": "located_in",
                        "cases": [case_id]
                    }
                else:
                    if case_id not in edges[edge_id]["cases"]:
                        edges[edge_id]["cases"].append(case_id)

            # 子系统 → 部件
            if record.subsystem and record.component:
                edge_id = f"subsystem_{record.subsystem}_component_{record.component}"
                if edge_id not in edges:
                    edges[edge_id] = {
                        "id": edge_id,
                        "source": subsystem_map[record.subsystem],
                        "target": component_map[record.component],
                        "relation": "contains",
                        "cases": [case_id]
                    }
                else:
                    if case_id not in edges[edge_id]["cases"]:
                        edges[edge_id]["cases"].append(case_id)

            # 部件 → 根因
            if record.component and record.potential_root_cause:
                edge_id = f"component_{record.component}_rootcause_{record.potential_root_cause}"
                if edge_id not in edges:
                    edges[edge_id] = {
                        "id": edge_id,
                        "source": component_map[record.component],
                        "target": rootcause_map[record.potential_root_cause],
                        "relation": "causes",
                        "cases": [case_id]
                    }
                else:
                    if case_id not in edges[edge_id]["cases"]:
                        edges[edge_id]["cases"].append(case_id)

        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_cases": len(records)
            }
        }

    @staticmethod
    def get_subgraph_nodes(case_id: str, db: Session) -> List[str]:
        """
        获取某个案例相关的所有节点ID（用于高亮）

        Args:
            case_id: 案例ID

        Returns:
            节点ID列表
        """
        record = db.query(FaultRecordDB).filter(
            FaultRecordDB.case_id == case_id
        ).first()

        if not record:
            return []

        node_ids = []

        # 现象节点
        node_ids.append(f"phenomenon_{record.id}")

        # 子系统节点
        if record.subsystem:
            node_ids.append(f"subsystem_{record.subsystem}")

        # 部件节点
        if record.component:
            node_ids.append(f"component_{record.component}")

        # 根因节点
        if record.potential_root_cause:
            node_ids.append(f"rootcause_{record.potential_root_cause}")

        # 参数节点
        params = record.get_params_dict()
        for param_key in params.keys():
            node_ids.append(f"param_{record.id}_{param_key}")

        return node_ids

    @staticmethod
    def _extract_unit(value_str: str) -> str:
        """从参数值中提取单位"""
        if "urad" in str(value_str):
            return "urad"
        elif "Low" in str(value_str) or "High" in str(value_str):
            return "level"
        else:
            return ""
