"""
metric 元数据严格校验测试(无需数据库)

覆盖目标:
- 配置驱动 fail-fast:任何专家可能写错的字段,都在启动时校验出来
- 不误伤现有合法配置(由 test_rules_validator.py::test_current_rules_config_is_valid 守护)
- 历史别名兼容(mysql / clickhouse 等)
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.rule_validator import (
    validate_metrics_metadata,
    validate_rules_config,
    VALID_SOURCE_KINDS,
    VALID_ROLES,
    VALID_LINKING_MODES,
    VALID_LINKING_OPERATORS,
    VALID_FALLBACK_POLICIES,
    VALID_TRANSFORM_TYPES,
)


def _no_action(_name: str) -> bool:
    return False


# ── 1. 合法配置不误报 ─────────────────────────────────────────────


def test_empty_or_none_metrics_passes():
    assert validate_metrics_metadata(None) == []
    assert validate_metrics_metadata({}) == []


def test_minimal_intermediate_metric_passes():
    metrics = {"D_x": {"description": "中间量", "source_kind": "intermediate"}}
    assert validate_metrics_metadata(metrics) == []


def test_failure_record_field_metric_passes():
    metrics = {
        "Tx": {
            "source_kind": "failure_record_field",
            "field": "wafer_translation_x",
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_request_param_metric_passes():
    metrics = {
        "input_a": {
            "source_kind": "request_param",
            "field": "a",
            "role": "diagnostic",
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_mysql_window_metric_passes():
    metrics = {
        "Tx_history": {
            "source_kind": "mysql_nearest_row",
            "table_name": "datacenter.lo_batch_equipment_performance",
            "column_name": "wafer_translation_x",
            "linking": {
                "mode": "exact_keys",
                "keys": [{"target": "chuck_id", "source": "chuck_id"}],
                "filters": [],
            },
            "fallback": {"policy": "nearest_in_window"},
            "duration": "30",
            "role": "internal",
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_clickhouse_window_with_regex_passes():
    metrics = {
        "Mwx_0": {
            "source_kind": "clickhouse_window",
            "table_name": "las.LOG_EH_UNION_VIEW",
            "column_name": "detail",
            "extraction_rule": r"regex:Mwx\s*\(\s*([\d\.]+)\s*\)",
            "linking": {"mode": "time_window_only", "keys": [], "filters": []},
            "duration": "7",
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_legacy_mysql_clickhouse_aliases_pass():
    """historical aliases 'mysql' and 'clickhouse' must be accepted."""
    metrics = {
        "X1": {
            "source_kind": "mysql",
            "table_name": "t.x",
            "column_name": "v",
        },
        "X2": {
            "source_kind": "clickhouse",
            "table_name": "t.y",
            "column_name": "w",
        },
    }
    assert validate_metrics_metadata(metrics) == []


def test_transform_equals_passes():
    metrics = {
        "trigger": {
            "source_kind": "failure_record_field",
            "field": "reject_reason",
            "transform": {"type": "equals", "value": 6},
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_linking_contains_operator_passes():
    metrics = {
        "X": {
            "source_kind": "mysql_nearest_row",
            "table_name": "t.x",
            "column_name": "v",
            "linking": {
                "mode": "time_window_only",
                "keys": [],
                "filters": [
                    {"target": "env_id", "operator": "contains", "source": "equipment"},
                    {"target": "table_name", "value": "COMC"},
                ],
            },
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_jsonpath_extraction_passes():
    metrics = {
        "Sx": {
            "source_kind": "mysql_nearest_row",
            "table_name": "datacenter.mc_config_commits_history",
            "column_name": "data",
            "extraction_rule": "jsonpath:foo/bar/x",
        }
    }
    assert validate_metrics_metadata(metrics) == []


def test_data_type_int_passes():
    metrics = {
        "n_88um": {
            "data_type": "int",
            "source_kind": "intermediate",
        }
    }
    assert validate_metrics_metadata(metrics) == []


# ── 2. 非法配置必须报错 ─────────────────────────────────────────


def test_unknown_source_kind_rejected():
    errs = validate_metrics_metadata({"X": {"source_kind": "redis_lookup"}})
    assert any("source_kind" in e and "redis_lookup" in e for e in errs)


def test_unknown_role_rejected():
    errs = validate_metrics_metadata(
        {"X": {"source_kind": "intermediate", "role": "important"}}
    )
    assert any("role" in e and "important" in e for e in errs)


def test_db_kind_missing_table_name_rejected():
    errs = validate_metrics_metadata(
        {"X": {"source_kind": "mysql_nearest_row", "column_name": "v"}}
    )
    assert any("table_name" in e for e in errs)


def test_db_kind_missing_column_name_rejected():
    errs = validate_metrics_metadata(
        {"X": {"source_kind": "clickhouse_window", "table_name": "t.x"}}
    )
    assert any("column_name" in e for e in errs)


def test_failure_record_field_missing_field_rejected():
    errs = validate_metrics_metadata({"X": {"source_kind": "failure_record_field"}})
    assert any("field" in e for e in errs)


def test_request_param_missing_field_rejected():
    errs = validate_metrics_metadata({"X": {"source_kind": "request_param"}})
    assert any("field" in e for e in errs)


def test_unknown_transform_type_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "failure_record_field",
                "field": "f",
                "transform": {"type": "wrap_in_list"},
            }
        }
    )
    assert any("transform.type" in e for e in errs)


def test_transform_map_missing_mapping_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "failure_record_field",
                "field": "f",
                "transform": {"type": "map"},
            }
        }
    )
    assert any("mapping" in e for e in errs)


def test_unknown_linking_mode_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "mysql_nearest_row",
                "table_name": "t.x",
                "column_name": "v",
                "linking": {"mode": "fuzzy_match"},
            }
        }
    )
    assert any("linking.mode" in e and "fuzzy_match" in e for e in errs)


def test_unknown_linking_operator_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "mysql_nearest_row",
                "table_name": "t.x",
                "column_name": "v",
                "linking": {
                    "mode": "exact_keys",
                    "keys": [{"target": "chuck_id", "source": "chuck_id", "operator": "between"}],
                    "filters": [],
                },
            }
        }
    )
    assert any("operator" in e and "between" in e for e in errs)


def test_linking_key_missing_target_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "mysql_nearest_row",
                "table_name": "t.x",
                "column_name": "v",
                "linking": {
                    "mode": "exact_keys",
                    "keys": [{"source": "chuck_id"}],
                    "filters": [],
                },
            }
        }
    )
    assert any("target" in e for e in errs)


def test_linking_key_missing_both_source_and_value_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "mysql_nearest_row",
                "table_name": "t.x",
                "column_name": "v",
                "linking": {
                    "mode": "exact_keys",
                    "keys": [{"target": "chuck_id"}],  # 既无 source 也无 value
                    "filters": [],
                },
            }
        }
    )
    assert any("source" in e and "value" in e for e in errs)


def test_unknown_fallback_policy_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "clickhouse_window",
                "table_name": "t.x",
                "column_name": "v",
                "fallback": {"policy": "snapshot_24h"},
            }
        }
    )
    assert any("fallback.policy" in e and "snapshot_24h" in e for e in errs)


def test_unknown_extraction_prefix_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "clickhouse_window",
                "table_name": "t.x",
                "column_name": "v",
                "extraction_rule": "xpath:/foo/bar",
            }
        }
    )
    assert any("extraction_rule" in e and "xpath:" in e for e in errs)


def test_invalid_duration_rejected():
    errs = validate_metrics_metadata(
        {
            "X": {
                "source_kind": "mysql_nearest_row",
                "table_name": "t.x",
                "column_name": "v",
                "duration": "thirty days",
            }
        }
    )
    assert any("duration" in e for e in errs)


def test_unknown_data_type_rejected():
    errs = validate_metrics_metadata(
        {"X": {"source_kind": "intermediate", "data_type": "tensor"}}
    )
    assert any("data_type" in e and "tensor" in e for e in errs)


def test_metric_meta_must_be_dict():
    errs = validate_metrics_metadata({"X": "not a dict"})
    assert any("元数据必须是对象" in e for e in errs)


# ── 3. 与 validate_rules_config 集成:metric 错误也会被 report ──


def test_validate_rules_config_includes_metric_errors():
    rules = {
        "diagnosis_scenes": [{"id": 1, "start_node": "10"}],
        "steps": [{"id": 10, "next": []}],
    }
    bad_metrics = {"X": {"source_kind": "fictional_db"}}
    errs = validate_rules_config(rules, action_exists=_no_action, metrics=bad_metrics)
    assert any("source_kind" in e and "fictional_db" in e for e in errs)


# ── 4. 公开常量稳定性(配置文档与代码同源) ──


def test_public_enum_sets_are_non_empty():
    """合法值集合不能因为某次重构变空——CONFIG_GUIDE 里的枚举都依赖这些常量。"""
    assert len(VALID_SOURCE_KINDS) >= 5
    assert len(VALID_ROLES) >= 3
    assert len(VALID_LINKING_MODES) >= 2
    assert len(VALID_LINKING_OPERATORS) >= 7
    assert len(VALID_FALLBACK_POLICIES) >= 2
    assert len(VALID_TRANSFORM_TYPES) >= 5


# ── post-stage4 Bug #3 fix: alias_of 字段校验 ─────────────────────────


def test_alias_of_passes_when_target_exists():
    metrics = {
        "Tx": {"source_kind": "failure_record_field", "field": "wafer_translation_x"},
        "output_Tx": {
            "source_kind": "intermediate",
            "alias_of": "Tx",
            "approximate": True,
        },
    }
    assert validate_metrics_metadata(metrics) == []


def test_alias_of_rejected_when_target_missing():
    metrics = {
        "output_Tx": {"source_kind": "intermediate", "alias_of": "non_existent_metric"},
    }
    errs = validate_metrics_metadata(metrics)
    assert any("alias_of" in e and "non_existent_metric" in e for e in errs)


def test_alias_of_rejected_when_self_referencing():
    metrics = {"X": {"source_kind": "intermediate", "alias_of": "X"}}
    errs = validate_metrics_metadata(metrics)
    assert any("alias_of" in e for e in errs)


def test_alias_of_rejected_when_not_string():
    metrics = {"X": {"source_kind": "intermediate", "alias_of": 123}}
    errs = validate_metrics_metadata(metrics)
    assert any("alias_of" in e for e in errs)


def test_alias_of_rejected_when_circular():
    metrics = {
        "A": {"source_kind": "intermediate", "alias_of": "B"},
        "B": {"source_kind": "intermediate", "alias_of": "A"},
    }
    errs = validate_metrics_metadata(metrics)
    assert any("\u5faa\u73af" in e for e in errs)


# ── post-stage4 Bug #5 fix: mock_value / mock_range 校验 ─────────────


def test_mock_range_valid_passes():
    metrics = {
        "X": {"source_kind": "intermediate", "mock_range": [-1.0, 1.0]},
        "Y": {"source_kind": "intermediate", "mock_range": [0, 100]},
    }
    assert validate_metrics_metadata(metrics) == []


def test_mock_value_any_type_passes():
    """mock_value 不限制类型(任何 JSON 字面量都允许)。"""
    metrics = {
        "Bool": {"source_kind": "clickhouse_window", "table_name": "t.x", "column_name": "v", "mock_value": True},
        "Int": {"source_kind": "intermediate", "mock_value": 42},
        "Str": {"source_kind": "intermediate", "mock_value": "fixed_str"},
        "Null": {"source_kind": "intermediate", "mock_value": None},
    }
    assert validate_metrics_metadata(metrics) == []


def test_mock_range_rejected_when_not_list_of_two():
    metrics = {"X": {"source_kind": "intermediate", "mock_range": [1.0]}}
    errs = validate_metrics_metadata(metrics)
    assert any("mock_range" in e and "\u957f\u5ea6\u4e3a 2" in e for e in errs)


def test_mock_range_rejected_when_low_greater_than_high():
    metrics = {"X": {"source_kind": "intermediate", "mock_range": [10, 1]}}
    errs = validate_metrics_metadata(metrics)
    assert any("mock_range" in e and ">" in e for e in errs)


def test_mock_range_rejected_when_elements_not_numeric():
    metrics = {"X": {"source_kind": "intermediate", "mock_range": ["a", "b"]}}
    errs = validate_metrics_metadata(metrics)
    assert any("mock_range" in e and "\u6570\u5b57" in e for e in errs)
