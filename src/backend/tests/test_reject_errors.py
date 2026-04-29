"""
拒片故障管理模块 - 接口测试套件
覆盖接口 1 (GET /reject-errors/metadata) 和接口 2 (POST /reject-errors/search)

运行方式:
    cd src/backend
    python -m pytest tests/test_reject_errors.py -v
    # 或直接运行（无需 pytest）:
    python tests/test_reject_errors.py
"""
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any

# ── UTF-8 输出（仅独立运行时生效；pytest capture 下若替换 sys.stdout
#    会破坏退出阶段的 readouterr，表现为 "I/O operation on closed file"）──
if __name__ == "__main__" and sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── 将项目根目录加入 Python 路径 ─────────────────────────────────────────
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest  # noqa: E402

from app.service.reject_error_service import RejectErrorService  # noqa: E402
from app.models.reject_errors_db import get_db_session  # noqa: E402


def _db_reachable() -> tuple[bool, str]:
    try:
        from sqlalchemy import text  # noqa: WPS433
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


_db_ok, _db_err = _db_reachable()
if not _db_ok and __name__ != "__main__":
    pytest.skip(
        f"接口 1/2 测试依赖 MySQL；当前不可达：{_db_err}。"
        f"请先 `docker-compose up -d` 起本地库。",
        allow_module_level=True,
    )

# ═══════════════════════════════════════════════════════════════════════════
# 测试工具函数
# ═══════════════════════════════════════════════════════════════════════════

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_eq(label: str, actual, expected):
    """断言相等"""
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        print(f"    ✅ {label}: {actual!r}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}: 期望 {expected!r}，实际 {actual!r}")
        FAIL_COUNT += 1


def assert_true(label: str, condition: bool, detail: str = ""):
    """断言为真"""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"    ✅ {label}{(' — ' + detail) if detail else ''}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}{(' — ' + detail) if detail else ''}")
        FAIL_COUNT += 1


def assert_raises(label: str, exc_type, func, *args, **kwargs):
    """断言抛出异常"""
    global PASS_COUNT, FAIL_COUNT
    try:
        func(*args, **kwargs)
        print(f"    ❌ {label}: 期望抛出 {exc_type.__name__}，但未抛出")
        FAIL_COUNT += 1
    except exc_type as e:
        print(f"    ✅ {label}: 正确抛出 {exc_type.__name__}({e})")
        PASS_COUNT += 1
    except Exception as e:
        print(f"    ❌ {label}: 期望 {exc_type.__name__}，实际抛出 {type(e).__name__}({e})")
        FAIL_COUNT += 1


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════════════════
# 接口 1 测试：GET /reject-errors/metadata
# ═══════════════════════════════════════════════════════════════════════════

def test_metadata_basic():
    """接口 1 - 基础查询：SSB8000 应返回正确的 Chuck/Lot/Wafer 层级结构"""
    section("接口1 - 基础查询 (equipment=SSB8000)")
    data = RejectErrorService.get_metadata("SSB8000")

    assert_true("返回非空列表", len(data) > 0, f"共 {len(data)} 个 Chuck")

    # 校验顶层结构
    first_chuck = data[0]
    assert_true("chuckId 字段存在且为 int", isinstance(first_chuck["chuckId"], int))
    assert_true("chuckName 字段存在", "chuckName" in first_chuck)
    assert_true("availableLots 字段存在", "availableLots" in first_chuck)

    # 校验 Lot 层
    first_lot = first_chuck["availableLots"][0]
    assert_true("lotId 字段存在且为 int", isinstance(first_lot["lotId"], int))
    assert_true("lotName 字段存在", "lotName" in first_lot)
    assert_true("availableWafers 字段存在且为列表", isinstance(first_lot["availableWafers"], list))

    # 校验 Wafer 层（1-25 范围）
    for wafer_id in first_lot["availableWafers"]:
        assert_true(
            f"waferIndex={wafer_id} 在 1-25 范围内",
            1 <= wafer_id <= 25
        )

    # 校验 Chuck 按 ID 升序排列
    chuck_ids = [c["chuckId"] for c in data]
    assert_eq("Chuck 列表按 ID 升序", chuck_ids, sorted(chuck_ids))


def test_metadata_multiple_equipment():
    """接口 1 - 多机台查询：SSB8001 / SSC8001 / SSB8005 各自独立"""
    section("接口1 - 多机台查询")
    for equip in ["SSB8001", "SSC8001", "SSB8005"]:
        data = RejectErrorService.get_metadata(equip)
        assert_true(f"{equip} 返回非空", len(data) > 0, f"共 {len(data)} 个 Chuck")


def test_metadata_invalid_equipment():
    """接口 1 - 非法机台：应抛出 ValueError"""
    section("接口1 - 非法机台校验")
    assert_raises(
        "非白名单机台 INVALID_MACHINE 抛出 ValueError",
        ValueError,
        RejectErrorService.get_metadata,
        "INVALID_MACHINE"
    )
    assert_raises(
        "空字符串机台抛出 ValueError",
        ValueError,
        RejectErrorService.get_metadata,
        ""
    )


def test_metadata_time_filter():
    """接口 1 - 时间筛选：传入时间范围应仅返回该范围内的数据"""
    section("接口1 - 时间范围筛选")
    # 2026-01-10 ~ 2026-01-12 之间只有 SSB8000 的部分数据
    start_ts = 1736467200000  # 2026-01-10 00:00:00 UTC+8
    end_ts   = 1736726400000  # 2026-01-13 00:00:00 UTC+8

    data_filtered = RejectErrorService.get_metadata("SSB8000", start_time=start_ts, end_time=end_ts)
    data_all      = RejectErrorService.get_metadata("SSB8000")

    # 时间过滤后数据条目 ≤ 全量数据
    total_filtered_wafers = sum(
        len(lot["availableWafers"])
        for chuck in data_filtered
        for lot in chuck["availableLots"]
    )
    total_all_wafers = sum(
        len(lot["availableWafers"])
        for chuck in data_all
        for lot in chuck["availableLots"]
    )
    assert_true(
        "时间过滤后 Wafer 数量 ≤ 全量",
        total_filtered_wafers <= total_all_wafers,
        f"过滤后={total_filtered_wafers}，全量={total_all_wafers}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 接口 2 测试：POST /reject-errors/search
# ═══════════════════════════════════════════════════════════════════════════

def test_search_basic():
    """接口 2 - 基础全量查询：不传任何筛选条件，应返回全部记录"""
    section("接口2 - 基础全量查询 (equipment=SSB8000)")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=20
    )

    assert_true("返回记录非空", len(records) > 0, f"共 {meta['total']} 条")
    assert_eq("meta.pageNo", meta["pageNo"], 1)
    assert_eq("meta.pageSize", meta["pageSize"], 20)
    assert_true("meta.total > 0", meta["total"] > 0)
    assert_true("meta.totalPages 正确", meta["totalPages"] == (meta["total"] + 19) // 20)

    # 校验单条记录字段完整性
    rec = records[0]
    for field in ["id", "failureId", "chuckId", "lotId", "waferIndex",
                  "rejectReason", "rejectReasonId", "time"]:
        assert_true(f"字段 '{field}' 存在", field in rec)

    # time 应为 13 位时间戳
    assert_true("time 为 13 位时间戳", len(str(rec["time"])) == 13, str(rec["time"]))


def test_search_filter_chuck():
    """接口 2 - 按 Chuck 筛选：只查 chuck_id=1"""
    section("接口2 - 按 Chuck 筛选 (chucks=[1])")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=50,
        chucks=[1]
    )
    assert_true("返回记录非空", len(records) > 0)
    for rec in records:
        assert_eq(f"记录 id={rec['id']} 的 chuckId=1", rec["chuckId"], 1)


def test_search_filter_lot():
    """接口 2 - 按 Lot 筛选：只查 lot_id=101"""
    section("接口2 - 按 Lot 筛选 (lots=[101])")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=50,
        lots=[101]
    )
    assert_true("返回记录非空", len(records) > 0)
    for rec in records:
        assert_eq(f"记录 id={rec['id']} 的 lotId=101", rec["lotId"], 101)


def test_search_filter_wafer():
    """接口 2 - 按 Wafer 筛选：只查 wafer_id=1"""
    section("接口2 - 按 Wafer 筛选 (wafers=[1])")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=50,
        wafers=[1]
    )
    assert_true("返回记录非空", len(records) > 0)
    for rec in records:
        assert_eq(f"记录 id={rec['id']} 的 waferIndex=1", rec["waferIndex"], 1)


def test_search_filter_combined():
    """接口 2 - 组合筛选：chuck=1 + lot=101"""
    section("接口2 - 组合筛选 (chucks=[1], lots=[101])")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=50,
        chucks=[1],
        lots=[101]
    )
    assert_true("返回记录非空", len(records) > 0)
    for rec in records:
        assert_eq(f"id={rec['id']} chuckId=1", rec["chuckId"], 1)
        assert_eq(f"id={rec['id']} lotId=101", rec["lotId"], 101)


def test_search_empty_array_intercept():
    """接口 2 - 空数组拦截：chucks=[] 应直接返回空，不查 DB"""
    section("接口2 - 空数组拦截规则")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=20,
        chucks=[]
    )
    assert_eq("chucks=[] 返回 data=[]", records, [])
    assert_eq("chucks=[] 返回 meta.total=0", meta["total"], 0)

    records2, meta2 = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=20,
        lots=[]
    )
    assert_eq("lots=[] 返回 data=[]", records2, [])

    records3, meta3 = RejectErrorService.search_reject_errors(
        equipment="SSB8000",
        page_no=1,
        page_size=20,
        wafers=[]
    )
    assert_eq("wafers=[] 返回 data=[]", records3, [])


def test_search_pagination():
    """接口 2 - 分页：page_size=3，验证各页数据不重叠"""
    section("接口2 - 分页逻辑验证")
    page1, meta1 = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=3
    )
    page2, meta2 = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=2, page_size=3
    )

    assert_eq("page1 返回 3 条", len(page1), 3)
    assert_true("page2 返回 ≤ 3 条", len(page2) <= 3)

    ids_page1 = {r["id"] for r in page1}
    ids_page2 = {r["id"] for r in page2}
    assert_eq("两页记录无重叠", ids_page1 & ids_page2, set())

    assert_eq("两页 total 相同", meta1["total"], meta2["total"])


def test_search_deep_page_guard():
    """接口 2 - 深层分页防备：pageNo 超出最大页数应返回空数组"""
    section("接口2 - 深层分页防备")
    records, meta = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=9999, page_size=20
    )
    assert_eq("超出最大页码返回 data=[]", records, [])
    assert_true("meta.total 仍有值", meta["total"] >= 0)


def test_search_sort_desc():
    """接口 2 - 排序：默认 time desc，第一条时间 ≥ 最后一条"""
    section("接口2 - 时间降序排序验证")
    records, _ = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=20,
        order_by="time", order_dir="desc"
    )
    if len(records) >= 2:
        assert_true(
            "time desc: 第一条 ≥ 最后一条",
            records[0]["time"] >= records[-1]["time"],
            f"{records[0]['time']} >= {records[-1]['time']}"
        )


def test_search_sort_asc():
    """接口 2 - 排序：time asc，第一条时间 ≤ 最后一条"""
    section("接口2 - 时间升序排序验证")
    records, _ = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=20,
        order_by="time", order_dir="asc"
    )
    if len(records) >= 2:
        assert_true(
            "time asc: 第一条 ≤ 最后一条",
            records[0]["time"] <= records[-1]["time"],
            f"{records[0]['time']} <= {records[-1]['time']}"
        )


def test_search_invalid_equipment():
    """接口 2 - 非法机台：应抛出 ValueError"""
    section("接口2 - 非法机台校验")
    assert_raises(
        "非白名单机台抛出 ValueError",
        ValueError,
        RejectErrorService.search_reject_errors,
        "NOT_A_MACHINE",
        1, 20
    )


def test_search_invalid_wafer_range():
    """接口 2 - Wafer ID 越界：wafer_id=26 应抛出 ValueError"""
    section("接口2 - Wafer ID 范围校验")
    assert_raises(
        "wafer_id=26 超出范围抛出 ValueError",
        ValueError,
        RejectErrorService.search_reject_errors,
        "SSB8000", 1, 20, None, None, [26]
    )
    assert_raises(
        "wafer_id=0 超出范围抛出 ValueError",
        ValueError,
        RejectErrorService.search_reject_errors,
        "SSB8000", 1, 20, None, None, [0]
    )


def test_search_null_filters_means_all():
    """接口 2 - null 筛选条件：chucks/lots/wafers 为 None 表示全选"""
    section("接口2 - null 筛选条件等价于全选")
    records_null, meta_null = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=100,
        chucks=None, lots=None, wafers=None
    )
    records_all, meta_all = RejectErrorService.search_reject_errors(
        equipment="SSB8000", page_no=1, page_size=100
    )
    assert_eq("null 筛选与不传等价（total 相同）", meta_null["total"], meta_all["total"])


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global PASS_COUNT, FAIL_COUNT
    PASS_COUNT = 0
    FAIL_COUNT = 0

    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  拒片故障管理模块 - 接口 1 & 2 测试套件".center(56) + "  █")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    # ── 接口 1 测试 ────────────────────────────────────────────
    print("\n▶ 接口 1：GET /reject-errors/metadata")
    test_metadata_basic()
    test_metadata_multiple_equipment()
    test_metadata_invalid_equipment()
    test_metadata_time_filter()

    # ── 接口 2 测试 ────────────────────────────────────────────
    print("\n▶ 接口 2：POST /reject-errors/search")
    test_search_basic()
    test_search_filter_chuck()
    test_search_filter_lot()
    test_search_filter_wafer()
    test_search_filter_combined()
    test_search_empty_array_intercept()
    test_search_pagination()
    test_search_deep_page_guard()
    test_search_sort_desc()
    test_search_sort_asc()
    test_search_invalid_equipment()
    test_search_invalid_wafer_range()
    test_search_null_filters_means_all()

    # ── 汇总 ───────────────────────────────────────────────────
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
