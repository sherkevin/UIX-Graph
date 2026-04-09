"""
/api/diagnosis 统一配置驱动适配器测试（无需数据库）。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.diagnosis_engine import DiagnosisEngine


def test_core_diagnosis_rotation_rule():
    result = DiagnosisEngine.analyze(
        params={"rotation_mean": 320, "rotation_3sigma": 200, "vacuum_level": "High"}
    )
    assert result["root_cause"] == "上片旋转机械超限"
    assert result["confidence"] == 85
    assert result["category"] == "机械精度"


def test_core_diagnosis_vacuum_rule():
    result = DiagnosisEngine.analyze(
        params={"rotation_mean": 150, "rotation_3sigma": 200, "vacuum_level": "Low"}
    )
    assert result["root_cause"] == "WS 硬件物理损坏/泄露"
    assert result["category"] == "硬件损耗"


def test_core_diagnosis_fallback_rule():
    result = DiagnosisEngine.analyze(
        params={"rotation_mean": 50, "rotation_3sigma": 80, "vacuum_level": "High"}
    )
    assert result["root_cause"] == "未知原因"
    assert result["confidence"] == 30


def test_core_diagnosis_get_rules_from_config():
    rules = DiagnosisEngine.get_rules()
    root_causes = {item["root_cause"] for item in rules}
    assert "上片旋转机械超限" in root_causes
    assert "WS 硬件物理损坏/泄露" in root_causes
