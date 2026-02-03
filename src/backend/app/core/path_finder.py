"""
故障传播路径查找器
使用BFS算法从故障现象追溯到根因
"""
from typing import List, Dict, Any, Optional
from collections import deque
from app.core.graph_builder import GraphBuilder
from app.models.database import SessionLocal, FaultRecordDB
import random
from datetime import datetime, timedelta


class PathFinder:
    """故障传播路径查找器"""

    @staticmethod
    def find_propagation_path(case_id: str, start_node: Optional[str] = None) -> Dict[str, Any]:
        """
        查找故障传播路径

        Args:
            case_id: 案例ID
            start_node: 起始节点ID（默认为现象节点）

        Returns:
            {
                "path": ["node1", "node2", ...],  # 节点ID序列
                "nodes": [{id, label, type, properties}],
                "edges": [{source, target, label}],
                "propagation_timeline": [{timestamp, event, node_id}],
                "confidence": 85,
                "fault_node": "phenomenon_X"  # 故障现象节点ID
            }
        """
        # 获取图谱数据
        graph_data = GraphBuilder.build_graph(case_id=case_id)

        # 如果未指定起始节点，找到现象节点
        fault_node_id = None
        if not start_node:
            phenomenon_nodes = [n for n in graph_data["nodes"] if n["type"] == "phenomenon"]
            if not phenomenon_nodes:
                return PathFinder._empty_result()
            start_node = phenomenon_nodes[0]["id"]
            fault_node_id = start_node
        else:
            fault_node_id = start_node

        # BFS查找从现象到根因的路径
        path = PathFinder._bfs_to_rootcause(graph_data, start_node)

        # 获取路径上的节点和边
        path_nodes = [n for n in graph_data["nodes"] if n["id"] in path]
        path_edges = PathFinder._get_path_edges(graph_data, path)

        # 构建传播时间线
        timeline = PathFinder._build_timeline(path, path_nodes)

        return {
            "path": path,
            "nodes": path_nodes,
            "edges": path_edges,
            "propagation_timeline": timeline,
            "confidence": PathFinder._calculate_confidence(path_nodes),
            "fault_node": fault_node_id  # 故障节点ID
        }

    @staticmethod
    def _bfs_to_rootcause(graph: Dict, start: str) -> List[str]:
        """BFS查找从现象到根因的最短路径"""
        queue = deque([(start, [start])])
        visited = {start}

        # 关系优先级（用于路径排序）
        relation_priority = {
            "explains": 1,      # 优先选择解释关系（现象→根因）
            "located_in": 2,
            "belongs_to": 3,
            "measured_at": 4
        }

        while queue:
            current, path = queue.popleft()

            # 检查是否到达根因
            current_node = next((n for n in graph["nodes"] if n["id"] == current), None)
            if current_node and current_node["type"] == "rootcause":
                return path

            # 获取出边（从当前节点出发的边）
            outgoing_edges = [e for e in graph["edges"] if e["source"] == current]

            # 按关系优先级排序
            outgoing_edges.sort(key=lambda e: relation_priority.get(e["relation_type"], 99))

            for edge in outgoing_edges:
                next_node = edge["target"]
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append((next_node, path + [next_node]))

        return path  # 如果没找到根因，返回当前路径

    @staticmethod
    def _get_path_edges(graph: Dict, path: List[str]) -> List[Dict]:
        """获取路径上的边"""
        edges = []
        for i in range(len(path) - 1):
            edge = next(
                (e for e in graph["edges"]
                 if e["source"] == path[i] and e["target"] == path[i + 1]),
                None
            )
            if edge:
                edges.append(edge)
        return edges

    @staticmethod
    def _build_timeline(path: List[str], nodes: List[Dict]) -> List[Dict]:
        """构建传播时间线"""
        timeline = []
        base_time = datetime.now()

        for i, node_id in enumerate(path):
            node = next((n for n in nodes if n["id"] == node_id), None)
            if node:
                timeline.append({
                    "timestamp": (base_time + timedelta(minutes=i*5)).isoformat(),
                    "event": f"检测到{node['type']}: {node['label']}",
                    "node_id": node_id,
                    "step": i + 1
                })

        return timeline

    @staticmethod
    def _calculate_confidence(nodes: List[Dict]) -> int:
        """计算路径置信度"""
        # 简单策略：如果包含根因，置信度高
        has_rootcause = any(n["type"] == "rootcause" for n in nodes)
        return 85 if has_rootcause else 60

    @staticmethod
    def _empty_result() -> Dict:
        """返回空结果"""
        return {
            "path": [],
            "nodes": [],
            "edges": [],
            "propagation_timeline": [],
            "confidence": 0,
            "fault_node": None
        }

    @staticmethod
    def get_entity_detail(entity_id: str, db: SessionLocal) -> Optional[Dict]:
        """
        获取实体详细信息

        Args:
            entity_id: 实体ID（如 "component_Chuck 1" 或 "phenomenon_1"）
            db: 数据库会话

        Returns:
            实体详情字典
        """
        # 解析实体ID: {type}_{name_or_id}
        parts = entity_id.split('_', 1)
        if len(parts) != 2:
            return None

        entity_type, entity_ref = parts

        # 根据实体类型提取信息
        related_cases = []
        properties = {}
        entity_label = entity_ref  # 默认使用ref作为label

        # 特殊处理：如果entity_ref是数字，直接通过ID查询
        if entity_type == "phenomenon" and entity_ref.isdigit():
            record = db.query(FaultRecordDB).filter(FaultRecordDB.id == int(entity_ref)).first()
            if record:
                return {
                    "id": entity_id,
                    "label": record.phenomenon,
                    "type": entity_type,
                    "properties": {
                        "case_id": record.case_id,
                        "subsystem": record.subsystem,
                        "component": record.component
                    },
                    "related_cases": [record.case_id]
                }
            return None

        # 其他情况：遍历所有记录查找匹配
        records = db.query(FaultRecordDB).all()
        for record in records:
            params = record.get_params_dict()

            if entity_type == "phenomenon":
                if record.phenomenon == entity_ref:
                    related_cases.append(record.case_id)
                    properties = {
                        "case_id": record.case_id,
                        "subsystem": record.subsystem,
                        "component": record.component
                    }

            elif entity_type == "subsystem":
                if record.subsystem == entity_ref:
                    related_cases.append(record.case_id)

            elif entity_type == "component":
                if record.component == entity_ref:
                    related_cases.append(record.case_id)
                    properties = {
                        "subsystem": record.subsystem,
                        "parameters": list(params.keys())
                    }

            elif entity_type == "param":
                # param_{record_id}_{key} 或直接的参数名
                if entity_ref in params:
                    related_cases.append(record.case_id)
                    properties = {
                        "key": entity_ref,
                        "value": params[entity_ref],
                        "unit": PathFinder._extract_unit(params[entity_ref])
                    }

            elif entity_type == "rootcause":
                if record.potential_root_cause == entity_ref:
                    related_cases.append(record.case_id)
                    properties = {
                        "is_confirmed": record.is_confirmed,
                        "confidence": record.confidence
                    }

        if not related_cases:
            return None

        return {
            "id": entity_id,
            "label": entity_label,
            "type": entity_type,
            "properties": properties,
            "related_cases": list(set(related_cases))
        }

    @staticmethod
    def _extract_unit(value_str: str) -> str:
        """从参数值中提取单位"""
        if "urad" in value_str:
            return "urad"
        elif "Low" in value_str or "High" in value_str:
            return "level"
        else:
            return ""

    @staticmethod
    def generate_mock_timeseries(entity_id: str, days: int = 7) -> Dict:
        """
        生成模拟时间序列数据

        Args:
            entity_id: 实体ID
            days: 天数

        Returns:
            {
                "timestamps": ["2024-01-01T10:00", ...],
                "values": [100, 105, ...],
                "threshold": 300,
                "unit": "urad"
            }
        """
        # 生成时间戳
        end_time = datetime.now()
        timestamps = []
        for i in range(days * 24):  # 每小时一个数据点
            ts = end_time - timedelta(hours=i)
            timestamps.append(ts.isoformat())

        timestamps.reverse()

        # 生成模拟值（带趋势和随机波动）
        import math
        base_value = random.uniform(50, 200)
        values = []
        for i in range(len(timestamps)):
            # 添加正弦波动 + 随机噪声
            value = base_value + 50 * math.sin(i / 12) + random.uniform(-20, 20)
            values.append(round(value, 2))

        return {
            "timestamps": timestamps[-24:],  # 只返回最近24小时
            "values": values[-24:],
            "threshold": random.choice([250, 300, 350]),
            "unit": "urad"
        }
