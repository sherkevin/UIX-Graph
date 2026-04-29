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
    """对齐 stage4/prd.md §前置工作：ws_pos 走 V2_SET_OFL；mark_pos 两步查（mark_candidates + UNION_VIEW）。"""
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    ws_pos_x = pipeline["metrics"]["ws_pos_x"]
    ws_pos_y = pipeline["metrics"]["ws_pos_y"]
    sx = pipeline["metrics"]["Sx"]
    sy = pipeline["metrics"]["Sy"]
    mark_candidates = pipeline["metrics"].get("mark_candidates")
    mark_pos_x = pipeline["metrics"]["mark_pos_x"]
    mark_pos_y = pipeline["metrics"]["mark_pos_y"]

    assert ws_pos_x["table_name"] == "src.RPT_WAA_V2_SET_OFL"
    assert ws_pos_y["table_name"] == "src.RPT_WAA_V2_SET_OFL"
    # stage4 修复后 WS 段落不再强制 phase 过滤（PRD 未要求）
    assert ws_pos_x["linking"]["filters"] == []
    assert ws_pos_y["linking"]["filters"] == []

    assert mark_candidates is not None, "mark_candidates 中间 metric 必须存在（stage4 PRD §具体步骤 2）"
    assert mark_candidates["table_name"] == "las.RPT_WAA_RESULT_OFL"
    assert mark_candidates["column_name"] == "mark_id"
    assert {"target": "phase", "value": "1ST_COWA"} in mark_candidates["linking"]["filters"]

    assert mark_pos_x["table_name"] == "las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW"
    assert mark_pos_y["table_name"] == "las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW"
    assert {
        "target": "mark_id",
        "operator": "in",
        "source": "mark_candidates",
    } in mark_pos_x["linking"]["filters"]
    assert {
        "target": "mark_id",
        "operator": "in",
        "source": "mark_candidates",
    } in mark_pos_y["linking"]["filters"]

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


def test_rule_loader_scene_metric_ids_survives_null_next_step():
    """
    回归测试:get_all_scene_metric_ids 在遍历 BFS 时用的是 step.get("next", [])。
    若配置里写了 "next": null(与"缺 key"语义不同),返回的是 None 而非 []。
    过去会触发 `for branch in None` 的 TypeError 让诊断引擎启动失败。
    """
    loader = RuleLoader()
    # 使用一个临时 steps_map 注入 null next,不影响真实 pipeline
    original_map = loader.steps_map
    original_steps = loader.steps
    probe_step = {"id": "__probe_null_next__", "metric_id": "probe_mid", "next": None}
    injected_map = dict(original_map)
    injected_map["__probe_null_next__"] = probe_step
    loader.steps_map = injected_map
    loader.steps = list(original_steps) + [probe_step]
    try:
        result = loader.get_all_scene_metric_ids({
            "metric_id": ["probe_mid"],
            "start_node": "__probe_null_next__",
        })
        # 正常跑完且把 step.metric_id 收集进去即可
        assert "probe_mid" in result
    finally:
        loader.steps_map = original_map
        loader.steps = original_steps
