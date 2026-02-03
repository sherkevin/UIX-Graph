"""
数据库模型定义
使用 SQLAlchemy ORM
"""
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional
import json

# SQLite 数据库配置
SQLALCHEMY_DATABASE_URL = "sqlite:///./smee_litho_rca.db"

# 创建数据库引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite 特定配置
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基类
Base = declarative_base()


# 数据库模型
class FaultRecordDB(Base):
    """故障记录表"""
    __tablename__ = "fault_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), unique=True, index=True, nullable=False)
    phenomenon = Column(String(200), nullable=False)
    subsystem = Column(String(100))
    component = Column(String(100))
    params = Column(Text)  # JSON 字符串
    logic_link = Column(Text)
    potential_root_cause = Column(String(200))
    is_confirmed = Column(Boolean, default=False)
    confidence = Column(Integer, default=0)  # 置信度 0-100

    def get_params_dict(self) -> dict:
        """将 params 字符串转换为字典"""
        try:
            return json.loads(self.params) if self.params else {}
        except:
            return {}


class OntologyClassDB(Base):
    """本体类定义"""
    __tablename__ = "ontology_classes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50))  # 现象、分系统、部件、参数、根因
    description = Column(Text)
    properties = Column(JSON)  # 属性定义


class OntologyRelationDB(Base):
    """本体关系定义"""
    __tablename__ = "ontology_relations"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, nullable=False)
    target_id = Column(Integer, nullable=False)
    relation_type = Column(String(50), nullable=False)
    properties = Column(JSON)


def init_db():
    """初始化数据库"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
