"""
safe_eval action 测试

覆盖目标:
- **配置驱动可用性**:常见数学/比较/布尔表达式都能跑(让专家写 JSON 不用写 Python)
- **安全性**:任何不在白名单的语法都拒绝(保护服务不被恶意配置注入代码)
- **边界**:expr/out 缺失、变量未定义、运行时错误等都不让 action 崩溃
"""
import math
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions import call_action, has_action
from app.engine.actions.safe_eval import (
    SafeEvalError,
    safe_arithmetic_eval,
    safe_eval_action,
)


# ── 1. 注册到 actions 注册表 ─────────────────────────────────────


def test_safe_eval_is_registered_via_autoload():
    assert has_action("safe_eval"), "safe_eval action 应被自动加载注册"


def test_safe_eval_callable_via_call_action():
    out = call_action(
        "safe_eval",
        params={"expr": "Tx + Ty", "out": "sum_xy"},
        context={"Tx": 3, "Ty": 4},
    )
    assert out == {"sum_xy": 7}


# ── 2. 算术 / 数字 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("1 + 2", 3),
        ("10 - 4", 6),
        ("3 * 5", 15),
        ("10 / 4", 2.5),
        ("10 // 3", 3),
        ("10 % 3", 1),
        ("2 ** 10", 1024),
        ("-5", -5),
        ("+5", 5),
        ("(1 + 2) * 3", 9),
        ("1.5 + 2.5", 4.0),
    ],
)
def test_arithmetic_literals(expr, expected):
    assert safe_arithmetic_eval(expr, {}) == expected


# ── 3. 变量引用从 ctx ─────────────────────────────────────────────


def test_variable_lookup_from_ctx():
    assert safe_arithmetic_eval("Tx + Ty", {"Tx": 10, "Ty": 5}) == 15


def test_variable_lookup_chained_in_complex_expr():
    ctx = {"Mwx_0": 1.00012, "Tx": 25.5, "Ty": -3.0}
    assert safe_arithmetic_eval("Mwx_0 * 1000", ctx) == pytest.approx(1000.12)
    assert safe_arithmetic_eval("Tx ** 2 + Ty ** 2", ctx) == pytest.approx(25.5 ** 2 + 9.0)


def test_unknown_variable_raises():
    with pytest.raises(SafeEvalError, match="未知变量"):
        safe_arithmetic_eval("undefined_var + 1", {})


# ── 4. 数学常量 ─────────────────────────────────────────────────


def test_math_constants():
    assert safe_arithmetic_eval("pi", {}) == pytest.approx(math.pi)
    assert safe_arithmetic_eval("e", {}) == pytest.approx(math.e)
    assert safe_arithmetic_eval("True", {}) is True
    assert safe_arithmetic_eval("False", {}) is False
    assert safe_arithmetic_eval("None", {}) is None


def test_ctx_overrides_constants():
    """ctx 优先于内置常量(避免命名冲突无法绕过)。"""
    assert safe_arithmetic_eval("pi", {"pi": 999}) == 999


# ── 5. 比较 / 布尔 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "expr, ctx, expected",
    [
        ("Tx > 20", {"Tx": 25}, True),
        ("Tx > 20", {"Tx": 19}, False),
        ("Tx >= 20 and Ty < 0", {"Tx": 20, "Ty": -1}, True),
        ("Tx > 20 or Ty < 0", {"Tx": 5, "Ty": -1}, True),
        ("Tx > 20 or Ty < 0", {"Tx": 5, "Ty": 5}, False),
        ("not Tx", {"Tx": 0}, True),
        ("not Tx", {"Tx": 1}, False),
        # 链式比较(Python 原生)
        ("0 < Tx < 100", {"Tx": 50}, True),
        ("0 < Tx < 100", {"Tx": 150}, False),
        ("-2 < Tx < 2", {"Tx": 0.5}, True),
    ],
)
def test_comparison_and_boolean(expr, ctx, expected):
    assert safe_arithmetic_eval(expr, ctx) is expected


def test_string_equality():
    assert safe_arithmetic_eval("model_type == '88um'", {"model_type": "88um"}) is True
    assert safe_arithmetic_eval("model_type == '88um'", {"model_type": "8um"}) is False


# ── 6. 三目运算 ────────────────────────────────────────────────


def test_ternary_expression():
    assert safe_arithmetic_eval("100 if Tx > 0 else -100", {"Tx": 5}) == 100
    assert safe_arithmetic_eval("100 if Tx > 0 else -100", {"Tx": -5}) == -100


# ── 7. 安全函数白名单 ──────────────────────────────────────────


def test_abs_function():
    assert safe_arithmetic_eval("abs(Tx)", {"Tx": -5}) == 5


def test_min_max_function():
    assert safe_arithmetic_eval("min(Tx, Ty)", {"Tx": 3, "Ty": 7}) == 3
    assert safe_arithmetic_eval("max(Tx, Ty)", {"Tx": 3, "Ty": 7}) == 7
    assert safe_arithmetic_eval("min(1, 2, 3, Tx)", {"Tx": 0}) == 0


def test_round_function():
    assert safe_arithmetic_eval("round(Mwx_0, 4)", {"Mwx_0": 1.000125}) == 1.0001


def test_int_float_bool_cast():
    assert safe_arithmetic_eval("int(Tx)", {"Tx": 3.7}) == 3
    assert safe_arithmetic_eval("float(Tx)", {"Tx": 3}) == 3.0
    assert safe_arithmetic_eval("bool(Tx)", {"Tx": 0}) is False


def test_math_sqrt_log():
    assert safe_arithmetic_eval("sqrt(Tx_Ty_sum_sq)", {"Tx_Ty_sum_sq": 25}) == 5.0
    assert safe_arithmetic_eval("log10(Tx)", {"Tx": 1000}) == pytest.approx(3.0)


# ── 8. 安全性:拒绝危险语法 ──────────────────────────────────────


@pytest.mark.parametrize(
    "danger_expr",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "(1).__class__",                    # 属性访问禁
        "[1, 2, 3]",                        # 列表字面量禁
        "{1: 2}",                           # 字典字面量禁
        "{1, 2}",                           # 集合字面量禁
        "(x for x in [1])",                 # 生成器禁
        "[x for x in [1]]",                 # 列表推导禁
        "lambda x: x",                      # lambda 禁
        "exec('print(1)')",                 # exec 禁(不在白名单)
        "eval('1+1')",                      # eval 禁
        "globals()",                        # globals 禁
        "Tx[0]",                            # 订阅禁
        "Tx.bit_length()",                  # 方法调用禁(属性访问就拒了)
    ],
)
def test_dangerous_syntax_rejected(danger_expr):
    with pytest.raises(SafeEvalError):
        safe_arithmetic_eval(danger_expr, {"Tx": 5})


def test_keyword_arguments_rejected():
    with pytest.raises(SafeEvalError, match="关键字参数"):
        safe_arithmetic_eval("round(Tx, ndigits=2)", {"Tx": 1.234})


# ── 9. 配置约定:expr/out 缺失时不崩 ───────────────────────────


def test_action_missing_expr_returns_empty():
    out = safe_eval_action(expr=None, out="x", Tx=5)
    assert out == {}


def test_action_missing_out_returns_empty():
    out = safe_eval_action(expr="Tx + 1", out=None, Tx=5)
    assert out == {}


def test_action_runtime_error_returns_empty_not_raise():
    # 除以 0 应该被吞掉(不让 action 崩坏整条诊断)
    out = safe_eval_action(expr="Tx / Ty", out="z", Tx=5, Ty=0)
    assert out == {}


def test_action_unknown_var_returns_empty_not_raise():
    out = safe_eval_action(expr="undefined_var + 1", out="z")
    assert out == {}


def test_action_syntax_error_returns_empty_not_raise():
    out = safe_eval_action(expr="1 + + +", out="z")
    assert out == {}


# ── 10. 真实诊断场景 ────────────────────────────────────────────


def test_realistic_cowa_case_threshold_check():
    """模拟 COWA 场景:综合偏差超阈值。"""
    ctx = {"Tx": 25.5, "Ty": -3.0, "Rw": 150}
    is_abnormal = safe_arithmetic_eval(
        "abs(Tx) > 20 or abs(Ty) > 20 or abs(Rw) > 300", ctx
    )
    assert is_abnormal is True


def test_realistic_compute_intermediate():
    """模拟中间量:计算 Tx+Ty 的几何模长。"""
    ctx = {"Tx": 3, "Ty": 4}
    out = call_action(
        "safe_eval",
        params={"expr": "sqrt(Tx ** 2 + Ty ** 2)", "out": "txy_norm"},
        context=ctx,
    )
    assert out == {"txy_norm": pytest.approx(5.0)}
