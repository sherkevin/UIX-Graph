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
    metric = pipeline["metrics"]["Coarse Alignment Failed"]
    assert metric["source_kind"] == "failure_record_field"
    assert metric["role"] == "trigger_only"
    assert metric["transform"]["type"] == "equals"
    assert pipeline["diagnosis_scenes"][0]["metric_id"] == ["Coarse Alignment Failed"]


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
    assert "D_x" in pipeline["metrics"]
    assert pipeline["metrics"]["D_x"]["source_kind"] == "intermediate"
    assert "动态上片偏差" in pipeline["metrics"]
    assert pipeline["metrics"]["Tx"]["notes"]
    assert pipeline["metrics"]["Tx"]["linking"]["mode"] == "time_window_only"
    assert pipeline["metrics"]["Tx"]["fallback"]["policy"] == "none"
    assert pipeline["metrics"]["Mwx_0"]["fallback"]["policy"] == "nearest_in_window"


def test_rule_loader_reload_works():
    loader = RuleLoader()
    loader.reload()
    assert loader.get_step("continue_model") is not None


def test_store_versions_are_valid():
    store = DiagnosisConfigStore()
    assert str(store.version).startswith("3.")
    pipeline = store.get_pipeline("reject_errors")
    assert str(pipeline["version"]).startswith("3.")
