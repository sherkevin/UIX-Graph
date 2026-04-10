"""
诊断配置静态校验器测试（无需数据库）
"""
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
repo_root = project_root.parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions import has_action
from app.engine.rule_validator import validate_rules_config


def test_current_rules_config_is_valid():
    pipeline_path = repo_root / "config" / "reject_errors.diagnosis.json"
    data = json.loads(pipeline_path.read_text(encoding="utf-8"))
    errors = validate_rules_config(
        {
            "diagnosis_scenes": data.get("diagnosis_scenes", []),
            "steps": data.get("steps", []),
        },
        action_exists=has_action,
        metrics=data.get("metrics", {}),
    )
    assert errors == []


def test_validator_detects_missing_action_and_target():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [{"action": "not_exists_action"}],
                "next": [{"target": "2", "condition": "{x} == 1"}],
            }
        ],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("action 未注册" in e for e in errors)
    assert any("target 不存在" in e for e in errors)


def test_validator_detects_unparseable_condition():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [{"target": "1", "condition": "this is not a valid condition"}],
            }
        ],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("condition 无法解析" in e for e in errors)


def test_validator_rejects_deprecated_operator_limit_on_next():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [{"target": "1", "condition": "{x} > 1", "operator": ">", "limit": 1}],
            }
        ],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("已废弃 operator" in e for e in errors)
    assert any("已废弃 limit" in e for e in errors)


def test_validator_detects_invalid_trigger_condition():
    data = {
        "diagnosis_scenes": [{
            "id": 1,
            "metric_id": ["A", "B"],
            "trigger_condition": ["{A} == true AND ???"],
            "start_node": "1",
        }],
        "steps": [{"id": 1, "details": [], "next": []}],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("trigger_condition" in e and "无法解析" in e for e in errors)


def test_validator_detects_trigger_metric_not_declared():
    data = {
        "diagnosis_scenes": [{
            "id": 1,
            "metric_id": ["A"],
            "trigger_condition": ["{A} == true AND {B} == true"],
            "start_node": "1",
        }],
        "steps": [{"id": 1, "details": [], "next": []}],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("未声明 metric_id" in e for e in errors)


def test_validator_accepts_structured_conditions():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [
                    {
                        "target": "2",
                        "condition": {
                            "all_of": [
                                {"compare": {"left": "A", "operator": ">", "right": 1}},
                                {"compare": {"left": "B", "operator": "==", "right": True}},
                            ]
                        },
                    }
                ],
            },
            {"id": 2, "details": [], "next": []},
        ],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert errors == []


def test_validator_detects_unknown_var_in_next_when_metrics_provided():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [{"target": "1", "condition": "{ghost_metric} == 1"}],
            },
        ],
    }
    errors = validate_rules_config(
        data,
        action_exists=has_action,
        metrics={"only_real": {}},
    )
    assert any("未知变量" in e and "ghost_metric" in e for e in errors)


def test_validator_accepts_next_var_from_branch_set_key():
    """Phase A：分支 set 注入的键名视为合法变量名。"""
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [
                    {
                        "target": "1",
                        "condition": "{injected} == 1",
                        "set": {"injected": "x"},
                    },
                ],
            },
        ],
    }
    errors = validate_rules_config(
        data,
        action_exists=has_action,
        metrics={},
    )
    assert errors == []


if __name__ == "__main__":
    test_current_rules_config_is_valid()
    test_validator_detects_missing_action_and_target()
    test_validator_detects_unparseable_condition()
    test_validator_rejects_deprecated_operator_limit_on_next()
    test_validator_detects_invalid_trigger_condition()
    test_validator_detects_trigger_metric_not_declared()
    test_validator_accepts_structured_conditions()
    test_validator_detects_unknown_var_in_next_when_metrics_provided()
    test_validator_accepts_next_var_from_branch_set_key()
    print("OK: test_rules_validator")
