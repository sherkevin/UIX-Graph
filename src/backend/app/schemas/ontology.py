"""
Pydantic 模式定义
用于数据验证和序列化
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ========== 本体相关模式 ==========
class OntologyClassBase(BaseModel):
    """本体类基础模式"""
    name: str = Field(..., description="类名称")
    category: Optional[str] = Field(None, description="类别")
    description: Optional[str] = Field(None, description="描述")
    properties: Optional[Dict[str, Any]] = Field(None, description="属性定义")


class OntologyClassCreate(OntologyClassBase):
    """创建本体类"""
    pass


class OntologyClass(OntologyClassBase):
    """本体类响应模式"""
    id: int

    class Config:
        from_attributes = True


# ========== 关系相关模式 ==========
class OntologyRelationBase(BaseModel):
    """本体关系基础模式"""
    source_id: int = Field(..., description="源节点ID")
    target_id: int = Field(..., description="目标节点ID")
    relation_type: str = Field(..., description="关系类型")
    properties: Optional[Dict[str, Any]] = Field(None, description="关系属性")


class OntologyRelationCreate(OntologyRelationBase):
    """创建关系"""
    pass


class OntologyRelation(OntologyRelationBase):
    """关系响应模式"""
    id: int

    class Config:
        from_attributes = True


# ========== 故障记录相关模式 ==========
class FaultRecordBase(BaseModel):
    """故障记录基础模式"""
    case_id: str = Field(..., description="案例ID")
    phenomenon: str = Field(..., description="故障现象")
    subsystem: Optional[str] = Field(None, description="分系统")
    component: Optional[str] = Field(None, description="部件")
    params: Optional[Dict[str, str]] = Field(None, description="参数")
    logic_link: Optional[str] = Field(None, description="逻辑链")
    potential_root_cause: Optional[str] = Field(None, description="潜在根因")
    is_confirmed: Optional[bool] = Field(False, description="是否确认")


class FaultRecordCreate(FaultRecordBase):
    """创建故障记录"""
    pass


class FaultRecord(FaultRecordBase):
    """故障记录响应模式"""
    id: int
    confidence: Optional[int] = Field(0, description="置信度")

    class Config:
        from_attributes = True


# ========== 诊断相关模式 ==========
class DiagnosisRequest(BaseModel):
    """诊断请求"""
    case_id: Optional[str] = Field(None, description="案例ID，如果为空则使用提供的参数")
    phenomenon: Optional[str] = Field(None, description="故障现象")
    params: Optional[Dict[str, Any]] = Field(None, description="参数")


class DiagnosisResult(BaseModel):
    """诊断结果"""
    case_id: str
    root_cause: str
    confidence: int
    category: str
    reasoning: List[str] = Field(default_factory=list)


# ========== 图谱相关模式 ==========
class GraphNode(BaseModel):
    """图谱节点"""
    id: str
    label: str
    type: str
    properties: Optional[Dict[str, Any]] = None


class GraphEdge(BaseModel):
    """图谱边"""
    source: str
    target: str
    label: str
    relation_type: str


class KnowledgeGraph(BaseModel):
    """知识图谱"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]


# ========== 传播路径相关模式 ==========
class EntityDetail(BaseModel):
    """实体详细信息"""
    id: str
    label: str
    type: str
    properties: Dict[str, Any]
    related_cases: List[str]


class PropagationPath(BaseModel):
    """故障传播路径"""
    path: List[str]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    propagation_timeline: List[Dict[str, Any]]
    confidence: int
    fault_node: Optional[str] = None  # 故障现象节点ID


class TimeSeriesData(BaseModel):
    """时间序列数据"""
    timestamps: List[str]
    values: List[float]
    threshold: Optional[float] = None
    unit: Optional[str] = None
