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


def test_validator_detects_unsupported_operator():
    data = {
        "diagnosis_scenes": [{"id": 1, "start_node": "1"}],
        "steps": [
            {
                "id": 1,
                "details": [],
                "next": [{"target": "1", "condition": "{x} ~~ 1", "operator": "~~", "limit": 1}],
            }
        ],
    }
    errors = validate_rules_config(data, action_exists=has_action)
    assert any("operator 不支持" in e for e in errors)


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


if __name__ == "__main__":
    test_current_rules_config_is_valid()
    test_validator_detects_missing_action_and_target()
    test_validator_detects_unparseable_condition()
    test_validator_detects_unsupported_operator()
    test_validator_detects_invalid_trigger_condition()
    test_validator_detects_trigger_metric_not_declared()
    test_validator_accepts_structured_conditions()
    print("OK: test_rules_validator")
