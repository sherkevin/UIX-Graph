"""
ODS 层 - Datacenter 数据源封装
封装 MySQL datacenter 数据库的访问
"""
from sqlalchemy import create_engine, Column, String, Integer, BigInteger, Boolean, Text, JSON, DateTime, Float, ForeignKey, Index, func, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import PoolProxiedConnection
from typing import Optional, List, Dict, Any, Tuple
import json
import os
import logging
from datetime import datetime

# 导入工具函数
from app.utils.time_utils import timestamp_to_datetime
from app.utils import detail_trace

logger = logging.getLogger(__name__)


# ============== 数据库配置 ==============

def get_mysql_engine() -> Any:
    """
    获取 MySQL 数据库引擎

    从 config/connections.json 读取配置
    优先级：local > test > prod > 默认配置
    """
    uix_root = os.environ.get("UIX_ROOT")
    if uix_root:
        config_path = os.path.join(uix_root, "config", "connections.json")
    else:
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config", "connections.json")

    # 通过环境变量控制使用哪个环境的配置（默认 local，内网设置 APP_ENV=prod 或 test）
    app_env = os.environ.get("APP_ENV", "local")

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            connections = json.load(f)
            # 按 APP_ENV 指定的环境读取，fallback 到 local
            config = connections.get(app_env, {}).get("mysql", {})
            if not config and app_env != "local":
                config = connections.get("local", {}).get("mysql", {})
            if config:
                return create_engine(
                    f"mysql+pymysql://{config.get('username', 'root')}:"
                    f"{config.get('password', '')}@"
                    f"{config.get('host', 'localhost')}:"
                    f"{config.get('port', 3306)}/"
                    f"{config.get('dbname', 'datacenter')}",
                    pool_pre_ping=True,
                    pool_size=10,
                    max_overflow=20,
                    echo=False
                )

    # 默认配置（本地开发）
    return create_engine(
        "mysql+pymysql://root:root@localhost:3306/datacenter",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False
    )


# 创建数据库引擎
engine = get_mysql_engine()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基类
Base = declarative_base()

# reject_reason_state 内存缓存（启动时加载一次，避免每次 JOIN）
_reason_map_cache: Optional[Dict[int, str]] = None


def _get_reason_map(db: Any) -> Dict[int, str]:
    """惰性加载拒片原因映射表，缓存到模块变量，避免重复查询"""
    global _reason_map_cache
    if _reason_map_cache is None:
        results = db.query(
            RejectReasonState.reject_reason_id,
            RejectReasonState.reject_reason_value
        ).all()
        _reason_map_cache = {r.reject_reason_id: r.reject_reason_value for r in results}
        logger.info("[ODS] reason_map loaded: %d entries", len(_reason_map_cache))
    return _reason_map_cache


# ============== ORM 模型定义 ==============

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


class RejectReasonState(Base):
    """
    拒片原因枚举值定义表
    对应 datacenter.reject_reason_state
    """
    __tablename__ = "reject_reason_state"

    reject_reason_id = Column(BigInteger, primary_key=True, comment="拒片原因 ID")
    reject_reason_value = Column(String(50), nullable=False, comment="拒片原因值")


# ============== ODS 数据源类 ==============

class DatacenterODS:
    """
    Datacenter 数据源访问类

    提供对 MySQL datacenter 数据库的封装访问
    """

    @staticmethod
    def get_session() -> Session:
        """获取数据库会话"""
        return SessionLocal()

    @classmethod
    def query_chuck_lot_wafer(
        cls,
        equipment: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        db: Optional[Session] = None
    ) -> List[Tuple[int, int, int]]:
        """
        查询 Chuck-Lot-Wafer 层级关系（仅含存在拒片故障的记录）

        与接口 2 搜索一致：排除 reject_reason 为 NONE_REJECTED 的行，
        下拉选项只展示当前时间窗内实际出现过故障的 Chuck/Lot/Wafer。

        Args:
            equipment: 机台名称
            start_time: 查询起始时间（可选）
            end_time: 查询结束时间（可选）
            db: 数据库会话（可选，如果为 None 则创建新会话）

        Returns:
            [(chuck_id, lot_id, wafer_index), ...]
        """
        should_close = False
        if db is None:
            db = cls.get_session()
            should_close = True

        try:
            logger.info("[ODS] query_chuck_lot_wafer | equipment=%s start=%s end=%s", equipment, start_time, end_time)
            detail_trace.info(
                "ODS metadata 查询 | equipment=%s | start=%s | end=%s",
                equipment,
                start_time,
                end_time,
            )
            reason_map = _get_reason_map(db)
            none_rejected_ids = [rid for rid, val in reason_map.items() if val == "NONE_REJECTED"]

            query = db.query(
                LoBatchEquipmentPerformance.chuck_id,
                LoBatchEquipmentPerformance.lot_id,
                LoBatchEquipmentPerformance.wafer_index
            ).filter(
                LoBatchEquipmentPerformance.equipment == equipment
            )
            if none_rejected_ids:
                query = query.filter(
                    LoBatchEquipmentPerformance.reject_reason.notin_(none_rejected_ids)
                )

            # 时间范围筛选：与 search 保持一致，均用 wafer_product_start_time
            if start_time is not None:
                query = query.filter(LoBatchEquipmentPerformance.wafer_product_start_time >= start_time)
            if end_time is not None:
                query = query.filter(LoBatchEquipmentPerformance.wafer_product_start_time <= end_time)

            # DISTINCT + 硬上限：防止超大时间范围返回几万行卡死
            METADATA_MAX_ROWS = 5000
            results = query.distinct().limit(METADATA_MAX_ROWS).all()
            logger.info(
                "[ODS] query_chuck_lot_wafer | equipment=%s -> %d distinct rows (cap=%d)",
                equipment, len(results), METADATA_MAX_ROWS
            )
            detail_trace.info(
                "ODS metadata 结果 | equipment=%s | rows=%s | none_rejected_ids=%s",
                equipment,
                len(results),
                detail_trace.preview(none_rejected_ids, 200),
            )
            if len(results) >= METADATA_MAX_ROWS:
                logger.warning(
                    "[ODS] query_chuck_lot_wafer | equipment=%s 已达上限 %d，建议缩小时间范围",
                    equipment, METADATA_MAX_ROWS
                )
            return results
        finally:
            if should_close:
                db.close()

    @classmethod
    def query_reject_reason_value(
        cls,
        reason_id: int,
        db: Optional[Session] = None
    ) -> Optional[str]:
        """
        根据拒片原因 ID 查询拒片原因值

        Args:
            reason_id: 拒片原因 ID
            db: 数据库会话

        Returns:
            拒片原因值，如果不存在则返回 None
        """
        should_close = False
        if db is None:
            db = cls.get_session()
            should_close = True

        try:
            result = db.query(RejectReasonState.reject_reason_value).filter(
                RejectReasonState.reject_reason_id == reason_id
            ).first()
            return result[0] if result else None
        finally:
            if should_close:
                db.close()

    @classmethod
    def query_all_reject_reasons(
        cls,
        db: Optional[Session] = None
    ) -> Dict[int, str]:
        """
        查询所有拒片原因

        Args:
            db: 数据库会话

        Returns:
            {reason_id: reason_value, ...}
        """
        should_close = False
        if db is None:
            db = cls.get_session()
            should_close = True

        try:
            results = db.query(RejectReasonState).all()
            return {r.reject_reason_id: r.reject_reason_value for r in results}
        finally:
            if should_close:
                db.close()

    @classmethod
    def query_failure_records(
        cls,
        equipment: str,
        chucks: Optional[List[Any]] = None,
        lots: Optional[List[Any]] = None,
        wafers: Optional[List[Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        order_by: str = "time",
        order_dir: str = "desc",
        offset: int = 0,
        limit: int = 20,
        db: Optional[Session] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        查询拒片故障记录列表

        Args:
            equipment: 机台名称
            chucks: Chuck ID 列表（可选）
            lots: Lot ID 列表（可选）
            wafers: Wafer ID 列表（可选）
            start_time: 查询起始时间（可选）
            end_time: 查询结束时间（可选）
            order_by: 排序字段（"time" 或 "id"）
            order_dir: 排序方向（"asc" 或 "desc"）
            offset: 偏移量
            limit: 限制数量
            db: 数据库会话

        Returns:
            (记录列表，总数)
        """
        should_close = False
        if db is None:
            db = cls.get_session()
            should_close = True

        try:
            logger.info(
                "[ODS] query_failure_records | equipment=%s chucks=%s lots=%s wafers=%s start=%s end=%s",
                equipment, chucks, lots, wafers, start_time, end_time
            )
            detail_trace.info(
                "ODS 列表查询入口 | equipment=%s | chucks=%s | lots=%s | wafers=%s | start=%s | end=%s | offset=%s | limit=%s | order=%s/%s",
                equipment,
                detail_trace.preview(chucks, 160),
                detail_trace.preview(lots, 160),
                detail_trace.preview(wafers, 160),
                start_time,
                end_time,
                offset,
                limit,
                order_by,
                order_dir,
            )

            # 加载拒片原因缓存，找出 NONE_REJECTED 对应的 reason_id 列表
            reason_map = _get_reason_map(db)
            none_rejected_ids = [rid for rid, val in reason_map.items() if val == "NONE_REJECTED"]

            # ── 步骤 1：不带 JOIN 的简单 COUNT（快 3-5x） ──────────────────────
            count_query = db.query(func.count(LoBatchEquipmentPerformance.id)).filter(
                LoBatchEquipmentPerformance.equipment == equipment
            )
            if none_rejected_ids:
                count_query = count_query.filter(
                    LoBatchEquipmentPerformance.reject_reason.notin_(none_rejected_ids)
                )
            if chucks is not None and len(chucks) > 0:
                count_query = count_query.filter(LoBatchEquipmentPerformance.chuck_id.in_(chucks))
            if lots is not None and len(lots) > 0:
                count_query = count_query.filter(LoBatchEquipmentPerformance.lot_id.in_(lots))
            if wafers is not None and len(wafers) > 0:
                count_query = count_query.filter(LoBatchEquipmentPerformance.wafer_index.in_(wafers))
            if start_time is not None:
                count_query = count_query.filter(LoBatchEquipmentPerformance.wafer_product_start_time >= start_time)
            if end_time is not None:
                count_query = count_query.filter(LoBatchEquipmentPerformance.wafer_product_start_time <= end_time)
            total = count_query.scalar() or 0

            logger.info("[ODS] query_failure_records | equipment=%s total=%d", equipment, total)
            detail_trace.info("ODS 列表 count 完成 | equipment=%s | total=%s", equipment, total)

            # ── 步骤 2：无 JOIN，直接查主表，reason 从内存缓存拼接（快 2-3x） ─
            data_query = db.query(
                LoBatchEquipmentPerformance.id,
                LoBatchEquipmentPerformance.equipment,
                LoBatchEquipmentPerformance.chuck_id,
                LoBatchEquipmentPerformance.lot_id,
                LoBatchEquipmentPerformance.wafer_index,
                LoBatchEquipmentPerformance.wafer_product_start_time,
                LoBatchEquipmentPerformance.reject_reason,
            ).filter(
                LoBatchEquipmentPerformance.equipment == equipment
            )

            if none_rejected_ids:
                data_query = data_query.filter(
                    LoBatchEquipmentPerformance.reject_reason.notin_(none_rejected_ids)
                )
            if chucks is not None and len(chucks) > 0:
                data_query = data_query.filter(LoBatchEquipmentPerformance.chuck_id.in_(chucks))
            if lots is not None and len(lots) > 0:
                data_query = data_query.filter(LoBatchEquipmentPerformance.lot_id.in_(lots))
            if wafers is not None and len(wafers) > 0:
                data_query = data_query.filter(LoBatchEquipmentPerformance.wafer_index.in_(wafers))
            if start_time is not None:
                data_query = data_query.filter(LoBatchEquipmentPerformance.wafer_product_start_time >= start_time)
            if end_time is not None:
                data_query = data_query.filter(LoBatchEquipmentPerformance.wafer_product_start_time <= end_time)

            # 排序（reason 按 ID 排序，因为已无 JOIN，无法按 value 排序）
            if order_by == "reason":
                col = LoBatchEquipmentPerformance.reject_reason
                data_query = data_query.order_by(col.desc() if order_dir == "desc" else col.asc())
            elif order_by == "time":
                col = LoBatchEquipmentPerformance.wafer_product_start_time
                data_query = data_query.order_by(col.desc() if order_dir == "desc" else col.asc())
            else:
                col = LoBatchEquipmentPerformance.id
                data_query = data_query.order_by(col.desc() if order_dir == "desc" else col.asc())

            records = data_query.offset(offset).limit(limit).all()
            detail_trace.info(
                "ODS 列表 data 完成 | equipment=%s | 本页行数=%s",
                equipment,
                len(records),
            )

            # reason value 从内存缓存拼接，避免 JOIN
            result = [
                {
                    "id": r.id,
                    "equipment": r.equipment,
                    "chuck_id": r.chuck_id,
                    "lot_id": r.lot_id,
                    "wafer_index": r.wafer_index,
                    "wafer_product_start_time": r.wafer_product_start_time,
                    "reject_reason": r.reject_reason,
                    "reject_reason_value": reason_map.get(r.reject_reason, str(r.reject_reason) if r.reject_reason else None)
                }
                for r in records
            ]

            detail_trace.info(
                "ODS 列表返回 | equipment=%s | total=%s | page_rows=%s | sample_ids=%s",
                equipment,
                total,
                len(result),
                detail_trace.preview([r["id"] for r in result[:5]], 120),
            )
            return result, total
        finally:
            if should_close:
                db.close()

    @classmethod
    def get_failure_record_by_id(
        cls,
        failure_id: int,
        db: Optional[Session] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据 ID 获取单条故障记录（含指标列）

        Args:
            failure_id: 故障记录 ID
            db: 数据库会话

        Returns:
            故障记录字典，如果不存在则返回 None
        """
        should_close = False
        if db is None:
            db = cls.get_session()
            should_close = True

        try:
            detail_trace.info("ODS 详情查询入口 | failure_id=%s", failure_id)
            record = db.query(
                LoBatchEquipmentPerformance.id,
                LoBatchEquipmentPerformance.equipment,
                LoBatchEquipmentPerformance.chuck_id,
                LoBatchEquipmentPerformance.lot_id,
                LoBatchEquipmentPerformance.wafer_index,
                LoBatchEquipmentPerformance.wafer_product_start_time,
                LoBatchEquipmentPerformance.reject_reason,
                RejectReasonState.reject_reason_value,
                # 指标列
                LoBatchEquipmentPerformance.wafer_translation_x,
                LoBatchEquipmentPerformance.wafer_translation_y,
                LoBatchEquipmentPerformance.wafer_rotation,
                LoBatchEquipmentPerformance.recipe_id,
            ).outerjoin(
                RejectReasonState,
                LoBatchEquipmentPerformance.reject_reason == RejectReasonState.reject_reason_id
            ).filter(
                LoBatchEquipmentPerformance.id == failure_id
            ).first()

            if not record:
                detail_trace.warning("ODS 详情查询未命中 | failure_id=%s", failure_id)
                return None

            result = {
                "id": record.id,
                "equipment": record.equipment,
                "chuck_id": record.chuck_id,
                "lot_id": record.lot_id,
                "wafer_index": record.wafer_index,
                "wafer_product_start_time": record.wafer_product_start_time,
                "reject_reason": record.reject_reason,
                "reject_reason_value": record.reject_reason_value,
                # 指标列
                "wafer_translation_x": record.wafer_translation_x,
                "wafer_translation_y": record.wafer_translation_y,
                "wafer_rotation": record.wafer_rotation,
                "recipe_id": record.recipe_id,
                "wafer_id": str(record.wafer_index) if record.wafer_index is not None else None,
            }
            detail_trace.info(
                "ODS 详情查询命中 | failure_id=%s | equipment=%s | chuck=%s | lot=%s | wafer=%s | reject_reason=%s",
                failure_id,
                result.get("equipment"),
                result.get("chuck_id"),
                result.get("lot_id"),
                result.get("wafer_index"),
                result.get("reject_reason"),
            )
            return result
        finally:
            if should_close:
                db.close()
