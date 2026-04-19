"""
机台白名单配置驱动测试(post-stage4 Bug #2 fix)

验证:
- service 启动从 config/equipments.json 读机台
- 文件缺失/解析错误时回退到内置默认
- 进程内缓存,reload 接口能刷新
- BC alias service.EQUIPMENT_WHITELIST 仍然可用(旧代码不破坏)
"""
import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.service.reject_error_service import (
    RejectErrorService,
    _DEFAULT_EQUIPMENTS,
)


@pytest.fixture(autouse=True)
def _reset_cache_around_each_test():
    """每个测试前后清空进程内缓存,避免互相污染。"""
    RejectErrorService._equipments_cache = None
    yield
    RejectErrorService._equipments_cache = None


def _write_config(tmp_path: Path, equipments: list, missing_key: bool = False) -> Path:
    fake_root = tmp_path / "uix-fake"
    (fake_root / "config").mkdir(parents=True)
    payload = {} if missing_key else {"equipments": equipments}
    (fake_root / "config" / "equipments.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return fake_root


def test_loads_from_real_config_file_under_repo_root():
    """不指定 UIX_ROOT 时,默认从 repo 根的 config/equipments.json 读。"""
    whitelist = RejectErrorService.equipment_whitelist()
    assert "SSB8000" in whitelist
    assert "SSC8001" in whitelist
    # 默认也应该全部能 validate
    assert RejectErrorService.validate_equipment("SSB8000") is True
    assert RejectErrorService.validate_equipment("UNKNOWN_RIG") is False


def test_loads_from_uix_root_override(tmp_path, monkeypatch):
    fake_root = _write_config(tmp_path, ["FAKE001", "FAKE002"])
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None  # 清缓存让 monkeypatch 生效

    whitelist = RejectErrorService.equipment_whitelist()
    assert sorted(whitelist) == ["FAKE001", "FAKE002"]
    assert RejectErrorService.validate_equipment("FAKE001") is True
    assert RejectErrorService.validate_equipment("SSB8000") is False


def test_falls_back_to_default_when_file_missing(tmp_path, monkeypatch):
    """不存在 config/equipments.json 时回退到内置默认列表。"""
    fake_root = tmp_path / "no-config-dir"
    (fake_root / "config").mkdir(parents=True)
    # 不写 equipments.json
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None

    whitelist = RejectErrorService.equipment_whitelist()
    assert whitelist == _DEFAULT_EQUIPMENTS


def test_falls_back_to_default_when_json_invalid(tmp_path, monkeypatch):
    fake_root = tmp_path / "bad-json"
    (fake_root / "config").mkdir(parents=True)
    (fake_root / "config" / "equipments.json").write_text("{ not valid json }", encoding="utf-8")
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None

    whitelist = RejectErrorService.equipment_whitelist()
    assert whitelist == _DEFAULT_EQUIPMENTS


def test_falls_back_to_default_when_equipments_list_empty(tmp_path, monkeypatch):
    fake_root = _write_config(tmp_path, [])  # 空列表
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None

    whitelist = RejectErrorService.equipment_whitelist()
    assert whitelist == _DEFAULT_EQUIPMENTS


def test_reload_equipments_refreshes_cache(tmp_path, monkeypatch):
    """改 JSON 后,reload_equipments() 应当让新机台生效。"""
    fake_root = _write_config(tmp_path, ["A001", "A002"])
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None

    assert sorted(RejectErrorService.equipment_whitelist()) == ["A001", "A002"]

    # 修改 JSON
    config_file = fake_root / "config" / "equipments.json"
    config_file.write_text(json.dumps({"equipments": ["B001", "B002", "B003"]}), encoding="utf-8")

    # 不调 reload 看不到新值
    assert sorted(RejectErrorService.equipment_whitelist()) == ["A001", "A002"]

    # reload 后才生效
    RejectErrorService.reload_equipments()
    assert sorted(RejectErrorService.equipment_whitelist()) == ["B001", "B002", "B003"]


def test_bc_alias_class_attribute_still_works():
    """老代码用 RejectErrorService.EQUIPMENT_WHITELIST 仍能拿到完整列表。"""
    whitelist = RejectErrorService.EQUIPMENT_WHITELIST
    assert isinstance(whitelist, list)
    assert "SSB8000" in whitelist


def test_whitelist_returns_copy_not_internal_reference(tmp_path, monkeypatch):
    """equipment_whitelist() 必须返回副本,调用方不能 mutate 内部 state。"""
    fake_root = _write_config(tmp_path, ["X001", "X002"])
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService._equipments_cache = None

    whitelist1 = RejectErrorService.equipment_whitelist()
    whitelist1.append("MUTATED")

    whitelist2 = RejectErrorService.equipment_whitelist()
    assert "MUTATED" not in whitelist2
    assert sorted(whitelist2) == ["X001", "X002"]
