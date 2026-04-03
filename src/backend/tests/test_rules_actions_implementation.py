"""
Action 实现回归测试（无需数据库）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions import call_action
from app.engine.actions.builtin import _run_model_once


def test_cowa_matlab_fixture_matches_pinv():
    """
    与用户提供的 MATLAB COWA 四参数脚本数值对齐（pinv(a1)*b1 及 Tx/Ty/Mw/Rw）。
    """
    out = _run_model_once(
        mark_scan=[
            (-4.950007090089312e-2, 1.102275511079749e-1),
            (5.052108622864396e-2, -1.097551035821438e-1),
        ],
        mark_data=[(-5.04e-2, 1.104e-1), (4.96e-2, -1.096e-1)],
        msx=1.000003160397744,
        msy=1.000004841099549,
        e_wsx=3.041574231200786e-7,
        e_wsy=1.701734537375717e-6,
        s_x=0.000935146384271204,
        s_y=-0.000339839162971417,
        d_x=-3.32067e-6,
        d_y=-8.61429e-6,
    )
    assert abs(out["output_Tx"] - (-21.58691089559314)) < 1e-6
    assert abs(out["output_Ty"] - 183.02995713073116) < 1e-6
    assert abs(out["output_Mw"] - (-24.560852937586414)) < 1e-6
    assert abs(out["output_Rw"] - 108.76964304623539) < 1e-6


def test_determine_model_type_88um():
    out = call_action("determine_model_type", None, {"Mwx_0": 1.0002})
    assert out["model_type"] == "88um"


def test_determine_model_type_8um():
    out = call_action("determine_model_type", None, {"Mwx_0": 1.00005})
    assert out["model_type"] == "8um"


def test_build_88um_model_outputs():
    ctx = {
        "ws_pos_x": [0.056, -0.064],
        "ws_pos_y": [0.021, -0.018],
        "mark_pos_x": [0.055, -0.063],
        "mark_pos_y": [0.020, -0.017],
        "Msx": 1.00000106,
        "Msy": 0.9999989718,
        "e_ws_x": -4.087065391e-07,
        "e_ws_y": -1.316297496e-06,
        "Sx": 6.91458953166459e-04,
        "Sy": -5.93531442506207e-04,
        "D_x": -1.5e-05,
        "D_y": 1.6e-05,
        "Tx": 0.2,
        "Ty": -0.3,
        "Rw": 10.0,
    }
    out = call_action("build_88um_model", None, ctx)
    assert "output_Tx" in out
    assert "output_Ty" in out
    assert "output_Mw" in out
    assert "output_Rw" in out
    assert 1 <= out["n_88um"] <= 8


def test_build_8um_model_outputs():
    ctx = {
        "ws_pos_x": [0.056, -0.064],
        "ws_pos_y": [0.021, -0.018],
        "mark_pos_x": [0.055, -0.063],
        "mark_pos_y": [0.020, -0.017],
        "Msx": 1.00000106,
        "Msy": 0.9999989718,
        "e_ws_x": -4.087065391e-07,
        "e_ws_y": -1.316297496e-06,
        "Sx": 6.91458953166459e-04,
        "Sy": -5.93531442506207e-04,
        "D_x": -1.5e-05,
        "D_y": 1.6e-05,
        "Tx": 0.2,
        "Ty": -0.3,
        "Rw": 10.0,
    }
    out = call_action("build_8um_model", None, ctx)
    assert "output_Tx" in out
    assert "output_Ty" in out
    assert "output_Mw" in out
    assert "output_Rw" in out
    assert 1 <= out["n_88um"] <= 8


def test_build_model_uses_explicit_model_type():
    ctx = {
        "model_type": "8um",
        "ws_pos_x": [0.056, -0.064],
        "ws_pos_y": [0.021, -0.018],
        "mark_pos_x": [0.055, -0.063],
        "mark_pos_y": [0.020, -0.017],
        "Msx": 1.00000106,
        "Msy": 0.9999989718,
        "e_ws_x": -4.087065391e-07,
        "e_ws_y": -1.316297496e-06,
        "Sx": 6.91458953166459e-04,
        "Sy": -5.93531442506207e-04,
        "D_x": -1.5e-05,
        "D_y": 1.6e-05,
    }
    out = call_action("build_model", None, ctx)
    assert out["model_type"] == "8um"
    assert "output_Mw" in out


def test_build_model_auto_determines_type_from_mwx0():
    ctx = {
        "Mwx_0": 1.0002,  # 对应 88um
        "ws_pos_x": [0.056, -0.064],
        "ws_pos_y": [0.021, -0.018],
        "mark_pos_x": [0.055, -0.063],
        "mark_pos_y": [0.020, -0.017],
        "Msx": 1.00000106,
        "Msy": 0.9999989718,
        "e_ws_x": -4.087065391e-07,
        "e_ws_y": -1.316297496e-06,
        "Sx": 6.91458953166459e-04,
        "Sy": -5.93531442506207e-04,
        "D_x": -1.5e-05,
        "D_y": 1.6e-05,
    }
    out = call_action("build_model", None, ctx)
    assert out["model_type"] == "88um"
    assert "output_Mw" in out


if __name__ == "__main__":
    test_cowa_matlab_fixture_matches_pinv()
    test_determine_model_type_88um()
    test_determine_model_type_8um()
    test_build_88um_model_outputs()
    test_build_8um_model_outputs()
    test_build_model_uses_explicit_model_type()
    test_build_model_auto_determines_type_from_mwx0()
    print("OK: test_rules_actions_implementation")
