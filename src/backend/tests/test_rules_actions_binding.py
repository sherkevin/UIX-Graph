"""
rules action 参数绑定回归测试（无需数据库）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions import call_action, has_action


def test_builtin_actions_autoloaded():
    assert has_action("increment_counter")
    assert has_action("calculate_monthly_mean_Rw")


def test_params_constant_and_context_binding():
    # counter_name/increment 由 params 常量传入，不依赖 context 是否存在同名键
    result = call_action(
        "increment_counter",
        {"counter_name": "normal_count", "increment": 2},
        {"normal_count": 1, "counter_name": "should_not_override", "increment": 999},
    )
    assert result["normal_count"] == 3


def test_params_empty_string_bind_from_context():
    result = call_action(
        "calculate_monthly_mean_Rw",
        {"Rw": ""},
        {"Rw": 123.45},
    )
    assert abs(result["mean_Rw"] - 123.45) < 1e-9


if __name__ == "__main__":
    test_builtin_actions_autoloaded()
    test_params_constant_and_context_binding()
    test_params_empty_string_bind_from_context()
    print("OK: test_rules_actions_binding")
