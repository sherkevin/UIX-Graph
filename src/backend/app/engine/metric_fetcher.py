"""
指标值获取器 (Metric Fetcher)

根据 metrics.json 中定义的数据源 (db_type, table_name, column_name)，
使用 equipment + 时间窗口从对应的数据库表中获取指标实际值。

设计要点：
- 基准时间 T + metrics.json 各指标 duration（分钟）→ 查询 [T-duration, T]；无 duration 时用回退窗口
- 数据源模式由环境变量 METRIC_SOURCE_MODE 控制：
    real           - ClickHouse/MySQL 不通则返回 None，不降级 mock
    mock_allowed   - 数据源不通时允许降级为 mock（默认联调模式）
    mock_forbidden - 与 real 相同效果，额外在日志中标注"生产模式禁止 mock"
- 每个 metric 独立查询，失败不影响其他 metric
- 每次诊断调用都会记录 source_type（real_mysql/real_clickhouse/mock/intermediate/none）
"""
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from app.engine.rule_loader import RuleLoader

logger = logging.getLogger(__name__)

# ── 可配置常量 ───────────────────────────────────────────────────────────────

# metrics.json 未配置 duration 时使用的回退窗口（分钟）
DEFAULT_FALLBACK_WINDOW_MINUTES = 5

# 数据源模式：real / mock_allowed / mock_forbidden
# 由环境变量 METRIC_SOURCE_MODE 控制，默认 mock_allowed（联调模式）
METRIC_SOURCE_MODE = os.environ.get("METRIC_SOURCE_MODE", "mock_allowed").lower()

# 合法模式集合
_VALID_MODES = {"real", "mock_allowed", "mock_forbidden"}
if METRIC_SOURCE_MODE not in _VALID_MODES:
    logger.warning("METRIC_SOURCE_MODE=%r 非法，回退到 mock_allowed", METRIC_SOURCE_MODE)
    METRIC_SOURCE_MODE = "mock_allowed"

logger.info("MetricFetcher 数据源模式: %s", METRIC_SOURCE_MODE)


class MetricFetcher:
    """
    指标值获取器

    根据 metrics.json 配置，从 MySQL / ClickHouse 获取指标实际值。
    本地开发环境下 ClickHouse 不可用时自动降级为模拟值。

    基准时间 T 使用 reference_time；每个指标若配置了 duration（分钟），
    查询区间为 [T - duration, T]；否则使用 fallback_duration_minutes。
    """

    def __init__(
        self,
        equipment: str,
        reference_time: datetime,
        chuck_id: int = None,
        fallback_duration_minutes: int = DEFAULT_FALLBACK_WINDOW_MINUTES,
    ):
        """
        Args:
            equipment: 机台名称
            reference_time: 分析基准时间 T（通常为 wafer_product_start_time 或请求传入的 requestTime）
            chuck_id: Chuck ID，用于某些需要 chuck_id 过滤的指标
            fallback_duration_minutes: metrics.json 未配置 duration 时的回退窗口（分钟）
        """
        self.equipment = equipment
        self.reference_time = reference_time
        self.chuck_id = chuck_id
        self.fallback_duration_minutes = fallback_duration_minutes

        self.rule_loader = RuleLoader()

        # 本次实例的指标来源记录：{ metric_id: source_type }
        # source_type: real_mysql / real_clickhouse / mock / intermediate / none
        self.source_log: Dict[str, str] = {}

    def _duration_minutes_for_meta(self, meta: Dict[str, Any]) -> int:
        raw = meta.get("duration")
        if raw is not None:
            try:
                return int(str(raw).strip())
            except ValueError:
                logger.warning("指标 duration 无效: %r，使用回退 %s 分钟", raw, self.fallback_duration_minutes)
        return self.fallback_duration_minutes

    def window_for_metric(self, meta: Dict[str, Any]) -> Tuple[datetime, datetime]:
        """返回该指标配置对应的时间窗 [start, end]，end 为基准时间 T。"""
        mins = self._duration_minutes_for_meta(meta)
        end = self.reference_time
        start = end - timedelta(minutes=mins)
        return start, end

    def fetch_all(self, metric_ids: List[str]) -> Dict[str, Optional[float]]:
        """
        批量获取指标值

        Args:
            metric_ids: 需要获取的指标 ID 列表

        Returns:
            { metric_id: value (float or None) }
        """
        result = {}
        for mid in metric_ids:
            try:
                result[mid] = self._fetch_one(mid)
            except Exception as e:
                logger.warning("获取指标 %s 失败: %s", mid, e)
                self.source_log[mid] = "none"
                result[mid] = None
        return result

    def _fetch_one(self, metric_id: str) -> Optional[float]:
        """
        获取单个指标值

        根据 metrics.json 中的 db_type 分发到对应的查询方法。
        不在 metrics.json 中的指标视为中间计算值（模型输出/计数器），
        使用 _mock_intermediate_value 提供合理的模拟值。
        """
        meta = self.rule_loader.get_metric_meta(metric_id)
        if meta is None:
            # 不在 metrics.json 中 — 可能是模型输出或中间计数器
            val = self._mock_intermediate_value(metric_id)
            self.source_log[metric_id] = "intermediate"
            return val

        db_type = meta.get("db_type", "").lower()

        if db_type == "mysql":
            return self._fetch_from_mysql(metric_id, meta)
        elif db_type == "clickhouse":
            return self._fetch_from_clickhouse(metric_id, meta)
        elif db_type == "intermediate":
            # 中间计算量（模型输出/计数器），无法从 DB 直接查，使用模拟值
            logger.debug("指标 %s 为 intermediate 类型，使用模拟值", metric_id)
            val = self._mock_intermediate_value(metric_id)
            self.source_log[metric_id] = "intermediate"
            return val
        else:
            logger.warning("指标 %s 的 db_type=%s 不支持", metric_id, db_type)
            self.source_log[metric_id] = "none"
            return None

    # ── MySQL 取数 ──────────────────────────────────────────────────────────

    def _fetch_from_mysql(self, metric_id: str, meta: Dict[str, Any]) -> Optional[float]:
        """
        从 MySQL 获取指标值

        当前支持真实查询的 MySQL 指标（来自 lo_batch_equipment_performance）：
        - Tx (wafer_translation_x)
        - Ty (wafer_translation_y)
        - Rw (wafer_rotation)

        其他 MySQL 指标（如 mc_config_commits_history）当前使用 mock；
        内网阶段按需实现真实查询。
        """
        table_name = meta.get("table_name", "")
        column_name = meta.get("column_name", "")

        if "lo_batch_equipment_performance" in table_name:
            return self._fetch_from_performance_table(metric_id, column_name, meta)

        if "mc_config_commits_history" in table_name:
            return self._fetch_from_config_history(metric_id, column_name, meta)

        # 其他 MySQL 表：当前不支持真实查询
        if METRIC_SOURCE_MODE in ("real", "mock_forbidden"):
            logger.warning(
                "MySQL 指标 %s 来自未实现真实查询的表 %s（METRIC_SOURCE_MODE=%s），返回 None",
                metric_id, table_name, METRIC_SOURCE_MODE,
            )
            self.source_log[metric_id] = "none"
            return None

        logger.info("MySQL 指标 %s 来自 %s，使用模拟值（mock_allowed）", metric_id, table_name)
        val = self._mock_value(metric_id, meta)
        self.source_log[metric_id] = "mock"
        return val

    def _fetch_from_performance_table(
        self, metric_id: str, column_name: str, meta: Dict[str, Any]
    ) -> Optional[float]:
        """
        从 lo_batch_equipment_performance 查询指标值

        使用 equipment + 该指标 duration 对应的时间窗口，取与 T 最接近的记录。
        """
        from app.ods.datacenter_ods import DatacenterODS, LoBatchEquipmentPerformance, SessionLocal
        from sqlalchemy import func

        time_start, time_end = self.window_for_metric(meta)

        db = SessionLocal()
        try:
            # 动态获取列
            col = getattr(LoBatchEquipmentPerformance, column_name, None)
            if col is None:
                logger.warning("列 %s 不存在于 lo_batch_equipment_performance", column_name)
                self.source_log[metric_id] = "none"
                return None

            # 查询：equipment + 时间窗口，取最接近 reference_time (T) 的一条
            record = (
                db.query(col)
                .filter(
                    LoBatchEquipmentPerformance.equipment == self.equipment,
                    LoBatchEquipmentPerformance.wafer_product_start_time >= time_start,
                    LoBatchEquipmentPerformance.wafer_product_start_time <= time_end,
                )
                .order_by(
                    func.abs(
                        func.timestampdiff(
                            func.text("SECOND"),
                            LoBatchEquipmentPerformance.wafer_product_start_time,
                            self.reference_time,
                        )
                    )
                )
                .first()
            )

            if record and record[0] is not None:
                self.source_log[metric_id] = "real_mysql"
                return float(record[0])

            logger.info(
                "指标 %s (%s) 在时间窗口 [%s, %s] 内无数据",
                metric_id, column_name, time_start, time_end,
            )
            self.source_log[metric_id] = "none"
            return None

        except Exception as e:
            logger.error("查询 %s 失败: %s", column_name, e)
            self.source_log[metric_id] = "none"
            return None
        finally:
            db.close()

    # ── mc_config_commits_history 取数（Sx / Sy） ────────────────────────────

    def _fetch_from_config_history(
        self, metric_id: str, column_name: str, meta: Dict[str, Any]
    ) -> Optional[float]:
        """
        从 datacenter.mc_config_commits_history 查询静态上片偏差（Sx / Sy）。

        该表记录机台配置变更历史，data 列存储配置 JSON 或文本。
        查询逻辑：equipment + 时间窗口内最近一条，用 extraction_rule 从 data 列提取数值。

        metrics.json 配置示例（Sx）：
          "Sx": {
            "db_type": "mysql",
            "table_name": "datacenter.mc_config_commits_history",
            "column_name": "data",
            "extraction_rule": "json:Sx",          <- 从 JSON 取 key "Sx"
            "duration": "1000"
          }

        extraction_rule 支持：
          json:<key>   - 解析 JSON 后取 key 对应的数值
          regex:<pat>  - 正则提取，第1捕获组为目标值
          （不填）     - 直接转 float
        """
        import re as _re
        import json as _json

        from app.ods.datacenter_ods import SessionLocal
        from sqlalchemy import text

        time_start, time_end = self.window_for_metric(meta)
        extraction_rule = meta.get("extraction_rule", "")

        db = SessionLocal()
        try:
            # mc_config_commits_history 表假定列：equipment, committed_at（时间）, data（内容）
            # 若列名不同，可在 metrics.json 中增加 time_column / equipment_column 覆盖
            time_col  = meta.get("time_column", "committed_at")
            equip_col = meta.get("equipment_column", "equipment")

            sql = text(f"""
                SELECT {column_name}
                FROM mc_config_commits_history
                WHERE {equip_col} = :equipment
                  AND {time_col} >= :time_start
                  AND {time_col} <= :time_end
                ORDER BY ABS(TIMESTAMPDIFF(SECOND, {time_col}, :ref_time)) ASC
                LIMIT 1
            """)
            row = db.execute(sql, {
                "equipment":  self.equipment,
                "time_start": time_start,
                "time_end":   time_end,
                "ref_time":   self.reference_time,
            }).fetchone()

            if row is None or row[0] is None:
                logger.info("mc_config_commits_history: 指标 %s 在时间窗口内无数据", metric_id)
                self.source_log[metric_id] = "none"
                return None

            raw = str(row[0])

            # extraction_rule 解析
            if extraction_rule.startswith("json:"):
                key = extraction_rule[5:].strip()
                try:
                    data_obj = _json.loads(raw)
                    val = data_obj.get(key)
                    if val is not None:
                        self.source_log[metric_id] = "real_mysql"
                        return float(val)
                except (_json.JSONDecodeError, ValueError):
                    pass
                logger.warning("mc_config_commits_history: JSON 提取 key=%s 失败，raw=%r", key, raw[:100])
                self.source_log[metric_id] = "none"
                return None

            elif extraction_rule.startswith("regex:"):
                pattern = extraction_rule[6:]
                match = _re.search(pattern, raw)
                if match:
                    val_str = match.group(1) if match.groups() else match.group(0)
                    self.source_log[metric_id] = "real_mysql"
                    return float(val_str)
                logger.warning("mc_config_commits_history: regex 提取失败，pattern=%s raw=%r", pattern, raw[:100])
                self.source_log[metric_id] = "none"
                return None

            else:
                # 无 extraction_rule，直接转 float
                self.source_log[metric_id] = "real_mysql"
                return float(raw)

        except Exception as e:
            logger.error("mc_config_commits_history 查询失败: metric=%s error=%s", metric_id, e)
            if METRIC_SOURCE_MODE in ("real", "mock_forbidden"):
                self.source_log[metric_id] = "none"
                return None
            # mock_allowed 降级
            val = self._mock_value(metric_id, meta)
            self.source_log[metric_id] = "mock"
            return val
        finally:
            db.close()

    # ── ClickHouse 取数 ──────────────────────────────────────────────────────

    def _fetch_from_clickhouse(self, metric_id: str, meta: Dict[str, Any]) -> Optional[float]:
        """
        从 ClickHouse 获取指标值。

        当前（外网联调阶段）：
          - METRIC_SOURCE_MODE=real 或 mock_forbidden：尝试真实查询；不通时返回 None（不 mock）
          - METRIC_SOURCE_MODE=mock_allowed（默认）：不通时降级为 mock 值

        内网部署时实现真实 ClickHouse 查询（见 TODO 注释）并设置 METRIC_SOURCE_MODE=real。

        ClickHouse 查询示例（供内网实现参考）：
          SELECT {column_name} FROM {table_name}
          WHERE equipment = '{self.equipment}'
            AND time >= '{time_start}' AND time <= '{time_end}'
          ORDER BY ABS(dateDiff('second', time, toDateTime('{self.reference_time}')))
          LIMIT 1
        如有 extraction_rule（regex），需从 detail 字段提取值。
        """
        time_start, time_end = self.window_for_metric(meta)

        # 真实 ClickHouse 查询（连接参数来自 config/connections.json，迁移时只改配置）
        try:
            from app.ods.clickhouse_ods import ClickHouseODS
            value = ClickHouseODS.query_metric_in_window(
                table_name=meta["table_name"],
                column_name=meta["column_name"],
                equipment=self.equipment,
                time_start=time_start,
                time_end=time_end,
                reference_time=self.reference_time,
                extraction_rule=meta.get("extraction_rule"),
                time_column=meta.get("time_column", "time"),
                equipment_column=meta.get("equipment_column", "equipment"),
            )
            if value is not None:
                self.source_log[metric_id] = "real_clickhouse"
                return value
            # ClickHouse 可连通但窗口内无数据
            logger.info(
                "ClickHouse 指标 %s 窗口内无数据: table=%s window=[%s, %s]",
                metric_id, meta.get("table_name", ""), time_start, time_end,
            )
            self.source_log[metric_id] = "none"
            return None

        except Exception as ch_err:
            # ClickHouse 不可达或查询出错
            if METRIC_SOURCE_MODE in ("real", "mock_forbidden"):
                logger.error(
                    "ClickHouse 查询失败，METRIC_SOURCE_MODE=%s 禁止降级 mock: "
                    "metric=%s table=%s error=%s",
                    METRIC_SOURCE_MODE, metric_id, meta.get("table_name", ""), ch_err,
                )
                self.source_log[metric_id] = "none"
                return None

            # mock_allowed：连不上 ClickHouse 时降级为模拟值
            logger.warning(
                "ClickHouse 不可达，降级为模拟值 (METRIC_SOURCE_MODE=mock_allowed): "
                "metric=%s table=%s error=%s",
                metric_id, meta.get("table_name", ""), ch_err,
            )
            val = self._mock_value(metric_id, meta)
            self.source_log[metric_id] = "mock"
            return val

    # ── Mock 值生成 ──────────────────────────────────────────────────────────

    def _mock_value(self, metric_id: str, meta: Dict[str, Any]) -> float:
        """
        为不可用的数据源生成合理的模拟值

        根据 metric_id 的语义生成有意义的数值范围。
        """
        mock_ranges = {
            # COWA 倍率相关
            "Mwx_0": (0.99985, 1.00015),       # 倍率值，接近 1
            # 标记对准位置
            "ws_pos_x": (-5.0, 5.0),
            "ws_pos_y": (-5.0, 5.0),
            "mark_pos_x": (-3.0, 3.0),
            "mark_pos_y": (-3.0, 3.0),
            # 台对准建模结果
            "Msx": (0.9999, 1.0001),
            "Msy": (0.9999, 1.0001),
            "e_ws_x": (-2.0, 2.0),
            "e_ws_y": (-2.0, 2.0),
            # 静态上片偏差
            "Sx": (-1.0, 1.0),
            "Sy": (-1.0, 1.0),
            # 建模输出（这些是 rules.json 中 step 10/11 的 results）
            "D_x": (-0.5, 0.5),
            "D_y": (-0.5, 0.5),
        }

        if metric_id in mock_ranges:
            low, high = mock_ranges[metric_id]
            return round(random.uniform(low, high), 6)

        # 默认：返回一个小范围随机值
        return round(random.uniform(-10.0, 10.0), 4)

    def _mock_intermediate_value(self, metric_id: str) -> float:
        """
        为中间计算值（不在 metrics.json 中的指标）生成模拟值

        这些指标是 rules.json 决策树中的：
        - 模型输出（output_Tx, output_Ty, output_Rw, output_Mw）
        - 计数器（n_88um）
        """
        intermediate_values = {
            # 建模次数 — 给一个 ≤8 的值，走正常分支
            "n_88um": 3.0,
            # COWA 建模输出 — 给正常范围内的值
            "output_Mw": 5.0,        # between (-20, 20) → 正常
            "output_Tx": None,       # 将用源记录 Tx 替代
            "output_Ty": None,       # 将用源记录 Ty 替代
            "output_Rw": None,       # 将用源记录 Rw 替代
            # 汇总计数
            "normal_count": 0.0,
        }

        if metric_id in intermediate_values:
            val = intermediate_values[metric_id]
            if val is not None:
                logger.info("中间指标 %s 使用模拟值: %s", metric_id, val)
                return val

        logger.info("中间指标 %s 无模拟值", metric_id)
        return None

    # ── 直接从源记录获取指标值 ────────────────────────────────────────────────

    def fetch_from_source_record(
        self, source_record: Dict[str, Any], metric_ids: List[str]
    ) -> Dict[str, Optional[float]]:
        """
        从源记录字典中直接提取已有的指标值

        对于 lo_batch_equipment_performance 表中直接存在的列
        (wafer_translation_x, wafer_translation_y, wafer_rotation)，
        直接从源记录字典中取值，避免额外 DB 查询。

        同时，模型输出 (output_Tx, output_Ty, output_Rw) 使用源记录的
        实际 Tx/Ty/Rw 值作为近似（因为本地无法运行实际建模函数）。

        Args:
            source_record: 源表记录字典
            metric_ids: 指标 ID 列表

        Returns:
            { metric_id: value }
        """
        # 指标 ID → 源记录字段名 映射
        METRIC_TO_COLUMN = {
            "Tx": "wafer_translation_x",
            "Ty": "wafer_translation_y",
            "Rw": "wafer_rotation",
            # 模型输出近似为源记录的实际值
            "output_Tx": "wafer_translation_x",
            "output_Ty": "wafer_translation_y",
            "output_Rw": "wafer_rotation",
        }

        result = {}
        remaining = []

        for mid in metric_ids:
            col = METRIC_TO_COLUMN.get(mid)
            if col and col in source_record and source_record[col] is not None:
                result[mid] = float(source_record[col])
                self.source_log[mid] = "real_mysql"
            else:
                remaining.append(mid)

        # 对剩余指标使用常规获取方式
        if remaining:
            fetched = self.fetch_all(remaining)
            result.update(fetched)

        return result
