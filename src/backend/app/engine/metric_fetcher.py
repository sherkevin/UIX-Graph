"""统一的指标取数器。"""
import json
import logging
import os
import random
import time
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.diagnosis.config_store import DiagnosisConfigStore
from app.engine.rule_loader import RuleLoader
from app.utils import detail_trace

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_WINDOW_DAYS = 7

METRIC_SOURCE_MODE = os.environ.get("METRIC_SOURCE_MODE", "mock_allowed").lower()
_VALID_MODES = {"real", "mock_allowed", "mock_forbidden"}
if METRIC_SOURCE_MODE not in _VALID_MODES:
    logger.warning("METRIC_SOURCE_MODE=%r 非法，回退到 mock_allowed", METRIC_SOURCE_MODE)
    METRIC_SOURCE_MODE = "mock_allowed"


def _safe_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", str(name)):
        raise ValueError(f"非法 SQL 标识符: {name}")
    return str(name)


class MetricFetcher:
    """根据 pipeline 中的 source_kind 解析指标值。"""

    def __init__(
        self,
        equipment: str,
        reference_time: datetime,
        chuck_id: Any = None,
        fallback_duration_days: int = DEFAULT_FALLBACK_WINDOW_DAYS,
        pipeline_id: str = "reject_errors",
        params: Optional[Dict[str, Any]] = None,
        source_record: Optional[Dict[str, Any]] = None,
    ):
        self.equipment = equipment
        self.reference_time = reference_time
        self.chuck_id = chuck_id
        self.fallback_duration_days = fallback_duration_days
        self.pipeline_id = pipeline_id
        self.params = params or {}
        self.source_record = source_record or {}
        self.rule_loader = RuleLoader(pipeline_id=pipeline_id)
        self.store = DiagnosisConfigStore()
        self.pipeline = self.store.get_pipeline(pipeline_id)
        self.source_log: Dict[str, str] = {}

    def _duration_days_for_meta(self, meta: Dict[str, Any]) -> int:
        raw = meta.get("duration")
        if raw is not None:
            try:
                return int(str(raw).strip())
            except ValueError:
                logger.warning("指标 duration 无效: %r，使用回退 %s 天", raw, self.fallback_duration_days)
        return self.fallback_duration_days

    def window_for_metric(self, meta: Dict[str, Any]) -> Tuple[datetime, datetime]:
        days = self._duration_days_for_meta(meta)
        end = self.reference_time
        start = end - timedelta(days=days)
        return start, end

    def fetch_all(self, metric_ids: List[str], extra_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        resolved_context: Dict[str, Any] = dict(extra_context or {})
        t_batch = time.perf_counter()
        for metric_id in metric_ids:
            t0 = time.perf_counter()
            try:
                value = self._fetch_one(metric_id, resolved_context)
                result[metric_id] = value
                resolved_context[metric_id] = value
                meta = self.rule_loader.get_metric_meta(metric_id) or {}
                source_kind = str(meta.get("source_kind", "")).strip().lower()
                source_kind = {
                    "mysql": "mysql_nearest_row",
                    "clickhouse": "clickhouse_window",
                }.get(source_kind, source_kind)
                if source_kind in {"mysql_nearest_row", "clickhouse_window"}:
                    window_values = list(value or [])
                    result[f"{metric_id}_window"] = window_values
                    resolved_context[f"{metric_id}_window"] = window_values
            except Exception as exc:
                logger.warning("获取指标 %s 失败: %s", metric_id, exc)
                self.source_log[metric_id] = "none"
                result[metric_id] = None
                result[f"{metric_id}_window"] = []
                resolved_context[metric_id] = None
                resolved_context[f"{metric_id}_window"] = []
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                src = self.source_log.get(metric_id, "?")
                detail_trace.info(
                    "  [指标] %s | 耗时=%.1fms | source=%s",
                    metric_id,
                    elapsed_ms,
                    src,
                )
        detail_trace.info(
            "metric_fetch_all 批合计 | 指标数=%s | 批耗时=%.1fms",
            len(metric_ids),
            (time.perf_counter() - t_batch) * 1000,
        )
        return result

    def _fetch_one(self, metric_id: str, extra_context: Optional[Dict[str, Any]] = None) -> Any:
        meta = self.rule_loader.get_metric_meta(metric_id)
        if meta is None:
            # post-stage4 Bug #5 fix:统一走 _mock_value(空 meta 时返回通用随机)
            value = self._mock_value(metric_id, {})
            self.source_log[metric_id] = "intermediate"
            return value

        if meta.get("enabled") is False:
            logger.debug("指标 %s 已禁用 (enabled=false)，跳过取数", metric_id)
            self.source_log[metric_id] = "disabled"
            return None

        source_kind = str(meta.get("source_kind", "")).strip().lower()
        source_kind = {
            "mysql": "mysql_nearest_row",
            "clickhouse": "clickhouse_window",
        }.get(source_kind, source_kind)
        if source_kind in {"failure_record_field", "request_param"}:
            return None
        if source_kind == "mysql_nearest_row":
            return self._fetch_from_mysql(metric_id, meta, extra_context=extra_context)
        if source_kind == "clickhouse_window":
            return self._fetch_from_clickhouse(metric_id, meta, extra_context=extra_context)
        if source_kind == "intermediate":
            # post-stage4 Bug #5 fix:intermediate 类也统一走 _mock_value
            # (action 没写 results 时,mock_value/mock_range 给出占位值;否则 action
            #  覆盖之)。新增 intermediate metric 无需改 Python,只需在配置里写
            #  mock_value 或 mock_range。
            value = self._mock_value(metric_id, meta)
            self.source_log[metric_id] = "intermediate"
            return value
        dynamic_handler = getattr(self, f"_fetch_from_{source_kind}", None)
        if callable(dynamic_handler):
            return dynamic_handler(metric_id, meta)
        logger.warning("指标 %s 的 source_kind=%s 不支持", metric_id, source_kind)
        self.source_log[metric_id] = "none"
        return None

    def _extract_scalar(self, raw: Any) -> Any:
        if raw is None:
            return None
        if isinstance(raw, (bool, int, float)):
            return raw
        if isinstance(raw, str):
            value = raw.strip()
            lowered = value.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except ValueError:
                return value
        return raw

    def _apply_transform(self, value: Any, transform: Dict[str, Any]) -> Any:
        if value is None or not transform:
            return value
        transform_type = str(transform.get("type", "")).strip().lower()
        if transform_type == "equals":
            return value == transform.get("value")
        if transform_type == "not_equals":
            return value != transform.get("value")
        if transform_type == "float":
            return float(value)
        if transform_type == "int":
            return int(value)
        if transform_type == "bool":
            return bool(value)
        if transform_type == "upper_equals":
            return str(value).upper() == str(transform.get("value", "")).upper()
        if transform_type == "lower_equals":
            return str(value).lower() == str(transform.get("value", "")).lower()
        if transform_type == "contains":
            return str(transform.get("value", "")) in str(value)
        if transform_type == "map":
            mapping = transform.get("mapping", {}) or {}
            return mapping.get(str(value), mapping.get(value, value))
        logger.warning("未知 transform.type=%s，保留原值", transform_type)
        return value

    def _apply_data_type(self, metric_id: str, value: Any, meta: Dict[str, Any]) -> Any:
        if value is None:
            return None
        raw_data_type = meta.get("data_type")
        if raw_data_type is None:
            return value
        data_type = str(raw_data_type).strip().lower()
        if not data_type:
            return value
        try:
            if data_type in {"float", "double", "number"}:
                return float(value)
            if data_type in {"int", "integer"}:
                return int(float(value))
            if data_type in {"bool", "boolean"}:
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "1", "yes", "y"}:
                        return True
                    if lowered in {"false", "0", "no", "n"}:
                        return False
                return bool(value)
            if data_type in {"str", "string", "text"}:
                return str(value)
        except (TypeError, ValueError) as exc:
            logger.warning("指标 %s data_type=%s 转换失败: %s", metric_id, data_type, exc)
            return value
        logger.warning("指标 %s 未知 data_type=%s，保留原值", metric_id, data_type)
        return value

    def _extract_direct_metric(self, metric_id: str, source_record: Dict[str, Any]) -> Tuple[bool, Any]:
        meta = self.rule_loader.get_metric_meta(metric_id)
        if meta is None:
            return False, None

        source_kind = str(meta.get("source_kind", "")).strip().lower()
        if source_kind not in {"failure_record_field", "request_param"}:
            return False, None

        field_name = str(meta.get("field", "")).strip()
        raw = None
        if source_kind == "failure_record_field":
            raw = source_record.get(field_name)
        else:
            raw = self.params.get(field_name)
            if raw is None:
                raw = source_record.get(field_name)
            if raw is None and isinstance(source_record.get("params"), dict):
                raw = source_record["params"].get(field_name)

        value = self._extract_scalar(raw)
        value = self._apply_transform(value, meta.get("transform", {}))
        value = self._apply_data_type(metric_id, value, meta)
        if value is None:
            return True, None
        self.source_log[metric_id] = "real_input"
        return True, value

    def fetch_from_source_record(self, source_record: Dict[str, Any], metric_ids: List[str]) -> Dict[str, Any]:
        self.source_record = source_record or {}
        result: Dict[str, Any] = {}
        remaining: List[str] = []
        direct_ids: List[str] = []

        for metric_id in metric_ids:
            handled, value = self._extract_direct_metric(metric_id, source_record)
            if handled:
                direct_ids.append(metric_id)
                result[metric_id] = value
                if value is None and metric_id not in self.source_log:
                    self.source_log[metric_id] = "none"
                continue
            remaining.append(metric_id)

        detail_trace.info(
            "fetch_from_source_record 分流 | 请求数=%s | 直接字段=%s | 需fetch_all=%s | direct_ids=%s | remaining_ids=%s",
            len(metric_ids),
            len(direct_ids),
            len(remaining),
            detail_trace.preview(direct_ids, 320),
            detail_trace.preview(remaining, 320),
        )

        if remaining:
            with detail_trace.span("metric_fetch_all", remaining=len(remaining)):
                result.update(self.fetch_all(remaining, extra_context=result))
        return result

    @staticmethod
    def _normalize_linking(meta: Dict[str, Any]) -> Dict[str, Any]:
        linking = meta.get("linking") or {}
        if not isinstance(linking, dict):
            linking = {}
        return {
            "mode": str(linking.get("mode", "time_window_only")).strip().lower(),
            "keys": list(linking.get("keys") or []),
            "filters": list(linking.get("filters") or []),
        }

    @staticmethod
    def _fallback_policy(meta: Dict[str, Any]) -> str:
        fallback = meta.get("fallback") or {}
        if not isinstance(fallback, dict):
            return "none"
        return str(fallback.get("policy", "none")).strip().lower()

    def _resolve_context_value(self, name: str, time_filter: datetime, extra_context: Dict[str, Any]) -> Any:
        mapping = {
            "equipment": self.equipment,
            "chuck_id": self.chuck_id,
            "time_filter": time_filter,
            "reference_time": self.reference_time,
        }
        if isinstance(self.source_record, dict):
            mapping.update(self.source_record)
        mapping.update(self.params)
        mapping.update(extra_context)
        chuck_value = mapping.get("chuck_id")
        try:
            if chuck_value is not None:
                mapping["chuck_index0"] = int(float(chuck_value)) - 1
        except (TypeError, ValueError):
            pass
        return mapping.get(name)

    def _resolve_filter_value(self, token: str, time_filter: datetime, extra_context: Dict[str, Any]) -> Any:
        token = str(token).strip()
        placeholder = re.fullmatch(r"\{(\w+)\}", token)
        if placeholder:
            return self._resolve_context_value(placeholder.group(1), time_filter, extra_context)
        return self._extract_scalar(token)

    def _build_linking_clauses(
        self,
        linking_items: List[Dict[str, Any]],
        time_filter: datetime,
        extra_context: Dict[str, Any],
        index_seed: int = 0,
        placeholder_style: str = "mysql",
    ) -> Tuple[List[str], Dict[str, Any], int, bool]:
        clauses: List[str] = []
        params: Dict[str, Any] = {}
        idx = index_seed
        missing_required = False

        for item in linking_items or []:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target", "")).strip()
            if not target:
                continue
            operator = str(item.get("operator", "=")).strip()
            if operator not in {"=", "==", "!=", ">", ">=", "<", "<=", "contains", "in"}:
                raise ValueError(f"linking.operator 不支持: {operator}")
            if "source" in item:
                value = self._resolve_context_value(str(item.get("source", "")).strip(), time_filter, extra_context)
            else:
                value = item.get("value")
            if value is None:
                missing_required = True
                continue
            param_name = f"link_{idx}"
            sql_operator = "=" if operator == "==" else operator
            target_ident = _safe_identifier(target)
            if sql_operator == "contains":
                placeholder = f":{param_name}" if placeholder_style == "mysql" else f"%({param_name})s"
                if placeholder_style == "clickhouse":
                    clauses.append(f"positionUTF8(toString({target_ident}), toString({placeholder})) > 0")
                else:
                    clauses.append(f"INSTR(CAST({target_ident} AS CHAR), CAST({placeholder} AS CHAR)) > 0")
                params[param_name] = value
                idx += 1
                continue
            if sql_operator == "in":
                values = list(value) if isinstance(value, (list, tuple, set)) else [value]
                if not values:
                    missing_required = True
                    continue
                placeholders: List[str] = []
                for sub_index, sub_value in enumerate(values):
                    item_param_name = f"{param_name}_{sub_index}"
                    placeholders.append(
                        f":{item_param_name}" if placeholder_style == "mysql" else f"%({item_param_name})s"
                    )
                    params[item_param_name] = sub_value
                if placeholder_style == "clickhouse":
                    placeholders_sql = ", ".join(f"toString({ph})" for ph in placeholders)
                    clauses.append(f"toString({target_ident}) IN ({placeholders_sql})")
                else:
                    clauses.append(f"{target_ident} IN ({', '.join(placeholders)})")
                idx += 1
                continue
            placeholder = f":{param_name}" if placeholder_style == "mysql" else f"%({param_name})s"
            if placeholder_style == "clickhouse" and sql_operator in {"=", "!="}:
                # ClickHouse 本地替身与内网参考在部分 linking 列上存在 String/Int 混用，
                # 这里统一按字符串比较，避免类型不一致导致联调失败。
                clauses.append(f"toString({target_ident}) {sql_operator} toString({placeholder})")
            else:
                clauses.append(f"{target_ident} {sql_operator} {placeholder}")
            params[param_name] = value
            idx += 1

        return clauses, params, idx, missing_required

    def _build_metric_filters(
        self,
        meta: Dict[str, Any],
        time_filter: datetime,
        include_exact_keys: bool,
        include_linking_filters: bool,
        placeholder_style: str = "mysql",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[str], Dict[str, Any], bool]:
        linking = self._normalize_linking(meta)
        clauses: List[str] = []
        params: Dict[str, Any] = {}
        idx = 0
        missing_required = False
        resolved_context = extra_context or {}

        if include_exact_keys and linking["mode"] == "exact_keys":
            key_clauses, key_params, idx, key_missing = self._build_linking_clauses(
                linking["keys"], time_filter, resolved_context, idx, placeholder_style
            )
            clauses.extend(key_clauses)
            params.update(key_params)
            missing_required = missing_required or key_missing

        if include_linking_filters:
            filter_clauses, filter_params, idx, filter_missing = self._build_linking_clauses(
                linking["filters"], time_filter, resolved_context, idx, placeholder_style
            )
            clauses.extend(filter_clauses)
            params.update(filter_params)
            missing_required = missing_required or filter_missing

        return clauses, params, missing_required

    @staticmethod
    def _join_sql_clauses(clauses: List[str]) -> str:
        if not clauses:
            return ""
        return " AND " + " AND ".join(clauses)

    def _query_mysql_window(
        self,
        table_name: str,
        column_name: str,
        time_column: str,
        equipment_column: str,
        time_start: datetime,
        time_end: datetime,
        where_sql: str,
        where_params: Dict[str, Any],
        omit_equipment_filter: bool = False,
    ) -> List[Any]:
        from app.ods.datacenter_ods import SessionLocal

        detail_trace.info(
            "    [MySQL查询] table=%s column=%s time=[%s, %s] omit_equipment=%s where_sql=%s params=%s",
            table_name,
            column_name,
            time_start,
            time_end,
            omit_equipment_filter,
            detail_trace.preview(where_sql, 300),
            detail_trace.preview(where_params, 400),
        )
        if omit_equipment_filter:
            where_equipment = ""
            base_params: Dict[str, Any] = {
                "time_start": time_start,
                "time_end": time_end,
                "ref_time": self.reference_time,
            }
        else:
            where_equipment = f"{equipment_column} = :equipment AND "
            base_params = {
                "equipment": self.equipment,
                "time_start": time_start,
                "time_end": time_end,
                "ref_time": self.reference_time,
            }

        sql = text(
            f"""
            SELECT {column_name}
            FROM {table_name}
            WHERE {where_equipment}{time_column} >= :time_start
              AND {time_column} <= :time_end
              {where_sql}
            ORDER BY ABS(TIMESTAMPDIFF(SECOND, {time_column}, :ref_time)) ASC
            """
        )
        db = SessionLocal()
        try:
            t0 = time.perf_counter()
            rows = db.execute(
                sql,
                {
                    **base_params,
                    **where_params,
                },
            ).fetchall()
            detail_trace.info(
                "    [MySQL查询完成] table=%s column=%s rows=%s 耗时=%.1fms",
                table_name,
                column_name,
                len(rows),
                (time.perf_counter() - t0) * 1000,
            )
            return [row[0] for row in rows if row is not None]
        finally:
            db.close()

    def _render_mysql_filters(self, filter_condition: Optional[str], time_filter: datetime, extra_context: Dict[str, Any]):
        if not filter_condition:
            return "", {}
        sql_expr, params, parsed = self._render_mysql_filter_expr(
            str(filter_condition),
            time_filter,
            extra_context,
            index_seed=0,
        )
        if not parsed or not sql_expr:
            return "", {}
        return f" AND ({sql_expr})", params

    def _render_mysql_filter_expr(
        self,
        expr: str,
        time_filter: datetime,
        extra_context: Dict[str, Any],
        index_seed: int = 0,
    ) -> Tuple[str, Dict[str, Any], int]:
        text_expr = str(expr or "").strip()
        if not text_expr:
            return "", {}, index_seed
        text_expr = self._strip_outer_parentheses(text_expr)

        or_parts = self._split_top_level_boolean(text_expr, "OR")
        if len(or_parts) > 1:
            sql_parts: List[str] = []
            params: Dict[str, Any] = {}
            idx = index_seed
            for part in or_parts:
                sub_sql, sub_params, idx = self._render_mysql_filter_expr(part, time_filter, extra_context, idx)
                if sub_sql:
                    sql_parts.append(f"({sub_sql})")
                    params.update(sub_params)
            return " OR ".join(sql_parts), params, idx

        and_parts = self._split_top_level_boolean(text_expr, "AND")
        if len(and_parts) > 1:
            sql_parts = []
            params = {}
            idx = index_seed
            for part in and_parts:
                sub_sql, sub_params, idx = self._render_mysql_filter_expr(part, time_filter, extra_context, idx)
                if sub_sql:
                    sql_parts.append(sub_sql)
                    params.update(sub_params)
            return " AND ".join(sql_parts), params, idx

        match = re.fullmatch(r"([A-Za-z_]\w*)\s*(==|=|>=|<=|>|<)\s*(.+)", text_expr)
        if not match:
            logger.warning("filter_condition 片段无法解析，已忽略: %s", text_expr)
            return "", {}, index_seed
        column_name, operator, raw_value = match.groups()
        param_name = f"filter_{index_seed}"
        value = self._resolve_filter_value(raw_value, time_filter, extra_context)
        if value is None:
            return "", {}, index_seed + 1
        clause = f"{_safe_identifier(column_name)} {operator} :{param_name}"
        return clause, {param_name: value}, index_seed + 1

    @staticmethod
    def _strip_outer_parentheses(expr: str) -> str:
        text_expr = expr.strip()
        while text_expr.startswith("(") and text_expr.endswith(")"):
            depth = 0
            closed_at_end = True
            for idx, ch in enumerate(text_expr):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and idx != len(text_expr) - 1:
                        closed_at_end = False
                        break
            if depth != 0 or not closed_at_end:
                break
            text_expr = text_expr[1:-1].strip()
        return text_expr

    @staticmethod
    def _split_top_level_boolean(expr: str, op: str) -> List[str]:
        parts: List[str] = []
        buf: List[str] = []
        depth = 0
        i = 0
        op_text = f" {op} "
        upper_expr = expr.upper()
        while i < len(expr):
            ch = expr[i]
            if ch == "(":
                depth += 1
                buf.append(ch)
                i += 1
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                buf.append(ch)
                i += 1
                continue
            if depth == 0 and upper_expr[i:i + len(op_text)] == op_text:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += len(op_text)
                continue
            buf.append(ch)
            i += 1
        last = "".join(buf).strip()
        if last:
            parts.append(last)
        return parts

    def _render_extraction_template(
        self,
        template: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        渲染 extraction_rule 模板里的 {var} 占位符。

        post-stage4 Bug #7 fix:如果 var 解析到 list(window 类指标常态),
        过去会 str([1.0, 2.0]) 拼成 '[1.0, 2.0]' 塞进 jsonpath/regex,
        导致后续 _extract_json_path_value / re.search **静默失败**(返回 None,
        无任何 warning,排障极困难)。
        现在:取 list 中第一个非 None 元素 + warning;全空则视为缺失。
        """
        resolved_context = extra_context or {}
        missing = False

        def _replace(match: re.Match[str]) -> str:
            nonlocal missing
            var_name = match.group(1)
            value = self._resolve_context_value(var_name, self.reference_time, resolved_context)
            if value is None:
                missing = True
                return ""
            if isinstance(value, list):
                non_null = [v for v in value if v is not None]
                if not non_null:
                    missing = True
                    return ""
                logger.warning(
                    "extraction template 变量 %s 解析为 list(len=%d),"
                    "取第一个非空元素 %r 拼到模板;若需完整列表语义,请在 jsonpath 中"
                    "避免引用 window 类指标(改用其标量派生)",
                    var_name, len(value), non_null[0],
                )
                return str(non_null[0])
            return str(value)

        rendered = re.sub(r"\{(\w+)\}", _replace, str(template or ""))
        if missing:
            return None
        return rendered

    # 兼容 jsonpath segment 形如 'chuck_message[0]' (剥离方括号、N 当数组下标)。
    # 模块级编译一次,避免每次调用重新编译。
    _NAME_INDEX_RE = re.compile(r"^(\w+)\[(\d+)\]$")

    @staticmethod
    def _extract_json_path_value(data: Any, path: str) -> Any:
        """
        按 '/' 分段解析 jsonpath。每段支持以下三种形式:
          - 'foo'        : dict key
          - '0'/'1'/...  : 数组下标(当前 current 必须是 list)
          - 'foo[0]'     : 等价于 'foo/0',先在 dict 取 foo,再在结果 list 取下标
        
        最后一种形式是为 reject_errors.diagnosis.json 中:
          jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x
        渲染后 'chuck_message[0]' 这种 segment 设计的。
        与 'foo/0' 的写法**双向兼容**。
        """
        current = data
        for segment in [part for part in str(path or "").split("/") if part]:
            # 形式 3: 'name[N]' 复合 segment(dict.name → list[N])
            m = MetricFetcher._NAME_INDEX_RE.match(segment)
            if m:
                key, idx_str = m.group(1), m.group(2)
                if not isinstance(current, dict):
                    return None
                current = current.get(key)
                if not isinstance(current, list):
                    return None
                idx = int(idx_str)
                if idx < 0 or idx >= len(current):
                    return None
                current = current[idx]
                continue
            # 形式 2: 数组下标
            if isinstance(current, list):
                if not segment.isdigit():
                    return None
                index = int(segment)
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
                continue
            # 形式 1: dict key
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
            if current is None:
                return None
        return current

    def _apply_extraction_rule(
        self,
        raw: Any,
        extraction_rule: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if raw is None:
            return None
        rule = str(extraction_rule or "").strip()
        if not rule:
            return self._extract_scalar(raw)
        if rule.startswith("json:"):
            key = rule[5:].strip()
            try:
                data = json.loads(str(raw))
            except json.JSONDecodeError:
                return None
            return self._extract_scalar(data.get(key))
        if rule.startswith("jsonpath:"):
            path_template = rule[9:].strip()
            path = self._render_extraction_template(path_template, extra_context)
            if not path:
                return None
            try:
                data = json.loads(str(raw))
            except json.JSONDecodeError:
                return None
            return self._extract_scalar(self._extract_json_path_value(data, path))
        if rule.startswith("regex:"):
            pattern = rule[6:]
            match = re.search(pattern, str(raw))
            if not match:
                return False
            if match.groups():
                return self._extract_scalar(match.group(1))
            return True
        return self._extract_scalar(raw)

    def _fetch_from_mysql(
        self,
        metric_id: str,
        meta: Dict[str, Any],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        table_name = _safe_identifier(meta.get("table_name", ""))
        column_name = _safe_identifier(meta.get("column_name", ""))
        time_column = _safe_identifier(meta.get("time_column", "wafer_product_start_time"))
        equipment_column = _safe_identifier(meta.get("equipment_column", "equipment"))
        omit_equipment = bool(meta.get("mysql_omit_equipment_filter"))
        time_start, time_end = self.window_for_metric(meta)
        linking = self._normalize_linking(meta)
        resolved_context = extra_context or {}
        detail_trace.info(
            "  [取数:mysql] metric=%s table=%s column=%s mode=%s duration_days=%s extraction=%s filter=%s",
            metric_id,
            table_name,
            column_name,
            linking.get("mode"),
            self._duration_days_for_meta(meta),
            meta.get("extraction_rule"),
            detail_trace.preview(meta.get("filter_condition"), 240),
        )

        filter_sql, filter_params = self._render_mysql_filters(
            meta.get("filter_condition"),
            time_start,
            resolved_context,
        )
        linking_clauses, linking_params, missing_required = self._build_metric_filters(
            meta,
            time_start,
            include_exact_keys=True,
            include_linking_filters=True,
            placeholder_style="mysql",
            extra_context=resolved_context,
        )

        try:
            if linking["mode"] == "exact_keys":
                if missing_required:
                    detail_trace.warning(
                        "  [取数:mysql] metric=%s 缺少 exact_keys 必填上下文，返回 None",
                        metric_id,
                    )
                    self.source_log[metric_id] = "none"
                    return None
                raw_values = self._query_mysql_window(
                    table_name,
                    column_name,
                    time_column,
                    equipment_column,
                    time_start,
                    time_end,
                    filter_sql + self._join_sql_clauses(linking_clauses),
                    {**filter_params, **linking_params},
                    omit_equipment_filter=omit_equipment,
                )
            else:
                fallback_clauses, fallback_params, _ = self._build_metric_filters(
                    meta,
                    time_start,
                    include_exact_keys=False,
                    include_linking_filters=True,
                    placeholder_style="mysql",
                    extra_context=resolved_context,
                )
                raw_values = self._query_mysql_window(
                    table_name,
                    column_name,
                    time_column,
                    equipment_column,
                    time_start,
                    time_end,
                    filter_sql + self._join_sql_clauses(fallback_clauses),
                    {**filter_params, **fallback_params},
                    omit_equipment_filter=omit_equipment,
                )

            if not raw_values:
                detail_trace.warning("  [取数:mysql] metric=%s 原始结果为空", metric_id)
                self.source_log[metric_id] = "none"
                return None

            values = []
            for raw in raw_values:
                value = self._apply_extraction_rule(raw, meta.get("extraction_rule", ""), resolved_context)
                value = self._apply_data_type(metric_id, value, meta)
                if value is None or value is False:
                    continue
                values.append(value)
            if not values:
                detail_trace.warning(
                    "  [取数:mysql] metric=%s 原始结果=%s，但提取/类型转换后为空",
                    metric_id,
                    len(raw_values),
                )
                self.source_log[metric_id] = "none"
                return None
            self.source_log[metric_id] = "real_mysql"
            detail_trace.info(
                "  [取数:mysql] metric=%s 成功 | raw_count=%s | normalized_count=%s | sample=%s",
                metric_id,
                len(raw_values),
                len(values),
                detail_trace.preview(values[:3], 160),
            )
            return values
        except Exception as exc:
            logger.error("MySQL 查询失败: metric=%s table=%s error=%s", metric_id, table_name, exc)
            detail_trace.error(
                "  [取数:mysql] metric=%s 异常 | table=%s | error=%s | mode=%s",
                metric_id,
                table_name,
                detail_trace.preview(exc, 260),
                METRIC_SOURCE_MODE,
            )
            if METRIC_SOURCE_MODE in ("real", "mock_forbidden"):
                self.source_log[metric_id] = "none"
                return None
            value = self._mock_value(metric_id, meta)
            self.source_log[metric_id] = "mock"
            detail_trace.warning(
                "  [取数:mysql] metric=%s 使用 mock 回退 | mock_value=%s",
                metric_id,
                detail_trace.preview(value, 160),
            )
            return [value] if value is not None else []

    def _fetch_from_clickhouse(
        self,
        metric_id: str,
        meta: Dict[str, Any],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        time_start, time_end = self.window_for_metric(meta)
        linking = self._normalize_linking(meta)
        resolved_context = extra_context or {}
        detail_trace.info(
            "  [取数:clickhouse] metric=%s table=%s column=%s mode=%s duration_days=%s extraction=%s",
            metric_id,
            meta.get("table_name"),
            meta.get("column_name"),
            linking.get("mode"),
            self._duration_days_for_meta(meta),
            meta.get("extraction_rule"),
        )
        try:
            from app.ods.clickhouse_ods import ClickHouseODS

            exact_filters, exact_filter_params, missing_required = self._build_metric_filters(
                meta,
                time_start,
                include_exact_keys=True,
                include_linking_filters=True,
                placeholder_style="clickhouse",
                extra_context=resolved_context,
            )

            if linking["mode"] == "exact_keys":
                if missing_required:
                    detail_trace.warning(
                        "  [取数:clickhouse] metric=%s 缺少 exact_keys 必填上下文，返回 None",
                        metric_id,
                    )
                    self.source_log[metric_id] = "none"
                    return None
                values = ClickHouseODS.query_metric_in_window(
                    table_name=meta["table_name"],
                    column_name=meta["column_name"],
                    equipment=self.equipment,
                    time_start=time_start,
                    time_end=time_end,
                    reference_time=self.reference_time,
                    extraction_rule=meta.get("extraction_rule"),
                    time_column=meta.get("time_column", "time"),
                    equipment_column=meta.get("equipment_column", "equipment"),
                    extra_filters=exact_filters,
                    extra_filter_params=exact_filter_params,
                )
            else:
                fallback_filters, fallback_filter_params, _ = self._build_metric_filters(
                    meta,
                    time_start,
                    include_exact_keys=False,
                    include_linking_filters=True,
                    placeholder_style="clickhouse",
                    extra_context=resolved_context,
                )
                values = ClickHouseODS.query_metric_in_window(
                    table_name=meta["table_name"],
                    column_name=meta["column_name"],
                    equipment=self.equipment,
                    time_start=time_start,
                    time_end=time_end,
                    reference_time=self.reference_time,
                    extraction_rule=meta.get("extraction_rule"),
                    time_column=meta.get("time_column", "time"),
                    equipment_column=meta.get("equipment_column", "equipment"),
                    extra_filters=fallback_filters,
                    extra_filter_params=fallback_filter_params,
                )

            normalized = []
            for value in values:
                value = self._apply_data_type(metric_id, value, meta)
                if value is None or value is False:
                    continue
                normalized.append(value)
            self.source_log[metric_id] = "real_clickhouse" if normalized else "none"
            detail_trace.info(
                "  [取数:clickhouse] metric=%s 完成 | raw_count=%s | normalized_count=%s | source=%s | sample=%s",
                metric_id,
                len(values or []),
                len(normalized),
                self.source_log[metric_id],
                detail_trace.preview(normalized[:3], 160),
            )
            return normalized or None
        except Exception as exc:
            if METRIC_SOURCE_MODE in ("real", "mock_forbidden"):
                logger.error("ClickHouse 查询失败: metric=%s error=%s", metric_id, exc)
                detail_trace.error(
                    "  [取数:clickhouse] metric=%s 异常且禁止 mock | error=%s",
                    metric_id,
                    detail_trace.preview(exc, 260),
                )
                self.source_log[metric_id] = "none"
                return None
            value = self._mock_value(metric_id, meta)
            self.source_log[metric_id] = "mock"
            detail_trace.warning(
                "  [取数:clickhouse] metric=%s 异常后使用 mock | error=%s | mock_value=%s",
                metric_id,
                detail_trace.preview(exc, 220),
                detail_trace.preview(value, 160),
            )
            return [value] if value is not None else []

    def _mock_value(self, metric_id: str, meta: Dict[str, Any]) -> Any:
        """
        统一的 mock 取值入口,替代 stage4 期前的硬编码 legacy_ranges 和
        _mock_intermediate_value 字典。

        优先级:
          1. meta.mock_value      → 固定常量(适合中间量、布尔触发指标)
          2. meta.mock_range      → 闭区间随机(适合数值型 metric,如 [0.99985, 1.00015])
          3. fallback             → [-10, 10] 通用随机(避免任何 metric 没 mock 时崩溃)

        post-stage4 Bug #5 fix:加新指标只需在 reject_errors.diagnosis.json 里给
        该 metric 配 mock_value 或 mock_range,**无需改 Python**。
        """
        if "mock_value" in meta:
            return meta["mock_value"]
        if isinstance(meta.get("mock_range"), list) and len(meta["mock_range"]) == 2:
            low, high = meta["mock_range"]
            return round(random.uniform(float(low), float(high)), 6)
        return round(random.uniform(-10.0, 10.0), 4)
