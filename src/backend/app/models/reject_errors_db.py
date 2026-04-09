"""
拒片故障管理模块 - MySQL 数据库配置
使用 SQLAlchemy ORM

注意：
1. 本模块使用 MySQL 数据库（而非 SQLite）
2. 数据库配置从 config/connections.json 读取
3. 本地开发环境会自动创建同名表结构，保证内网迁移后可直接运行
"""
from sqlalchemy import create_engine, Column, String, Integer, BigInteger, Boolean, Text, JSON, DateTime, Float, ForeignKey, Index, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from typing import Optional, List
import json
import os
from datetime import datetime

# 数据库配置
# 本地开发环境：使用本地 MySQL 创建模拟数据库
# 内网环境：使用 config/connections.json 中的配置
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/datacenter"

# 尝试从配置文件读取数据库连接
config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config", "connections.json")
if os.path.exists(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        connections = json.load(f)
        # 通过环境变量 APP_ENV 控制使用哪个环境（默认 local，内网设置 APP_ENV=prod 或 test）
        app_env = os.environ.get("APP_ENV", "local")
        db_config = connections.get(app_env, {}).get("mysql", {})
        if not db_config and app_env != "local":
            db_config = connections.get("local", {}).get("mysql", {})
        if db_config:
            SQLALCHEMY_DATABASE_URL = (
                f"mysql+pymysql://{db_config.get('username', 'root')}:"
                f"{db_config.get('password', '')}@"
                f"{db_config.get('host', 'localhost')}:"
                f"{db_config.get('port', 3306)}/"
                f"{db_config.get('dbname', 'datacenter')}"
            )

# 创建数据库引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # 连接前 ping 测试
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    echo=False  # 是否打印 SQL 日志
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基类
Base = declarative_base()


# ============== 源数据表模型 ==============

class LoBatchEquipmentPerformance(Base):
    """
    机台生产过程中的批次、性能、拒片等原始数据表
    对应 datacenter.lo_batch_equipment_performance
    """
    __tablename__ = "lo_batch_equipment_performance"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="故障记录 ID")
    equipment = Column(String(50), nullable=False, comment="机台名称")
    chuck_id = Column(String(100), nullable=False, comment="Chuck ID（兼容整数与字符串）")
    lot_id = Column(String(100), nullable=False, comment="Lot ID（兼容整数与字符串）")
    wafer_index = Column(String(100), nullable=False, comment="Wafer Index（兼容整数与字符串）")
    lot_start_time = Column(DateTime(6), nullable=True, comment="Lot 开始时间")
    lot_end_time = Column(DateTime(6), nullable=True, comment="Lot 结束时间")
    wafer_product_start_time = Column(DateTime(6), nullable=False, comment="Wafer 生产开始时间")
    reject_reason = Column(BigInteger, nullable=False, comment="拒片原因 ID（外键）")

    # ── 指标列（诊断 pipeline 配置中定义的 MySQL 侧指标） ──
    wafer_translation_x = Column("wafer_translation_x", Float, nullable=True, comment="上片偏差 Tx (um)")
    wafer_translation_y = Column("wafer_translation_y", Float, nullable=True, comment="上片偏差 Ty (um)")
    wafer_rotation = Column("wafer_rotation", Float, nullable=True, comment="上片旋转 Rw (urad)")
    recipe_id = Column("recipe_id", String(500), nullable=True, comment="工艺配方 ID（ClickHouse linking）")

    # 索引
    __table_args__ = (
        Index("IDX_equipment", "equipment"),
        Index("IDX_chuck_lot_wafer", "chuck_id", "lot_id", "wafer_index"),
        Index("IDX_wafer_product_start_time", "wafer_product_start_time"),
        Index("IDX_lot_start_end_time", "lot_start_time", "lot_end_time"),
        Index("IDX_reject_reason", "reject_reason"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "equipment": self.equipment,
            "chuck_id": self.chuck_id,
            "lot_id": self.lot_id,
            "wafer_index": self.wafer_index,
            "lot_start_time": self.lot_start_time,
            "lot_end_time": self.lot_end_time,
            "wafer_product_start_time": self.wafer_product_start_time,
            "reject_reason": self.reject_reason,
            "wafer_translation_x": self.wafer_translation_x,
            "wafer_translation_y": self.wafer_translation_y,
            "wafer_rotation": self.wafer_rotation,
            "recipe_id": self.recipe_id,
        }


class RejectReasonState(Base):
    """
    拒片原因枚举值定义表
    对应 datacenter.reject_reason_state
    """
    __tablename__ = "reject_reason_state"

    reject_reason_id = Column(BigInteger, primary_key=True, comment="拒片原因 ID")
    reject_reason_value = Column(String(50), nullable=False, comment="拒片原因值")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "reject_reason_id": self.reject_reason_id,
            "reject_reason_value": self.reject_reason_value,
        }


# ============== 缓存表模型 ==============

class RejectedDetailedRecord(Base):
    """
    拒片详细记录表
    用于存储接口 2 和接口 3 的查询结果，避免重复计算

    对应 rejected_detailed_records
    """
    __tablename__ = "rejected_detailed_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    failure_id = Column(BigInteger, unique=True, nullable=False, comment="故障记录 ID（关联源表 ID）")
    equipment = Column(String(50), nullable=False, comment="机台名称")
    chuck_id = Column(String(100), nullable=False, comment="Chuck ID（兼容整数与字符串）")
    lot_id = Column(String(100), nullable=False, comment="Lot ID（兼容整数与字符串）")
    wafer_id = Column(String(100), nullable=False, comment="Wafer ID（兼容整数与字符串）")
    occurred_at = Column(DateTime(6), nullable=False, comment="故障发生时间")
    reject_reason = Column(String(50), nullable=False, comment="拒片原因值")
    reject_reason_id = Column(BigInteger, nullable=False, comment="拒片原因 ID")
    root_cause = Column(String(255), nullable=True, comment="根本原因")
    system = Column(String(50), nullable=True, comment="所属分系统")
    error_field = Column(String(255), nullable=True, comment="报错字段")
    metrics_data = Column(JSON, nullable=True, comment="指标数据（含 status）")
    created_at = Column(DateTime(6), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(6), server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 索引
    __table_args__ = (
        Index("UK_failure_id", "failure_id", unique=True),
        Index("IDX_equipment", "equipment"),
        Index("IDX_occurred_at", "occurred_at"),
        Index("IDX_chuck_lot_wafer", "chuck_id", "lot_id", "wafer_id"),
        Index("IDX_reject_reason", "reject_reason"),
    )

    def to_dict(self) -> dict:
        """转换为字典（API 返回格式）"""
        return {
            "id": self.id,
            "failureId": self.failure_id,
            "chuckId": self.chuck_id,
            "lotId": self.lot_id,
            "waferIndex": self.wafer_id,
            "rejectReason": self.reject_reason,
            "rejectReasonId": self.reject_reason_id,
            "rootCause": self.root_cause,
            "system": self.system,
            "time": int(self.occurred_at.timestamp() * 1000) if self.occurred_at else None,  # 13 位时间戳
        }


# ============== 数据库会话管理 ==============

def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """同步获取数据库会话（非生成器版本）"""
    return SessionLocal()
