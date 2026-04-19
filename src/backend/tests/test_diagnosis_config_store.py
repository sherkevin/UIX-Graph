"""
统一诊断配置存储测试。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.diagnosis.config_store import DiagnosisConfigStore
from app.engine.rule_loader import RuleLoader


def test_store_loads_reject_errors_pipeline_from_structured_file():
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    assert pipeline["id"] == "reject_errors"
    metric = pipeline["metrics"]["trigger_reject_reason_cowa_6"]
    assert metric["source_kind"] == "failure_record_field"
    assert metric["role"] == "trigger_only"
    assert metric["transform"]["type"] == "equals"
    assert pipeline["diagnosis_scenes"][0]["metric_id"] == [
        "trigger_reject_reason_cowa_6",
        "trigger_log_mwx_cgg6_range",
    ]


def test_store_loads_structured_ontology_pipeline():
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("ontology_api")
    assert pipeline["default_scene_id"] == "ontology-default"
    assert "rotation_mean" in pipeline["metrics"]
    assert pipeline["metrics"]["rotation_mean"]["source_kind"] == "request_param"
    assert pipeline["steps_map"]["1"]["next"][0]["condition"]["any_of"]


def test_store_backfills_rule_metrics_and_meta_notes():
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    # D_x / D_y 保留作为 stage4 计划接入的 intermediate 占位(带 _status / _planned_source 标注)
    assert "D_x" in pipeline["metrics"]
    assert pipeline["metrics"]["D_x"]["source_kind"] == "intermediate"
    assert pipeline["metrics"]["D_x"].get("_status") == "stage4-planned"
    # \u300a动态上片偏差\u300b orphan 中文 id 已删除(L2 清理)
    assert "\u52a8\u6001\u4e0a\u7247\u504f\u5dee" not in pipeline["metrics"]
    assert "notes" not in pipeline["metrics"]["Tx"]
    assert pipeline["metrics"]["Tx"]["linking"]["mode"] == "time_window_only"
    assert pipeline["metrics"]["Tx"]["fallback"]["policy"] == "none"
    assert pipeline["metrics"]["Mwx_0"]["fallback"]["policy"] == "nearest_in_window"


def test_store_applies_safe_cowa_source_updates():
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    ws_pos_x = pipeline["metrics"]["ws_pos_x"]
    ws_pos_y = pipeline["metrics"]["ws_pos_y"]
    sx = pipeline["metrics"]["Sx"]
    sy = pipeline["metrics"]["Sy"]

    assert ws_pos_x["table_name"] == "src.RPT_WAA_SET_UNION_VIEW"
    assert ws_pos_y["table_name"] == "src.RPT_WAA_SET_UNION_VIEW"
    assert {"target": "phase", "value": "1ST_COWA"} in ws_pos_x["linking"]["filters"]
    assert {"target": "phase", "value": "1ST_COWA"} in ws_pos_y["linking"]["filters"]

    assert {"target": "table_name", "value": "COMC"} in sx["linking"]["filters"]
    assert {"target": "table_name", "value": "COMC"} in sy["linking"]["filters"]
    assert {"target": "env_id", "operator": "contains", "source": "equipment"} in sx["linking"]["filters"]
    assert {"target": "env_id", "operator": "contains", "source": "equipment"} in sy["linking"]["filters"]
    assert sx["extraction_rule"] == "jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x"
    assert sy["extraction_rule"] == "jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/y"


def test_rule_loader_reload_works():
    loader = RuleLoader()
    loader.reload()
    assert loader.get_step("continue_model") is not None


def test_store_versions_are_valid():
    store = DiagnosisConfigStore()
    assert str(store.version).startswith("3.")
    pipeline = store.get_pipeline("reject_errors")
    assert str(pipeline["version"]).startswith("3.")
