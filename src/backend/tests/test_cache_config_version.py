"""
缓存按 config_version 失效测试(post-stage4 Bug #4 fix)

验证 service.RejectErrorService:
- _current_pipeline_version() 返回当前 pipeline.version
- _cache_version_matches() 正确判断:NULL/空 → 兼容,'unknown' → 兼容,其他 → 严格相等

不依赖 DB:用 SimpleNamespace 模拟 cached row。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.service.reject_error_service import RejectErrorService


def test_current_pipeline_version_reads_from_config_store():
    """版本号应来自 config/diagnosis.json -> reject_errors.diagnosis.json 的 version 字段。"""
    ver = RejectErrorService._current_pipeline_version()
    # 当前是 "3.0.0",我们不写死具体值,只断言是非空字符串且不是 'unknown'
    assert isinstance(ver, str) and ver and ver != "unknown", \
        f"reject_errors pipeline 应有 version 字段,实际 {ver!r}"


def test_cache_match_when_versions_equal():
    """缓存 version 与当前一致 → 命中。"""
    current = RejectErrorService._current_pipeline_version()
    cached = SimpleNamespace(config_version=current)
    assert RejectErrorService._cache_version_matches(cached) is True


def test_cache_miss_when_versions_differ():
    """缓存 version 与当前不一致 → 失配。"""
    cached = SimpleNamespace(config_version="0.1.0-ancient")
    assert RejectErrorService._cache_version_matches(cached) is False


def test_cache_match_when_cached_version_null_for_backward_compat():
    """缓存行 config_version=NULL(旧数据,Bug #4 fix 之前写入的) → 兼容,视为命中。"""
    cached = SimpleNamespace(config_version=None)
    assert RejectErrorService._cache_version_matches(cached) is True


def test_cache_match_when_cached_version_empty_string():
    """空字符串与 NULL 等价处理。"""
    cached = SimpleNamespace(config_version="")
    assert RejectErrorService._cache_version_matches(cached) is True


def test_cache_match_when_current_version_unknown(monkeypatch):
    """当前 version 读不到('unknown')时,不做版本比较,视为命中。"""
    monkeypatch.setattr(
        RejectErrorService,
        "_current_pipeline_version",
        classmethod(lambda cls: "unknown"),
    )
    cached = SimpleNamespace(config_version="3.0.0")
    assert RejectErrorService._cache_version_matches(cached) is True


def test_orm_class_has_config_version_column():
    """RejectedDetailedRecord ORM 应有 config_version 列(post-stage4 Bug #4)。"""
    from app.models.reject_errors_db import RejectedDetailedRecord
    assert hasattr(RejectedDetailedRecord, "config_version"), \
        "RejectedDetailedRecord 缺 config_version 列;迁移未完成"


def test_init_sql_has_config_version_column():
    """init_docker_db.sql 的 rejected_detailed_records DDL 应包含 config_version 列。"""
    repo_root = Path(__file__).resolve().parents[3]
    sql = (repo_root / "scripts" / "init_docker_db.sql").read_text(encoding="utf-8")
    assert "`config_version`" in sql, \
        "init_docker_db.sql 缺 `config_version` 列;DDL 与 ORM 不一致"
    assert "IDX_config_version" in sql, \
        "init_docker_db.sql 缺 IDX_config_version 索引"
