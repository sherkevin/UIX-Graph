"""
MetricFetcher 时间窗与窗口列表行为测试。
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
    monkeypatch.setattr(f, "_fetch_one", lambda metric_id: [1.0, 2.0] if metric_id == "Mwx_0" else None)

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
