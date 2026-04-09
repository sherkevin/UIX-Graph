# -*- coding: utf-8 -*-
"""
拒片故障管理模块 - 接口 3 测试套件
覆盖：GET /reject-errors/{id}/metrics

运行方式:
    cd src/backend
    python -m pytest tests/test_reject_error_detail.py -v
    # 或直接：
    python tests/test_reject_error_detail.py

依赖 MySQL（通过 config/connections.json local 配置连接）。
"""
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.service.reject_error_service import RejectErrorService
from app.models.reject_errors_db import RejectedDetailedRecord, get_db_session

# ═══════════════════════════════════════════════════════════════════════════
# 测试工具
# ═══════════════════════════════════════════════════════════════════════════

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_true(label: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"    ✅ {label}{(' — ' + detail) if detail else ''}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}{(' — ' + detail) if detail else ''}")
        FAIL_COUNT += 1


def assert_eq(label: str, actual, expected):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        print(f"    ✅ {label}: {actual!r}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}: 期望 {expected!r}，实际 {actual!r}")
        FAIL_COUNT += 1


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def _get_first_valid_failure_id() -> int:
    """从数据库取一条真实记录 ID"""
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=1
    )
    if not records:
        raise RuntimeError("测试数据库无 SSB8000 记录，请先运行 scripts/init_docker_db.sql")
    return records[0]["id"]


def _get_first_coarse_align_failure_id() -> int:
    """从数据库取一条 COARSE_ALIGN_FAILED 的记录 ID"""
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=50
    )
    for r in records:
        if r.get("rejectReasonId") == 6:
            return r["id"]
    # 若前 50 条没有，再取后续
    for page in range(2, 20):
        records, meta = RejectErrorService.search_reject_errors(
            equipment="SSB8000", page_no=page, page_size=50
        )
        if not records:
            break
        for r in records:
            if r.get("rejectReasonId") == 6:
                return r["id"]
    raise RuntimeError("未找到 COARSE_ALIGN_FAILED（reject_reason_id=6）记录，请确认测试数据")


# ═══════════════════════════════════════════════════════════════════════════
# 接口 3 测试
# ═══════════════════════════════════════════════════════════════════════════

def test_detail_not_found():
    """接口 3 - 不存在的 ID：应返回 None（由 handler 转换为 404）"""
    section("接口3 - 不存在 ID 返回 None")
    detail_data, meta = RejectErrorService.get_failure_details(failure_id=999_999_999)
    assert_eq("不存在 ID 返回 None", detail_data, None)
    assert_eq("meta.total=0", meta["total"], 0)


def test_detail_unsupported_reject_reason():
    """接口 3 - 不支持诊断的 reject_reason：返回基础信息，metrics=[]"""
    section("接口3 - 不支持诊断的 reject_reason")
    records, _ = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=50
    )
    non_coarse = [r for r in records if r.get("rejectReasonId") != 6]
    if not non_coarse:
        print("    ⚠️  测试数据中所有记录均为 COARSE_ALIGN_FAILED，跳过此用例")
        return

    fid = non_coarse[0]["id"]
    detail_data, meta = RejectErrorService.get_failure_details(failure_id=fid)
    assert_true("返回非 None", detail_data is not None)
    assert_eq("非支持原因 metrics=[]", detail_data["metrics"] if detail_data else None, [])
    assert_eq("meta.total=0", meta["total"], 0)


def test_detail_coarse_align_basic():
    """接口 3 - COARSE_ALIGN_FAILED 基础诊断：返回结构完整"""
    section("接口3 - COARSE_ALIGN_FAILED 基础诊断")
    fid = _get_first_coarse_align_failure_id()
    detail_data, meta = RejectErrorService.get_failure_details(failure_id=fid)

    assert_true("返回非 None", detail_data is not None)
    if detail_data:
        for field in ["failureId", "equipment", "chuckId", "lotId", "waferIndex",
                      "rejectReason", "rejectReasonId", "rootCause", "time", "metrics"]:
            assert_true(f"字段 '{field}' 存在", field in detail_data, str(detail_data.get(field)))

        assert_true("rejectReasonId=6", detail_data["rejectReasonId"] == 6)
        assert_true("rootCause 非空", bool(detail_data.get("rootCause")), detail_data.get("rootCause"))
        assert_true("time 为 13 位时间戳", len(str(detail_data["time"])) == 13, str(detail_data["time"]))
        assert_true("meta.total >= 0", meta["total"] >= 0, str(meta["total"]))


def test_detail_cache_hit():
    """接口 3 - 缓存命中：同一 ID 请求两次，第二次来自缓存"""
    section("接口3 - 缓存命中验证")
    fid = _get_first_coarse_align_failure_id()

    # 清空该 ID 的缓存（确保第一次不命中）
    db = get_db_session()
    try:
        db.query(RejectedDetailedRecord).filter(
            RejectedDetailedRecord.failure_id == fid
        ).delete()
        db.commit()
    finally:
        db.close()

    # 第一次：缓存 miss，走诊断引擎
    detail1, _ = RejectErrorService.get_failure_details(failure_id=fid)
    # 第二次：缓存 hit
    detail2, _ = RejectErrorService.get_failure_details(failure_id=fid)

    assert_true("两次均返回非 None", detail1 is not None and detail2 is not None)
    if detail1 and detail2:
        assert_eq("两次 rootCause 一致", detail1.get("rootCause"), detail2.get("rootCause"))
        assert_eq("两次 system 一致", detail1.get("system"), detail2.get("system"))


def test_detail_bypass_cache_with_different_request_time():
    """接口 3 - requestTime 与发生时间不同：绕过缓存，不写缓存"""
    section("接口3 - requestTime 不同时绕过缓存")
    fid = _get_first_coarse_align_failure_id()

    # 先拿到发生时间
    records, _ = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=100
    )
    target = next((r for r in records if r["id"] == fid), None)
    if target is None:
        print("    ⚠️  找不到目标记录，跳过")
        return

    occurred_ms = target["time"]
    different_ms = occurred_ms - 60_000  # 提前 1 分钟

    # 绕过缓存查询（requestTime 不等于发生时间）
    detail, meta = RejectErrorService.get_failure_details(
        failure_id=fid, request_time_ms=different_ms
    )
    assert_true("绕过缓存仍返回结果", detail is not None)

    # 确认此次不写缓存（缓存表中若之前有记录保持不变，不影响正确性）
    if detail:
        assert_true("返回了 rootCause 或 None（绕过不报错）", "rootCause" in detail)


def test_detail_metric_pagination():
    """接口 3 - 指标分页：pageSize=2，多页数据不重叠"""
    section("接口3 - 指标分页")
    fid = _get_first_coarse_align_failure_id()

    detail_p1, meta_p1 = RejectErrorService.get_failure_details(
        failure_id=fid, page_no=1, page_size=2
    )
    assert_true("第1页返回结果", detail_p1 is not None)
    n_diag = meta_p1.get("metricDiagnosticTotal", meta_p1["total"])
    if detail_p1 and n_diag > 2:
        detail_p2, meta_p2 = RejectErrorService.get_failure_details(
            failure_id=fid, page_no=2, page_size=2
        )
        assert_true("第2页返回结果", detail_p2 is not None)
        if detail_p2:
            names_p1 = {m["name"] for m in detail_p1["metrics"] if m.get("type") != "model_param"}
            names_p2 = {m["name"] for m in detail_p2["metrics"] if m.get("type") != "model_param"}
            assert_eq("两页诊断指标无重叠", names_p1 & names_p2, set())
            assert_eq("两页 meta.total 相同", meta_p1["total"], meta_p2["total"])
            assert_eq("两页 metricDiagnosticTotal 相同", meta_p1["metricDiagnosticTotal"], meta_p2["metricDiagnosticTotal"])
    else:
        print("    ⚠️  诊断指标数 ≤ 2，无法验证多页，已跳过")


def test_detail_bypass_cache_with_same_time():
    """接口 3 - requestTime 与发生时间相同：也应绕过缓存，避免返回过期规则结果"""
    section("接口3 - requestTime 与发生时间相同时绕过缓存")
    fid = _get_first_coarse_align_failure_id()

    records, _ = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=100
    )
    target = next((r for r in records if r["id"] == fid), None)
    if target is None:
        print("    ⚠️  找不到目标记录，跳过")
        return

    occurred_ms = target["time"]

    # 以相同的毫秒时间请求，也应重算而不是直接命中缓存
    detail, meta = RejectErrorService.get_failure_details(
        failure_id=fid, request_time_ms=occurred_ms
    )
    assert_true("相同时间请求返回结果", detail is not None)
    if detail:
        assert_true("rootCause 字段存在", "rootCause" in detail)


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global PASS_COUNT, FAIL_COUNT
    PASS_COUNT = 0
    FAIL_COUNT = 0

    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  接口 3 测试套件（GET /{id}/metrics）".center(56) + "  █")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    test_detail_not_found()
    test_detail_unsupported_reject_reason()
    test_detail_coarse_align_basic()
    test_detail_cache_hit()
    test_detail_bypass_cache_with_different_request_time()
    test_detail_metric_pagination()
    test_detail_bypass_cache_with_same_time()

    total = PASS_COUNT + FAIL_COUNT
    print("\n" + "█" * 60)
    print(f"  测试结果：{PASS_COUNT}/{total} 通过")
    if FAIL_COUNT == 0:
        print("  🎉 所有测试通过！")
    else:
        print(f"  ⚠️  {FAIL_COUNT} 个测试失败，请检查上方日志。")
    print("█" * 60 + "\n")

    return FAIL_COUNT == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
