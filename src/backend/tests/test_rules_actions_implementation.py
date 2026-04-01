"""
Action 实现回归测试（无需数据库）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.actions import call_action


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


if __name__ == "__main__":
    test_determine_model_type_88um()
    test_determine_model_type_8um()
    test_build_88um_model_outputs()
    test_build_8um_model_outputs()
    print("OK: test_rules_actions_implementation")
