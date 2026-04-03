# -*- coding: utf-8 -*-
"""
Service 层 - 拒片故障管理业务逻辑

提供元数据查询、搜索、详情等业务服务。

核心流程：
- 接口 1 (get_metadata): 查询 Chuck→Lot→Wafer 层级结构
- 接口 2 (search_reject_errors): 查询故障列表，从缓存表补充 rootCause/system
- 接口 3 (get_failure_details): 查询故障详情 + 诊断引擎计算指标
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import json
import os
import logging

from app.utils.time_utils import timestamp_to_datetime, datetime_to_timestamp
from app.ods.datacenter_ods import DatacenterODS
from app.models.reject_errors_db import RejectedDetailedRecord, get_db_session
from app.engine.diagnosis_engine import DiagnosisEngine

logger = logging.getLogger(__name__)


class RejectErrorService:
    """
    拒片故障管理服务类

    提供拒片故障相关的业务逻辑处理
    """

    # 机台枚举白名单
    EQUIPMENT_WHITELIST = [
        "SSB8000", "SSB8001", "SSB8002", "SSB8005",
        "SSC8001", "SSC8002", "SSC8003", "SSC8004", "SSC8005", "SSC8006"
    ]

    # 诊断引擎（每次模块重载后重新初始化）
    _diagnosis_engine: Optional[DiagnosisEngine] = None

    @classmethod
    def get_diagnosis_engine(cls) -> DiagnosisEngine:
        """获取诊断引擎（每次重新创建以获取最新 rules.json）"""
        if cls._diagnosis_engine is None:
            # 强制 RuleLoader 重新加载配置
            from app.engine.rule_loader import RuleLoader
            RuleLoader._instance = None
            RuleLoader._loaded = False
            cls._diagnosis_engine = DiagnosisEngine(time_window_minutes=5)
        return cls._diagnosis_engine

    @classmethod
    def validate_equipment(cls, equipment: str) -> bool:
        """验证机台名称是否合法"""
        return equipment in cls.EQUIPMENT_WHITELIST

    @classmethod
    def validate_wafer_ids(cls, wafer_ids) -> Tuple[bool, Optional[str]]:
        """验证 Wafer ID 列表是否合法（兼容整数与字符串格式）"""
        if wafer_ids is None:
            return True, None
        for wafer_id in wafer_ids:
            try:
                v = int(wafer_id)
                if not (1 <= v <= 25):
                    return False, f"无效的 Wafer ID: {wafer_id}。整数 Wafer 必须在 1-25 范围内"
            except (ValueError, TypeError):
                pass  # 字符串格式 wafer_id（如 W01_CARRIER_38_6）不做范围校验
        return True, None

    # =========================================================================
    # 接口 1：获取筛选元数据
    # =========================================================================

    @classmethod
    def get_metadata(
        cls,
        equipment: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取筛选元数据（Chuck → Lot → Wafer 层级结构）

        根据机台 + 时间范围筛选可选的 Chuck/Lot/Wafer 组合；
        仅包含在对应范围内出现过拒片故障（非 NONE_REJECTED）的记录，
        与 search 接口的故障集合一致。

        Args:
            equipment: 机台名称
            start_time: 查询起始时间（13 位时间戳，可选）
            end_time: 查询结束时间（13 位时间戳，可选）

        Returns:
            [{ chuckId, chuckName, availableLots: [{ lotId, lotName, availableWafers }] }]
        """
        logger.info("[Service] get_metadata | equipment=%s start_time=%s end_time=%s", equipment, start_time, end_time)

        if not cls.validate_equipment(equipment):
            raise ValueError(f"无效的机台名称：{equipment}")

        start_dt = timestamp_to_datetime(start_time)
        end_dt = timestamp_to_datetime(end_time)

        records = DatacenterODS.query_chuck_lot_wafer(
            equipment=equipment,
            start_time=start_dt,
            end_time=end_dt
        )
        logger.info("[Service] get_metadata | equipment=%s -> %d raw chuck/lot/wafer rows", equipment, len(records))

        # 组织数据：Chuck → Lot → Wafers
        chuck_data = {}
        for chuck_id, lot_id, wafer_index in records:
            if chuck_id not in chuck_data:
                chuck_data[chuck_id] = {"lots": {}}
            if lot_id not in chuck_data[chuck_id]["lots"]:
                chuck_data[chuck_id]["lots"][lot_id] = set()
            chuck_data[chuck_id]["lots"][lot_id].add(wafer_index)

        def _sort_key(v):
            """兼容整数/字符串的排序键：整数优先按数值，字符串按字母"""
            try:
                return (0, int(v))
            except (ValueError, TypeError):
                return (1, str(v))

        # 转换为响应格式
        response_data = []
        for chuck_id, lot_data in sorted(chuck_data.items(), key=lambda x: _sort_key(x[0])):
            chuck_info = {
                "chuckId": chuck_id,
                "chuckName": f"Chuck {chuck_id}",
                "availableLots": []
            }
            for lot_id, wafers in sorted(lot_data["lots"].items(), key=lambda x: _sort_key(x[0])):
                lot_info = {
                    "lotId": lot_id,
                    "lotName": f"Lot {lot_id}",
                    "availableWafers": sorted(list(wafers), key=_sort_key)
                }
                chuck_info["availableLots"].append(lot_info)
            response_data.append(chuck_info)

        logger.info("[Service] get_metadata | equipment=%s -> %d chucks in response", equipment, len(response_data))
        return response_data

    # =========================================================================
    # 接口 2：查询拒片故障记录
    # =========================================================================

    @classmethod
    def search_reject_errors(
        cls,
        equipment: str,
        page_no: int = 1,
        page_size: int = 20,
        chucks: Optional[List[Any]] = None,
        lots: Optional[List[Any]] = None,
        wafers: Optional[List[Any]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        order_by: str = "time",
        order_dir: str = "desc"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        搜索拒片故障记录

        先从源表查询基础数据，然后从缓存表 rejected_detailed_records
        补充 rootCause 和 system（如果已被接口3诊断过）。

        Returns:
            (记录列表, 分页元数据)
        """
        logger.info(
            "[Service] search_reject_errors | equipment=%s page=%d/%d chucks=%s lots=%s wafers=%s start=%s end=%s order=%s/%s",
            equipment, page_no, page_size, chucks, lots, wafers, start_time, end_time, order_by, order_dir
        )

        if not cls.validate_equipment(equipment):
            raise ValueError(f"无效的机台名称：{equipment}")

        is_valid, error_msg = cls.validate_wafer_ids(wafers)
        if not is_valid:
            raise ValueError(error_msg)

        # 空数组拦截
        if (
            (chucks is not None and len(chucks) == 0) or
            (lots is not None and len(lots) == 0) or
            (wafers is not None and len(wafers) == 0)
        ):
            logger.info("[Service] search_reject_errors | equipment=%s empty filter array -> return 0", equipment)
            return [], {
                "total": 0,
                "pageNo": page_no,
                "pageSize": page_size,
                "totalPages": 0
            }

        start_dt = timestamp_to_datetime(start_time)
        end_dt = timestamp_to_datetime(end_time)
        offset = (page_no - 1) * page_size

        records, total = DatacenterODS.query_failure_records(
            equipment=equipment,
            chucks=chucks,
            lots=lots,
            wafers=wafers,
            start_time=start_dt,
            end_time=end_dt,
            order_by=order_by,
            order_dir=order_dir,
            offset=offset,
            limit=page_size
        )

        logger.info("[Service] search_reject_errors | equipment=%s -> total=%d this_page=%d", equipment, total, len(records))
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if page_no > total_pages and total > 0:
            return [], {
                "total": total,
                "pageNo": page_no,
                "pageSize": page_size,
                "totalPages": total_pages
            }

        # 从缓存表批量查询已诊断的 rootCause / system
        failure_ids = [r["id"] for r in records]
        cache_map = cls._batch_get_cache(failure_ids) if failure_ids else {}

        # 转换为响应格式
        response_records = []
        for record in records:
            fid = record["id"]
            cached = cache_map.get(fid)

            response_records.append({
                "id": fid,
                "failureId": fid,
                "chuckId": record["chuck_id"],
                "lotId": record["lot_id"],
                "waferIndex": record["wafer_index"],
                "rejectReason": record["reject_reason_value"] or f"UNKNOWN_{record['reject_reason']}",
                "rejectReasonId": record["reject_reason"],
                "rootCause": cached.root_cause if cached else None,
                "time": datetime_to_timestamp(record["wafer_product_start_time"]),
                "system": cached.system if cached else None,
            })

        return response_records, {
            "total": total,
            "pageNo": page_no,
            "pageSize": page_size,
            "totalPages": total_pages
        }

    @classmethod
    def _batch_get_cache(cls, failure_ids: List[int]) -> Dict[int, RejectedDetailedRecord]:
        """
        从缓存表批量查询已诊断的记录

        Args:
            failure_ids: 故障记录 ID 列表

        Returns:
            { failure_id: RejectedDetailedRecord }
        """
        if not failure_ids:
            return {}

        db = get_db_session()
        try:
            cached_records = db.query(RejectedDetailedRecord).filter(
                RejectedDetailedRecord.failure_id.in_(failure_ids)
            ).all()
            return {r.failure_id: r for r in cached_records}
        except Exception as e:
            logger.warning("批量查询缓存表失败: %s", e)
            return {}
        finally:
            db.close()

    # =========================================================================
    # 接口 3：获取拒片故障详情（含指标数据 + 诊断引擎）
    # =========================================================================

    @classmethod
    def get_failure_details(
        cls,
        failure_id: int,
        page_no: int = 1,
        page_size: int = 20,
        request_time_ms: Optional[int] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        获取故障详情（含指标数据）

        流程：
        1. 若传入 requestTime 且与记录发生时间不一致 → 跳过缓存读写
        2. 否则先查缓存表 rejected_detailed_records，命中则直接返回
        3. 缓存未命中 → 查源表 → 运行诊断引擎（基准时间 T）→ 条件允许时写入缓存 → 返回

        Args:
            failure_id: 故障记录 ID
            page_no: 指标分页页码
            page_size: 指标分页大小
            request_time_ms: 可选，分析基准时间 T（13 位毫秒）；未传则 T 为 wafer_product_start_time

        Returns:
            (详情数据, 分页元数据)
        """
        empty_meta = {
            "total": 0,
            "pageNo": page_no,
            "pageSize": page_size,
            "totalPages": 0,
        }

        db = get_db_session()
        try:
            source_record: Optional[Dict[str, Any]] = None
            bypass_cache = False

            if request_time_ms is not None:
                source_record = DatacenterODS.get_failure_record_by_id(failure_id, db)
                if not source_record:
                    return None, empty_meta
                # 前端详情页始终携带 requestTime。这里统一绕过缓存，避免 rules.json
                # 或阈值判定逻辑更新后仍复用旧 metrics_data，导致详情页展示过期结果。
                bypass_cache = True

            if not bypass_cache:
                cached = db.query(RejectedDetailedRecord).filter(
                    RejectedDetailedRecord.failure_id == failure_id
                ).first()
                if cached:
                    logger.info("缓存命中: failure_id=%s", failure_id)
                    return cls._build_detail_from_cache(cached, page_no, page_size)

            if source_record is None:
                source_record = DatacenterODS.get_failure_record_by_id(failure_id, db)
                if not source_record:
                    return None, empty_meta

            if request_time_ms is not None:
                ref_dt = timestamp_to_datetime(request_time_ms)
            else:
                ref_dt = source_record["wafer_product_start_time"]
                if isinstance(ref_dt, str):
                    ref_dt = datetime.fromisoformat(ref_dt)

            # ── 运行诊断引擎 ──
            engine = cls.get_diagnosis_engine()
            reject_reason_id = source_record.get("reject_reason")

            if engine.can_diagnose(reject_reason_id):
                logger.info(
                    "运行诊断引擎: failure_id=%s, reject_reason=%s, bypass_cache=%s",
                    failure_id, reject_reason_id, bypass_cache,
                )
                diagnosis = engine.diagnose(source_record, reference_time=ref_dt)
                logger.info(
                    "诊断完成: failure_id=%s rootCause=%r system=%r errorField=%r diagnosed=%s "
                    "bypass_cache=%s reference_time=%s trace=%s",
                    failure_id, diagnosis.root_cause, diagnosis.system,
                    diagnosis.error_field, diagnosis.is_diagnosed,
                    bypass_cache, ref_dt, diagnosis.trace,
                )
                # 记录各指标的数据来源（供排障，不暴露给前端响应）
                if hasattr(engine, '_last_fetcher') and engine._last_fetcher is not None:
                    _source_log = engine._last_fetcher.source_log
                    if _source_log:
                        mock_metrics = [k for k, v in _source_log.items() if v == "mock"]
                        real_metrics = [k for k, v in _source_log.items() if v.startswith("real")]
                        logger.info(
                            "指标来源统计: failure_id=%s 真实=%s mock=%s",
                            failure_id, real_metrics, mock_metrics,
                        )

                if not bypass_cache:
                    cls._save_to_cache(db, source_record, diagnosis)

                detail_data = {
                    "failureId": source_record["id"],
                    "equipment": source_record["equipment"],
                    "chuckId": source_record["chuck_id"],
                    "lotId": source_record["lot_id"],
                    "waferIndex": source_record["wafer_index"],
                    "errorField": diagnosis.error_field or None,
                    "rejectReason": source_record["reject_reason_value"] or f"UNKNOWN_{reject_reason_id}",
                    "rejectReasonId": reject_reason_id,
                    "rootCause": diagnosis.root_cause,
                    "system": diagnosis.system,
                    "time": datetime_to_timestamp(source_record["wafer_product_start_time"]),
                }
                all_metrics = diagnosis.metrics
            else:
                logger.info("reject_reason=%s 不支持诊断", reject_reason_id)
                detail_data = {
                    "failureId": source_record["id"],
                    "equipment": source_record["equipment"],
                    "chuckId": source_record["chuck_id"],
                    "lotId": source_record["lot_id"],
                    "waferIndex": source_record["wafer_index"],
                    "errorField": None,
                    "rejectReason": source_record["reject_reason_value"] or f"UNKNOWN_{reject_reason_id}",
                    "rejectReasonId": reject_reason_id,
                    "rootCause": None,
                    "system": None,
                    "time": datetime_to_timestamp(source_record["wafer_product_start_time"]),
                }
                all_metrics = []

            return cls._paginate_metrics(detail_data, all_metrics, page_no, page_size)

        except Exception as e:
            logger.error("获取故障详情失败: failure_id=%s, error=%s", failure_id, e, exc_info=True)
            raise
        finally:
            db.close()

    @classmethod
    def _build_detail_from_cache(
        cls,
        cached: RejectedDetailedRecord,
        page_no: int,
        page_size: int,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """从缓存记录构建详情响应"""
        detail_data = {
            "failureId": cached.failure_id,
            "equipment": cached.equipment,
            "chuckId": cached.chuck_id,
            "lotId": cached.lot_id,
            "waferIndex": cached.wafer_id,
            "errorField": cached.error_field,
            "rejectReason": cached.reject_reason,
            "rejectReasonId": cached.reject_reason_id,
            "rootCause": cached.root_cause,
            "system": cached.system,
            "time": datetime_to_timestamp(cached.occurred_at),
        }

        # 解析缓存的指标数据
        metrics_raw = cached.metrics_data or []
        all_metrics = []
        for m in metrics_raw:
            all_metrics.append({
                "name": m.get("name", ""),
                "value": m.get("value", 0),
                "unit": m.get("unit", ""),
                "status": m.get("status", "NORMAL"),
                "type": m.get("type", "diagnostic"),
                "threshold": {
                    "operator": m.get("threshold", {}).get("operator", ""),
                    "limit": m.get("threshold", {}).get("limit", 0),
                    "display": m.get("threshold", {}).get("display"),
                },
            })

        # ABNORMAL 置顶
        all_metrics.sort(key=lambda x: (0 if x.get("status") == "ABNORMAL" else 1))

        return cls._paginate_metrics(detail_data, all_metrics, page_no, page_size)

    @classmethod
    def _paginate_metrics(
        cls,
        detail_data: Dict[str, Any],
        all_metrics: List[Dict[str, Any]],
        page_no: int,
        page_size: int,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """对指标列表分页"""
        total = len(all_metrics)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        if page_no > total_pages and total > 0:
            paged_metrics = []
        else:
            start_idx = (page_no - 1) * page_size
            end_idx = start_idx + page_size
            paged_metrics = all_metrics[start_idx:end_idx]

        detail_data["metrics"] = paged_metrics

        return detail_data, {
            "total": total,
            "pageNo": page_no,
            "pageSize": page_size,
            "totalPages": total_pages,
        }

    @classmethod
    def _save_to_cache(
        cls,
        db,
        source_record: Dict[str, Any],
        diagnosis,
    ) -> None:
        """
        将诊断结果写入缓存表 rejected_detailed_records（幂等写入）

        使用 SELECT + INSERT/UPDATE 两步确保并发安全：
        - 若 failure_id 已存在缓存行：直接返回（首次诊断结果优先，不覆盖）
        - 若不存在：INSERT 新行；若并发 INSERT 触发唯一键冲突：rollback 后静默忽略

        Args:
            db: 数据库会话
            source_record: 源表记录
            diagnosis: DiagnosisResult 诊断结果
        """
        fid = source_record["id"]
        try:
            # 先检查是否已存在（防止并发重复写入导致唯一键冲突）
            existing = db.query(RejectedDetailedRecord).filter(
                RejectedDetailedRecord.failure_id == fid
            ).first()
            if existing:
                logger.debug("缓存已存在，跳过写入: failure_id=%s", fid)
                return

            reason_value = source_record.get("reject_reason_value") or ""

            cached_record = RejectedDetailedRecord(
                failure_id=fid,
                equipment=source_record["equipment"],
                chuck_id=source_record["chuck_id"],
                lot_id=source_record["lot_id"],
                wafer_id=source_record["wafer_index"],
                occurred_at=source_record["wafer_product_start_time"],
                reject_reason=reason_value,
                reject_reason_id=source_record["reject_reason"],
                root_cause=diagnosis.root_cause,
                system=diagnosis.system,
                error_field=diagnosis.error_field or None,
                metrics_data=diagnosis.metrics,
            )

            db.add(cached_record)
            db.commit()
            logger.info("诊断结果已缓存: failure_id=%s", fid)

        except Exception as e:
            db.rollback()
            # 唯一键冲突（并发写入）属于预期情况，降级为 debug 日志
            err_str = str(e).lower()
            if "duplicate" in err_str or "unique" in err_str:
                logger.debug("缓存写入冲突（并发）已忽略: failure_id=%s", fid)
            else:
                logger.error("缓存写入失败: failure_id=%s, error=%s", fid, e)
            # 不抛出异常，缓存失败不影响当次返回
