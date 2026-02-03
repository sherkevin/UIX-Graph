"""
诊断图谱数据模型
基于 PRD1.md 中定义的 JSON Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class NodeCategory(str, Enum):
    """节点类型枚举"""
    SUBSYSTEM = "SUBSYSTEM"
    COMPONENT = "COMPONENT"
    SYMPTOM = "SYMPTOM"
    INDICATOR = "INDICATOR"
    ROOT_CAUSE = "ROOT_CAUSE"
    RULE_LOGIC = "RULE_LOGIC"


class NodeOperator(BaseModel):
    """节点算子定义"""
    data_source: Optional[str] = Field(None, description="函数名字符串，用于获取实时值或状态")


class NodeAttributes(BaseModel):
    """节点属性"""
    description: Optional[str] = None
    unit: Optional[str] = Field(None, description="仅指标类需要")
    classification: Optional[str] = Field(None, description="仅根因类需要 (e.g., '机械精度', '硬件损耗')")
    logic: Optional[str] = Field(None, description="仅规则逻辑类需要 (e.g., 'AND', 'OR')")

    # 允许额外的动态属性
    class Config:
        extra = "allow"


class Node(BaseModel):
    """图谱节点"""
    id: str = Field(..., description="唯一标识符")
    label: str = Field(..., description="显示名称")
    category: NodeCategory = Field(..., description="节点类型")
    attributes: NodeAttributes = Field(default_factory=NodeAttributes, description="节点属性")
    operator: Optional[NodeOperator] = Field(None, description="数据获取算子")


class EdgeOperator(BaseModel):
    """边算子定义"""
    s2t: str = Field(..., description="函数名字符串，输入Source值，输出布尔判断结果")


class Edge(BaseModel):
    """图谱边"""
    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    relation: str = Field(..., description="关系描述 (e.g., 'INDICATES', 'CAUSES')")
    operator: Optional[EdgeOperator] = Field(None, description="推理逻辑算子")


class GraphInfo(BaseModel):
    """图谱元信息"""
    title: str = Field(..., description="图谱标题")
    version: str = Field(..., description="版本号")


class DiagnosisGraph(BaseModel):
    """完整诊断图谱"""
    graph_info: GraphInfo
    nodes: List[Node]
    edges: List[Edge]


class DiagnosisResult(BaseModel):
    """诊断结果"""
    root_causes: List[Node] = Field(..., description="激活的根因节点列表")
    activated_paths: List[List[str]] = Field(..., description="激活的路径列表，每条路径是节点ID序列")
    timestamp: str = Field(..., description="诊断时间戳")
    sensor_data: Dict[str, Any] = Field(default_factory=dict, description="传感器读取的原始数据")
