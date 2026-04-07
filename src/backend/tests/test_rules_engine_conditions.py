"""
rules 条件表达式求值回归测试（无需数据库）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.diagnosis_engine import DiagnosisEngine
from app.engine.condition_evaluator import evaluate_condition_text


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
    matched, var_name, operator, limit, value = evaluate_condition_text(
        "-300<{mean_Rw}<300",
        {"mean_Rw": 120},
        None,
    )
    assert matched is True
    assert var_name == "mean_Rw"
    assert operator == "between"
    assert limit == [-300.0, 300.0]
    assert value == 120.0


def test_multiple_branch_match_falls_back_to_else():
    engine = DiagnosisEngine()
    step = {"id": "ambiguous_step", "metric_id": "Tx"}
    branches = [
        {"target": "A", "condition": "{Tx} > 1", "operator": ">", "limit": 1},
        {"target": "B", "condition": "{Tx} > 2", "operator": ">", "limit": 2},
        {"target": "E", "condition": "else"},
    ]
    context = {"Tx": 3}

    target, _ = engine._evaluate_branches(step, branches, context, [])
    assert str(target) == "E"


def test_no_match_without_else_returns_none():
    engine = DiagnosisEngine()
    step = {"id": "no_else_step", "metric_id": "Tx"}
    branches = [
        {"target": "A", "condition": "{Tx} > 10", "operator": ">", "limit": 10},
    ]
    context = {"Tx": 3}

    target, branch = engine._evaluate_branches(step, branches, context, [])
    assert target is None
    assert branch is None


def test_expression_string_equality_not_match():
    engine = DiagnosisEngine()
    step = {"id": "continue_model", "metric_id": None}
    branches = [
        {"target": "10", "condition": "{model_type} == '88um'"},
        {"target": "11", "condition": "{model_type} == '8um'"},
        {"target": "99", "condition": "else"},
    ]
    context = {"model_type": "unknown"}

    target, _ = engine._evaluate_branches(step, branches, context, [])
    assert str(target) == "99"


def test_mwx0_threshold_uses_rule_branches_not_fake_between():
    engine = DiagnosisEngine()
    threshold = engine._find_threshold("Mwx_0")
    assert threshold is not None
    assert threshold["operator"] == "any_of"
    assert threshold["limit"] == [
        {"operator": ">", "limit": 1.0001},
        {"operator": "<", "limit": 0.9999},
        {"operator": "between", "limit": [1.00002, 1.0001]},
        {"operator": "between", "limit": [0.9999, 0.99998]},
    ]


def test_mwx0_status_respects_sparse_valid_ranges():
    engine = DiagnosisEngine()
    threshold = engine._find_threshold("Mwx_0")
    assert threshold is not None
    assert engine._is_within_normal_range(1.0, threshold["operator"], threshold["limit"]) is False
    assert engine._is_within_normal_range(1.00005, threshold["operator"], threshold["limit"]) is True
    assert engine._is_within_normal_range(1.0002, threshold["operator"], threshold["limit"]) is True


def test_between_threshold_uses_open_interval():
    engine = DiagnosisEngine()
    assert engine._is_within_normal_range(0.0, "between", [-20, 20]) is True
    assert engine._is_within_normal_range(-20.0, "between", [-20, 20]) is False
    assert engine._is_within_normal_range(20.0, "between", [-20, 20]) is False


def test_parallel_targets_execute_independently_and_accumulate_normal_count():
    engine = DiagnosisEngine()
    root_cause, system, trace, abnormal_metrics, final_context = engine._walk_tree(
        "21",
        {
            "output_Mw": 5.0,
            "output_Tx": 1.0,
            "output_Ty": 1.0,
            "output_Rw": 10.0,
        },
        base_context={"normal_count": 0},
    )
    assert root_cause == "人工处理"
    assert final_context.get("normal_count") == 3
    assert "22" in trace and "23" in trace and "24" in trace


def test_parallel_targets_can_reach_tx_root_cause_branch():
    engine = DiagnosisEngine()
    root_cause, system, trace, abnormal_metrics, final_context = engine._walk_tree(
        "21",
        {
            "output_Mw": 5.0,
            "output_Tx": 25.0,
            "output_Ty": 1.0,
            "output_Rw": 10.0,
            "Tx": 25.0,
            "mean_Tx": 0.5,
        },
        base_context={"normal_count": 0},
    )
    assert root_cause in {"上片工艺适应性问题", "上片偏差异常"}
    assert "30" in trace
    assert ("40" in trace) or ("41" in trace)


def test_metrics_list_uses_final_context_outputs_and_means():
    engine = DiagnosisEngine()
    metrics = engine._build_metrics_list(
        ["Mwx_0", "n_88um", "output_Mw", "output_Tx", "mean_Tx"],
        {
            "Mwx_0": 1.00005,
            "n_88um": 3.0,
            "output_Mw": 5.0,
            "output_Tx": 25.0,
            "mean_Tx": 0.5,
        },
    )
    by_name = {m["name"]: m for m in metrics}
    assert "output_Tx" in by_name
    assert "mean_Tx" in by_name
    assert by_name["output_Tx"]["status"] == "ABNORMAL"
    assert by_name["mean_Tx"]["status"] == "NORMAL"


if __name__ == "__main__":
    test_expression_string_equality_branch()
    test_expression_numeric_equality_branch()
    test_expression_between_without_operator()
    test_multiple_branch_match_falls_back_to_else()
    test_no_match_without_else_returns_none()
    test_expression_string_equality_not_match()
    test_mwx0_threshold_uses_rule_branches_not_fake_between()
    test_mwx0_status_respects_sparse_valid_ranges()
    test_between_threshold_uses_open_interval()
    test_parallel_targets_execute_independently_and_accumulate_normal_count()
    test_parallel_targets_can_reach_tx_root_cause_branch()
    test_metrics_list_uses_final_context_outputs_and_means()
    print("OK: test_rules_engine_conditions")
