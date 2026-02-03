"""
诊断推理引擎
基于规则的故障诊断
"""
from typing import Dict, Any, List, Optional
from app.models.database import SessionLocal, FaultRecordDB
import json


class DiagnosisEngine:
    """诊断引擎"""

    # 诊断规则定义
    RULES = [
        {
            "name": "旋转超限规则",
            "condition": lambda params: (
                self._extract_number(params.get("rotation_mean", "0")) > 300 or
                self._extract_number(params.get("rotation_3sigma", "0")) > 350
            ),
            "root_cause": "上片旋转机械超限",
            "category": "机械精度",
            "reasoning": [
                "检测到旋转参数超出阈值",
                "rotation_mean > 300 urad 或 rotation_3sigma > 350",
                "判定为上片旋转机械超限"
            ]
        },
        {
            "name": "真空吸附异常规则",
            "condition": lambda params: (
                params.get("vacuum_level") == "Low" and
                self._extract_number(params.get("rotation_mean", "0")) > 100
            ),
            "root_cause": "WS 硬件物理损坏/泄露",
            "category": "硬件损耗",
            "reasoning": [
                "检测到真空度低且旋转异常",
                "vacuum_level = Low 且 rotation_mean > 100",
                "判定为WS硬件物理损坏/泄露"
            ]
        },
        {
            "name": "对准重复性异常规则",
            "condition": lambda params: (
                self._extract_number(params.get("rotation_mean", "0")) > 300
            ),
            "root_cause": "上片旋转机械超限",
            "category": "机械精度",
            "reasoning": [
                "检测到对准重复性异常",
                "rotation_mean > 300 urad",
                "判定为上片旋转机械超限"
            ]
        }
    ]

    @staticmethod
    def _extract_number(value: str) -> float:
        """从字符串中提取数字"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # 移除单位并提取数字
            import re
            match = re.search(r'[\d.]+', value)
            if match:
                return float(match.group())
        return 0.0

    @classmethod
    def analyze(cls, case_id: Optional[str] = None,
                phenomenon: Optional[str] = None,
                params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析故障记录

        Args:
            case_id: 案例ID
            phenomenon: 故障现象
            params: 参数字典

        Returns:
            诊断结果
        """
        db = SessionLocal()
        try:
            # 如果提供了 case_id，从数据库获取记录
            if case_id:
                record = db.query(FaultRecordDB).filter(
                    FaultRecordDB.case_id == case_id
                ).first()
                if record:
                    phenomenon = record.phenomenon
                    params = record.get_params_dict()

            # 如果没有参数，返回默认结果
            if not params:
                return {
                    "case_id": case_id or "UNKNOWN",
                    "root_cause": "无法确定",
                    "confidence": 0,
                    "category": "未知",
                    "reasoning": ["缺少参数信息"]
                }

            # 应用诊断规则
            for rule in cls.RULES:
                try:
                    # 使用 lambda 需要绑定 self
                    condition = rule["condition"]
                    # 创建一个可调用的条件检查
                    if cls._check_condition(condition, params):
                        return {
                            "case_id": case_id or "UNKNOWN",
                            "root_cause": rule["root_cause"],
                            "confidence": 85,
                            "category": rule["category"],
                            "reasoning": rule["reasoning"]
                        }
                except Exception as e:
                    continue

            # 如果没有匹配的规则
            return {
                "case_id": case_id or "UNKNOWN",
                "root_cause": "未知原因",
                "confidence": 30,
                "category": "待分析",
                "reasoning": ["未找到匹配的诊断规则"]
            }

        finally:
            db.close()

    @classmethod
    def _check_condition(cls, condition_func, params: Dict[str, Any]) -> bool:
        """检查条件"""
        try:
            result = condition_func(params)
            return bool(result)
        except:
            return False

    @classmethod
    def get_rules(cls) -> List[Dict[str, Any]]:
        """获取所有诊断规则"""
        return [
            {
                "name": rule["name"],
                "root_cause": rule["root_cause"],
                "category": rule["category"]
            }
            for rule in cls.RULES
        ]
