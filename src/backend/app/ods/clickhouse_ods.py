"""
ODS 层 - ClickHouse 数据源封装

连接配置来源：config/connections.json，由 APP_ENV 环境变量选择环境（local/test/prod）。
只需修改 connections.json 中对应环境的 clickhouse 配置，即可切换到不同 ClickHouse 实例。

ClickHouse 表约定（SMEE LAS 系统）：
  - 时间列名：time（可通过 metrics.json 中的 time_column 字段覆盖）
  - 设备列名：equipment（可通过 metrics.json 中的 equipment_column 字段覆盖）
  - detail 字段正则提取：通过 extraction_rule 字段配置（如 "regex:Mwx\\s*\\(([\\d\\.]+)\\)"）
"""
import clickhouse_connect
import logging
import re
from typing import Optional, List, Dict, Any
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 列名默认值（若内网实际列名不同，在 metrics.json 对应指标加 time_column / equipment_column 覆盖）──
DEFAULT_TIME_COLUMN = os.environ.get("CH_DEFAULT_TIME_COLUMN", "time")
DEFAULT_EQUIPMENT_COLUMN = os.environ.get("CH_DEFAULT_EQUIPMENT_COLUMN", "equipment")


# ============== 数据库配置 ==============

def get_clickhouse_client():
    """
    获取 ClickHouse 客户端

    从 config/connections.json 读取配置，由 APP_ENV 环境变量选择环境。
    只需修改 connections.json，无需改代码。
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config", "connections.json")
    app_env = os.environ.get("APP_ENV", "local")

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            connections = json.load(f)
        config = connections.get(app_env, {}).get("clickhouse", {})
        if config:
            return clickhouse_connect.get_client(
                host=config.get("host", "localhost"),
                port=config.get("port", 8123),
                username=config.get("username", ""),
                password=config.get("password", ""),
                database=config.get("dbname", "default"),
            )

    return clickhouse_connect.get_client(
        host="localhost", port=8123, username="default", password="", database="default"
    )


# ============== ODS 数据源类 ==============

class ClickHouseODS:
    """
    ClickHouse 数据源访问类

    所有连接参数来自 config/connections.json，迁移环境时只需修改配置文件，代码不变。
    """

    def __init__(self):
        self.client = None

    def __enter__(self):
        self.client = get_clickhouse_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            self.client.close()

    @classmethod
    def query_metric_in_window(
        cls,
        table_name: str,
        column_name: str,
        equipment: str,
        time_start: datetime,
        time_end: datetime,
        reference_time: datetime,
        extraction_rule: Optional[str] = None,
        time_column: str = DEFAULT_TIME_COLUMN,
        equipment_column: str = DEFAULT_EQUIPMENT_COLUMN,
    ) -> Optional[float]:
        """
        在时间窗口 [time_start, time_end] 内查询距 reference_time 最近的指标值。

        支持两种模式：
          1. 直接列值：column_name 为数值列，直接读取并转 float
          2. detail 正则提取：column_name 为文本列（如 detail），通过 extraction_rule 提取数值
             extraction_rule 格式：`regex:<pattern>`，捕获组1为目标值

        Args:
            table_name      : 含 db 前缀的完整表名，如 "las.LOG_EH_UNION_VIEW"
            column_name     : 目标列名（数值列或文本列）
            equipment       : 机台名称
            time_start      : 时间窗口起点
            time_end        : 时间窗口终点
            reference_time  : 基准时间 T，用于"最近一条"排序
            extraction_rule : 正则提取规则，仅 detail 类列需要，如 "regex:Mwx\\s*\\(([\\d\\.]+)\\)"
            time_column     : 时间列名（默认 "time"，可被 metrics.json 的 time_column 字段覆盖）
            equipment_column: 设备列名（默认 "equipment"，可被 metrics.json 的 equipment_column 覆盖）

        Returns:
            float 或 None（窗口内无数据）
        """
        client = get_clickhouse_client()
        try:
            # ClickHouse 使用 toDateTime 处理时间参数
            ts_fmt = "%Y-%m-%d %H:%M:%S"
            t_start_str = time_start.strftime(ts_fmt)
            t_end_str   = time_end.strftime(ts_fmt)
            t_ref_str   = reference_time.strftime(ts_fmt)

            query = f"""
                SELECT {column_name}
                FROM {table_name}
                WHERE {equipment_column} = %(equipment)s
                  AND {time_column} >= toDateTime(%(t_start)s)
                  AND {time_column} <= toDateTime(%(t_end)s)
                ORDER BY abs(dateDiff('second',
                    {time_column},
                    toDateTime(%(t_ref)s)
                )) ASC
                LIMIT 1
            """
            params = {
                "equipment": equipment,
                "t_start":   t_start_str,
                "t_end":     t_end_str,
                "t_ref":     t_ref_str,
            }
            result = client.query(query, parameters=params)

            if not result.result_set:
                return None

            raw = result.result_set[0][0]

            # 正则提取模式
            if extraction_rule and str(extraction_rule).startswith("regex:"):
                pattern = extraction_rule[6:]
                match = re.search(pattern, str(raw))
                if match:
                    val_str = match.group(1) if match.groups() else match.group(0)
                    return float(val_str)
                return None

            # 直接转数值
            return float(raw) if raw is not None else None

        except Exception as e:
            logger.error("ClickHouse query_metric_in_window 失败: table=%s column=%s error=%s",
                         table_name, column_name, e)
            raise   # 由调用方决定是否降级 mock
        finally:
            client.close()

    @classmethod
    def query_log_data(
        cls,
        table_name: str,
        columns: List[str],
        filter_conditions: Dict[str, Any],
        order_by: Optional[str] = None,
        order_dir: str = "desc",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """通用日志查询，保留供其他模块使用"""
        client = get_clickhouse_client()
        try:
            select_sql = ", ".join(columns)
            where_clauses = [f"{k} = %({k})s" for k in filter_conditions]
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            order_sql = f"ORDER BY {order_by} {order_dir}" if order_by else ""
            query = f"SELECT {select_sql} FROM {table_name} WHERE {where_sql} {order_sql} LIMIT {limit}"
            result = client.query(query, parameters=filter_conditions)
            return [dict(zip(columns, row)) for row in result.result_set]
        except Exception as e:
            logger.error("ClickHouse query_log_data 失败: %s", e)
            return []
        finally:
            client.close()
