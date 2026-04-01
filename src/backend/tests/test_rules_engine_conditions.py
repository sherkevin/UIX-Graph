"""
rules 条件表达式求值回归测试（无需数据库）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.diagnosis_engine import DiagnosisEngine


def test_expression_string_equality_branch():
    engine = DiagnosisEngine()
    step = {"id": "continue_model", "metric_id": None}
    branches = [
        {"target": "10", "condition": "{model_type} == '88um'"},
        {"target": "11", "condition": "{model_type} == '8um'"},
    ]
    context = {"model_type": "88um"}

    target, _ = engine._evaluate_branches(step, branches, context, [])
    assert str(target) == "10"


def test_expression_numeric_equality_branch():
    engine = DiagnosisEngine()
    step = {"id": "50", "metric_id": None}
    branches = [{"target": "99", "condition": "{normal_count} == 3"}]
    context = {"normal_count": 3}

    target, _ = engine._evaluate_branches(step, branches, context, [])
    assert str(target) == "99"


def test_expression_between_without_operator():
    engine = DiagnosisEngine()
    matched, var_name, operator, limit, value = engine._eval_condition_by_text(
        "-300<{mean_Rw}<300",
        {"mean_Rw": 120},
        None,
    )
    assert matched is True
    assert var_name == "mean_Rw"
    assert operator == "between"
    assert limit == [-300.0, 300.0]
    assert value == 120.0


if __name__ == "__main__":
    test_expression_string_equality_branch()
    test_expression_numeric_equality_branch()
    test_expression_between_without_operator()
    print("OK: test_rules_engine_conditions")
