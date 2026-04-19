"""
MetricFetcher 鏃堕棿绐椾笌绐楀彛鍒楄〃琛屼负娴嬭瘯銆?
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from types import SimpleNamespace

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions.builtin import calculate_monthly_mean_Tx, select_window_metric
from app.engine.metric_fetcher import MetricFetcher


def test_window_uses_duration_days_from_meta():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_days=7,
    )
    start, end = f.window_for_metric({"duration": "30"})
    assert end == T
    assert start == T - timedelta(days=30)


def test_window_fallback_when_no_duration_uses_days():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_days=7,
    )
    start, end = f.window_for_metric({})
    assert end == T
    assert start == T - timedelta(days=7)


def test_mysql_filter_condition_supports_parentheses_and_or():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        chuck_id=12,
        fallback_duration_days=7,
    )
    sql, params = f._render_mysql_filters(
        "(chuck_id={chuck_id} AND lot_start_time >= {time_filter}) OR wafer_index = 5",
        T - timedelta(days=1),
        {},
    )
    assert " OR " in sql
    assert " AND " in sql
    assert "filter_0" in params
    assert "filter_1" in params
    assert "filter_2" in params


def test_extract_direct_metric_applies_transform_and_data_type(monkeypatch):
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_days=7,
    )

    def _fake_meta(metric_id):
        if metric_id == "X":
            return {
                "source_kind": "failure_record_field",
                "field": "raw_x",
                "transform": {"type": "int"},
                "data_type": "float",
            }
        return None

    monkeypatch.setattr(f.rule_loader, "get_metric_meta", _fake_meta)
    handled, value = f._extract_direct_metric("X", {"raw_x": "12.7"})
    assert handled is True
    assert isinstance(value, float)
    assert value == 12.0


def test_apply_data_type_ignores_none_without_warning():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_days=7,
    )
    assert f._apply_data_type("X", "raw-text", {"data_type": None}) == "raw-text"


def test_regex_patterns_accept_mwx_and_max():
    import re
    assert re.search(r"M[wa]x out of range,C?GG6_check_parameter_ranges", "Mwx out of range,CGG6_check_parameter_ranges")
    assert re.search(r"M[wa]x out of range,C?GG6_check_parameter_ranges", "Max out of range,CGG6_check_parameter_ranges")
    assert re.search(r"M[wa]x out of range,C?GG6_check_parameter_ranges", "Mwx out of range,GG6_check_parameter_ranges")
    assert re.search(r"M[wa]x out of range,C?GG6_check_parameter_ranges", "Max out of range,GG6_check_parameter_ranges")
    assert re.search(r"M[wa]x\s*\(\s*([\d\.]+)\s*\)", "Mwx ( 1.00003 )")
    assert re.search(r"M[wa]x\s*\(\s*([\d\.]+)\s*\)", "Max ( 1.00003 )")


def test_resolve_filter_value_reads_source_record_context():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        chuck_id=12,
        fallback_duration_days=7,
        source_record={"lot_id": "LOT-1", "wafer_index": "W03"},
    )
    assert f._resolve_filter_value("{lot_id}", T, {}) == "LOT-1"
    assert f._resolve_filter_value("{wafer_index}", T, {}) == "W03"


def test_build_metric_filters_uses_exact_keys_from_source_record():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        chuck_id=12,
        fallback_duration_days=7,
        source_record={"lot_id": "LOT-1", "wafer_index": "W03"},
    )
    clauses, params, missing = f._build_metric_filters(
        {
            "linking": {
                "mode": "exact_keys",
                "keys": [
                    {"target": "lot_id", "source": "lot_id"},
                    {"target": "wafer_index", "source": "wafer_index"},
                ],
                "filters": [{"target": "stage", "value": "ALIGN"}],
            }
        },
        T,
        include_exact_keys=True,
        include_linking_filters=True,
        placeholder_style="mysql",
    )
    assert missing is False
    assert "lot_id = :link_0" in clauses
    assert "wafer_index = :link_1" in clauses
    assert "stage = :link_2" in clauses
    assert params["link_0"] == "LOT-1"
    assert params["link_1"] == "W03"
    assert params["link_2"] == "ALIGN"


def test_build_metric_filters_supports_contains_in_and_context_sources():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        chuck_id=2,
        fallback_duration_days=7,
        source_record={"lot_id": "LOT-1"},
    )
    clauses, params, missing = f._build_metric_filters(
        {
            "linking": {
                "mode": "time_window_only",
                "keys": [],
                "filters": [
                    {"target": "env_id", "operator": "contains", "source": "equipment"},
                    {"target": "mark_id", "operator": "in", "source": "mark_candidates"},
                    {"target": "table_name", "source": "config_table"},
                ],
            }
        },
        T,
        include_exact_keys=False,
        include_linking_filters=True,
        placeholder_style="mysql",
        extra_context={
            "mark_candidates": ["M1", "M2", "M3", "M4"],
            "config_table": "COMC",
        },
    )
    assert missing is False
    assert "INSTR(CAST(env_id AS CHAR), CAST(:link_0 AS CHAR)) > 0" in clauses
    assert "mark_id IN (:link_1_0, :link_1_1, :link_1_2, :link_1_3)" in clauses
    assert "table_name = :link_2" in clauses
    assert params["link_0"] == "SSB8000"
    assert params["link_1_0"] == "M1"
    assert params["link_1_3"] == "M4"
    assert params["link_2"] == "COMC"


def test_mysql_exact_match_returns_none_without_explicit_fallback(monkeypatch):
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_days=7,
        source_record={"lot_id": "LOT-1"},
    )

    monkeypatch.setattr(f, "_query_mysql_window", lambda *args, **kwargs: [])
    value = f._fetch_from_mysql(
        "Sx",
        {
            "table_name": "datacenter.mc_config_commits_history",
            "column_name": "data",
            "time_column": "committed_at",
            "equipment_column": "equipment",
            "extraction_rule": "json:Sx",
            "linking": {
                "mode": "exact_keys",
                "keys": [{"target": "lot_id", "source": "lot_id"}],
                "filters": [],
            },
            "fallback": {"policy": "none"},
        },
    )
    assert value is None
    assert f.source_log["Sx"] == "none"


def test_apply_extraction_rule_supports_jsonpath_with_context():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        chuck_id=2,
        fallback_duration_days=7,
    )
    raw = """
    {
      "static_wafer_load_offset": {
        "chuck_message": [
          {"static_load_offset": {"x": 1.23, "y": 4.56}},
          {"static_load_offset": {"x": 7.89, "y": 0.12}}
        ]
      }
    }
    """
    value_x = f._apply_extraction_rule(
        raw,
        "jsonpath:static_wafer_load_offset/chuck_message/{chuck_index0}/static_load_offset/x",
        {"chuck_index0": 1},
    )
    value_y = f._apply_extraction_rule(
        raw,
        "jsonpath:static_wafer_load_offset/chuck_message/{chuck_index0}/static_load_offset/y",
        {"chuck_index0": 1},
    )
    assert value_x == 7.89
    assert value_y == 0.12


def test_fetch_all_passes_previous_metric_results_as_context(monkeypatch):
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(equipment="SSB8000", reference_time=T, fallback_duration_days=7)

    monkeypatch.setattr(
        f.rule_loader,
        "get_metric_meta",
        lambda metric_id: {"source_kind": "mysql_nearest_row"},
    )

    seen_context = {}

    def _fake_fetch(metric_id, extra_context=None):
        seen_context[metric_id] = dict(extra_context or {})
        if metric_id == "mark_candidates":
            return ["M1", "M2", "M3", "M4"]
        return ["final"]

    monkeypatch.setattr(f, "_fetch_one", _fake_fetch)
    values = f.fetch_all(["mark_candidates", "mark_pos_x"])
    assert values["mark_candidates"] == ["M1", "M2", "M3", "M4"]
    assert values["mark_candidates_window"] == ["M1", "M2", "M3", "M4"]
    assert seen_context["mark_pos_x"]["mark_candidates"] == ["M1", "M2", "M3", "M4"]
    assert seen_context["mark_pos_x"]["mark_candidates_window"] == ["M1", "M2", "M3", "M4"]


def test_mysql_window_omits_equipment_predicate_when_configured(monkeypatch):
    captured: dict = {}

    class FakeResult:
        def fetchall(self):
            return []

    class FakeDb:
        def execute(self, sql, params):
            captured["sql"] = str(sql)
            captured["params"] = dict(params)
            return FakeResult()

        def close(self):
            return None

    monkeypatch.setattr("app.ods.datacenter_ods.SessionLocal", lambda: FakeDb())

    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(equipment="SSB8000", reference_time=T, fallback_duration_days=7)
    f._query_mysql_window(
        "datacenter.mc_config_commits_history",
        "data",
        "last_modify_date",
        "equipment",
        T - timedelta(hours=1),
        T,
        "",
        {},
        omit_equipment_filter=True,
    )
    assert ":equipment" not in captured["sql"]
    assert "equipment" not in captured["params"]
    assert "last_modify_date >=" in captured["sql"]


def test_clickhouse_query_accepts_extra_filters(monkeypatch):
    import app.ods.clickhouse_ods as clickhouse_ods
    T = datetime(2026, 3, 25, 12, 0, 0)

    captured = {}

    class FakeClient:
        def query(self, query, parameters=None):
            captured["query"] = query
            captured["parameters"] = parameters or {}
            return SimpleNamespace(result_set=[["1.02"], ["1.03"]])

        def close(self):
            return None

    monkeypatch.setattr(clickhouse_ods, "get_clickhouse_client", lambda: FakeClient())
    value = clickhouse_ods.ClickHouseODS.query_metric_in_window(
        table_name="db.tbl",
        column_name="metric_col",
        equipment="EQ-1",
        time_start=T,
        time_end=T,
        reference_time=T,
        extra_filters=["lot_id = %(link_0)s", "wafer_index = %(link_1)s"],
        extra_filter_params={"link_0": "LOT-1", "link_1": "W03"},
    )
    assert value == [1.02, 1.03]
    assert "`db`.`tbl`" in captured["query"]
    assert "`metric_col`" in captured["query"]
    assert "parseDateTimeBestEffortOrNull(toString(`time`))" in captured["query"]
    assert "lot_id = %(link_0)s" in captured["query"]
    assert "wafer_index = %(link_1)s" in captured["query"]
    assert "LIMIT 1" not in captured["query"]
    assert captured["parameters"]["link_0"] == "LOT-1"
    assert captured["parameters"]["link_1"] == "W03"


def test_fetch_all_adds_window_alias_for_query_metrics(monkeypatch):
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(equipment="SSB8000", reference_time=T, fallback_duration_days=7)

    monkeypatch.setattr(
        f.rule_loader,
        "get_metric_meta",
        lambda metric_id: {"source_kind": "clickhouse_window"} if metric_id == "Mwx_0" else None,
    )
    monkeypatch.setattr(
        f,
        "_fetch_one",
        lambda metric_id, extra_context=None: [1.0, 2.0] if metric_id == "Mwx_0" else None,
    )

    values = f.fetch_all(["Mwx_0"])
    assert values["Mwx_0"] == [1.0, 2.0]
    assert values["Mwx_0_window"] == [1.0, 2.0]


def test_select_window_metric_picks_first_value():
    assert select_window_metric(metric_name="Mwx_0", values=[1.00003, 1.00006]) == {"Mwx_0": 1.00003}


def test_monthly_mean_action_uses_list_input():
    result = calculate_monthly_mean_Tx(Tx=[1.0, 2.0, 3.0])
    assert result == {"mean_Tx": 2.0}


if __name__ == "__main__":
    test_window_uses_duration_days_from_meta()
    test_window_fallback_when_no_duration_uses_days()
    print("OK: test_metric_fetcher_window")

# ── post-stage4 Bug #1 fix: jsonpath name[N] segment 支持 ─────────────────


def test_extract_json_path_value_supports_name_bracket_index():
    """jsonpath segment 形如 'chuck_message[0]' 应当被识别为 dict.chuck_message → list[0]。

    这是 reject_errors.diagnosis.json Sx/Sy 的实际写法,
    extraction_rule = jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x
    """
    data = {
        "static_wafer_load_offset": {
            "chuck_message": [
                {"static_load_offset": {"x": 1.234, "y": -5.678}},
                {"static_load_offset": {"x": 2.0, "y": -3.0}},
            ]
        }
    }
    assert MetricFetcher._extract_json_path_value(
        data, "static_wafer_load_offset/chuck_message[0]/static_load_offset/x"
    ) == 1.234
    assert MetricFetcher._extract_json_path_value(
        data, "static_wafer_load_offset/chuck_message[1]/static_load_offset/y"
    ) == -3.0


def test_extract_json_path_value_name_bracket_index_out_of_range_returns_none():
    data = {"chuck_message": [{"x": 1}]}
    assert MetricFetcher._extract_json_path_value(data, "chuck_message[5]/x") is None
    assert MetricFetcher._extract_json_path_value(data, "chuck_message[10]") is None


def test_extract_json_path_value_name_bracket_with_non_list_value_returns_none():
    """如果 dict.name 不是 list,name[N] 形式应返回 None(类型不匹配)。"""
    data = {"chuck_message": "not a list"}
    assert MetricFetcher._extract_json_path_value(data, "chuck_message[0]") is None


def test_extract_json_path_value_old_slash_index_still_works():
    """向后兼容:'chuck_message/0/x' 写法(纯 / 分段)与 'chuck_message[0]/x' 等价。"""
    data = {"chuck_message": [{"x": 42}, {"x": 100}]}
    assert MetricFetcher._extract_json_path_value(data, "chuck_message/0/x") == 42
    assert MetricFetcher._extract_json_path_value(data, "chuck_message/1/x") == 100


def test_extract_json_path_value_dict_key_lookup_unaffected():
    """普通 dict key 访问仍然正常,bug fix 不应影响这条路径。"""
    data = {"static_wafer_load_offset": {"chuck_message": {"first": {"x": 1.0}}}}
    assert MetricFetcher._extract_json_path_value(
        data, "static_wafer_load_offset/chuck_message/first/x"
    ) == 1.0


def test_extract_json_path_value_name_bracket_root_data_must_be_dict():
    """如果当前 current 是 list,name[N] 形式应返回 None(name 不存在于 list)。"""
    data = [{"x": 1}, {"x": 2}]
    # 第一段 'name[0]' 期待 current 是 dict,实际是 list,返回 None
    assert MetricFetcher._extract_json_path_value(data, "name[0]") is None


# ── post-stage4 Bug #7 fix: _render_extraction_template list 变量边界 ─────


def _make_fetcher_with_ctx(ctx: dict) -> MetricFetcher:
    """构造一个最小 MetricFetcher,把 ctx 透传到 _resolve_context_value。"""
    fetcher = MetricFetcher.__new__(MetricFetcher)
    fetcher.equipment = "X"
    fetcher.reference_time = datetime(2026, 1, 1)
    fetcher.chuck_id = 1
    fetcher.params = {}
    fetcher.source_record = {}

    # 注入 ctx 到 _resolve_context_value:用 monkeypatch-style 替换
    def _resolve(name, time_filter, extra):
        if name in extra:
            return extra[name]
        if name in ctx:
            return ctx[name]
        return None
    fetcher._resolve_context_value = _resolve  # type: ignore[assignment]
    return fetcher


def test_render_template_with_list_var_picks_first_non_null():
    """list 类型变量应取第一个非 None 元素,而不是 str([...]) 拼出错误模板。"""
    fetcher = _make_fetcher_with_ctx({"chuck_index0": [0, 1, 2]})
    rendered = fetcher._render_extraction_template(
        "static_wafer_load_offset/chuck_message[{chuck_index0}]/x"
    )
    assert rendered == "static_wafer_load_offset/chuck_message[0]/x"


def test_render_template_with_list_var_skips_leading_nones():
    """list 中前几个为 None 时应取第一个非 None。"""
    fetcher = _make_fetcher_with_ctx({"chuck_index0": [None, None, 5]})
    rendered = fetcher._render_extraction_template("foo/{chuck_index0}/bar")
    assert rendered == "foo/5/bar"


def test_render_template_with_all_none_list_returns_none():
    """list 全 None → 视为变量缺失,整体返回 None(让后续逻辑 fall through)。"""
    fetcher = _make_fetcher_with_ctx({"v": [None, None]})
    assert fetcher._render_extraction_template("foo/{v}/bar") is None


def test_render_template_scalar_var_unchanged():
    """标量变量行为不变(确保 fix 不破坏现有路径)。"""
    fetcher = _make_fetcher_with_ctx({"chuck_index0": 1})
    rendered = fetcher._render_extraction_template("foo/chuck_message[{chuck_index0}]/x")
    assert rendered == "foo/chuck_message[1]/x"
