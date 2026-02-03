"""
模拟数据服务
使用本地 JSON 文件模拟数据库查询
生产环境会替换为真实的 MySQL/ClickHouse 查询
"""
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime


class MockDataService:
    """模拟数据服务"""

    def __init__(self):
        """初始化数据服务"""
        # 项目根目录
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.data_dir = os.path.join(self.base_dir, "..", "..", "..", "data")

        # 加载所有数据组
        self.data_groups = {}
        for i in range(1, 9):  # data/1 到 data/8
            group_dir = os.path.join(self.data_dir, str(i))
            if os.path.exists(group_dir):
                self.data_groups[str(i)] = self._load_data_group(group_dir)

        # 加载合并数据
        merged_dir = os.path.join(self.data_dir, "merged")
        if os.path.exists(merged_dir):
            self.merged_data = self._load_data_group(merged_dir)
        else:
            self.merged_data = None

    def _load_data_group(self, group_dir: str) -> Dict[str, Any]:
        """加载单个数据组"""
        data = {}
        node_file = os.path.join(group_dir, "node.json")
        compute_file = os.path.join(group_dir, "compute.json")

        if os.path.exists(node_file):
            with open(node_file, 'r', encoding='utf-8') as f:
                data['nodes'] = json.load(f)

        if os.path.exists(compute_file):
            with open(compute_file, 'r', encoding='utf-8') as f:
                data['compute'] = json.load(f)

        return data

    def generate_mock_reject_errors(
        self,
        machine: Optional[str] = None,
        chunks: Optional[List[str]] = None,
        lots: Optional[List[str]] = None,
        wafers: Optional[List[int]] = None,
        errorCode: Optional[str] = None,
        startTime: Optional[int] = None,
        endTime: Optional[int] = None,
        pageNo: int = 1,
        pageSize: int = 20,
        sortedBy: str = "occurredAt",
        orderedBy: str = "desc"
    ) -> Dict[str, Any]:
        """
        生成模拟拒片故障记录
        模拟数据库查询逻辑
        """
        # 基础数据池
        all_chunks = ["Chunk 1", "Chunk 2", "Chunk 3", "Chunk 4"]
        all_lots = ["Lot A001", "Lot A002", "Lot B001", "Lot B002", "Lot C001"]
        all_wafers = list(range(1, 26))
        all_systems = ["OPT", "WSA", "WS", "WH"]

        # 错误代码和原因映射
        error_codes = {
            "MEASURE_FAILED": "Sensor calibration drift",
            "ALIGNMENT_FAILED": "Mark quality degradation",
            "MAGNIFICATION_EXCEEDED": "Lens thermal drift",
            "ROTATION_EXCEEDED": "Wafer handling issue",
            "DOCKING_FAILED": "Mechanical positioning error",
            "COWA_REJECT": "Overall alignment out of spec"
        }

        # 生成模拟数据
        records = []
        base_time = int(datetime(2024, 1, 1).timestamp())

        # 生成 200 条模拟记录
        for i in range(200):
            record = {
                "id": 10000 + i,
                "chunk": all_chunks[i % len(all_chunks)],
                "lotId": all_lots[i % len(all_lots)],
                "waferIndex": all_wafers[i % len(all_wafers)],
                "errorCode": list(error_codes.keys())[i % len(error_codes)],
                "errorReason": list(error_codes.values())[i % len(error_codes)],
                "occurredAt": base_time + i * 3600,  # 每小时一条
                "system": all_systems[i % len(all_systems)]
            }
            records.append(record)

        # 应用筛选条件
        filtered = records

        if machine:
            filtered = [r for r in filtered if machine in r.get('machine', r['chunk'])]

        if chunks:  # 空列表或 None 表示不过滤
            filtered = [r for r in filtered if r['chunk'] in chunks]

        if lots:
            filtered = [r for r in filtered if r['lotId'] in lots]

        if wafers:
            filtered = [r for r in filtered if r['waferIndex'] in wafers]

        if errorCode:
            filtered = [r for r in filtered if r['errorCode'] == errorCode]

        if startTime:
            filtered = [r for r in filtered if r['occurredAt'] >= startTime]

        if endTime:
            filtered = [r for r in filtered if r['occurredAt'] <= endTime]

        # 排序
        reverse = orderedBy == "desc"
        if sortedBy == "occurredAt":
            filtered.sort(key=lambda x: x['occurredAt'], reverse=reverse)
        elif sortedBy == "waferIndex":
            filtered.sort(key=lambda x: x['waferIndex'], reverse=reverse)

        # 分页
        total = len(filtered)
        start = (pageNo - 1) * pageSize
        end = start + pageSize
        paged = filtered[start:end]

        return {
            "records": paged,
            "total": total
        }

    def get_metadata(self) -> Dict[str, Any]:
        """获取筛选元数据"""
        return {
            "availableMachines": ["C 1", "C 2"],
            "availableChunks": ["Chunk 1", "Chunk 2", "Chunk 3", "Chunk 4"],
            "availableLots": ["Lot A001", "Lot A002", "Lot B001", "Lot B002", "Lot C001"],
            "availableWafers": list(range(1, 26)),
            "waferRange": {"min": 1, "max": 25}
        }

    def get_graph_data(self, group_id: str = "merged") -> Dict[str, Any]:
        """获取图谱数据"""
        if group_id == "merged" and self.merged_data:
            return self.merged_data
        elif group_id in self.data_groups:
            return self.data_groups[group_id]
        else:
            return None


# 全局单例
mock_data_service = MockDataService()
