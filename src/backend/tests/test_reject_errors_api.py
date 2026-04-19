"""
拒片故障管理模块 - HTTP 层契约测试（使用 FastAPI TestClient）
覆盖接口 1/2/3 的 HTTP 状态码、响应结构契约、参数校验。

运行方式:
    cd src/backend
    pip install httpx  # TestClient 依赖
    python -m pytest tests/test_reject_errors_api.py -v
    # 或直接：
    python tests/test_reject_errors_api.py

依赖 MySQL（通过 config/connections.json local 配置）。
"""
import asyncio
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx
from app.main import app


class SyncASGIClient:
    """兼容新版本 httpx.ASGITransport（仅提供本测试需要的 get/post）。"""

    def __init__(self, app, base_url="http://testserver"):
        self.app = app
        self.base_url = base_url

    async def _request_async(self, method, url, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
            return await client.request(method, url, **kwargs)

    def request(self, method, url, **kwargs):
        return asyncio.run(self._request_async(method, url, **kwargs))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


client = SyncASGIClient(app)

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_true(label, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"    ✅ {label}{(' — ' + str(detail)) if detail else ''}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}{(' — ' + str(detail)) if detail else ''}")
        FAIL_COUNT += 1


def assert_eq(label, actual, expected):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        print(f"    ✅ {label}: {actual!r}")
        PASS_COUNT += 1
    else:
        print(f"    ❌ {label}: 期望 {expected!r}，实际 {actual!r}")
        FAIL_COUNT += 1


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════════════════════

def test_health():
    section("健康检查 GET /health")
    resp = client.get("/health")
    assert_eq("HTTP 200", resp.status_code, 200)
    assert_true("status=healthy", resp.json().get("status") == "healthy")


# ═══════════════════════════════════════════════════════════════════════════
# 接口 1 HTTP 层
# ═══════════════════════════════════════════════════════════════════════════

def test_api_metadata_200():
    section("接口1 HTTP - 正常请求 200")
    resp = client.get("/api/v1/reject-errors/metadata", params={"equipment": "SSB8000"})
    assert_eq("HTTP 200", resp.status_code, 200)
    body = resp.json()
    assert_true("返回 data 字段", "data" in body)
    assert_true("data 是列表", isinstance(body["data"], list))


def test_api_metadata_400_invalid_equipment():
    section("接口1 HTTP - 非法机台 → 400")
    resp = client.get("/api/v1/reject-errors/metadata", params={"equipment": "INVALID_MACHINE"})
    assert_eq("HTTP 400", resp.status_code, 400)
    assert_true("返回 detail", "detail" in resp.json())


def test_api_metadata_400_missing_equipment():
    section("接口1 HTTP - 缺少 equipment 参数 → 422")
    resp = client.get("/api/v1/reject-errors/metadata")
    # FastAPI 参数缺失返回 422 Unprocessable Entity
    assert_true("HTTP 422", resp.status_code == 422, str(resp.status_code))


# ═══════════════════════════════════════════════════════════════════════════
# 接口 2 HTTP 层
# ═══════════════════════════════════════════════════════════════════════════

def test_api_search_200():
    section("接口2 HTTP - 正常请求 200")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1,
        "pageSize": 10,
        "equipment": "SSB8000",
    })
    assert_eq("HTTP 200", resp.status_code, 200)
    body = resp.json()
    assert_true("返回 data 字段", "data" in body)
    assert_true("返回 meta 字段", "meta" in body)
    meta = body["meta"]
    for f in ["total", "pageNo", "pageSize", "totalPages"]:
        assert_true(f"meta.{f} 存在", f in meta)


def test_api_search_400_invalid_equipment():
    section("接口2 HTTP - 非法机台 → 400")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 10, "equipment": "BAD_MACHINE"
    })
    assert_eq("HTTP 400", resp.status_code, 400)


def test_api_search_empty_array():
    section("接口2 HTTP - chucks=[] 返回空结果 200")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 10, "equipment": "SSB8000", "chucks": []
    })
    assert_eq("HTTP 200", resp.status_code, 200)
    body = resp.json()
    assert_eq("data=[]", body.get("data"), [])
    assert_eq("meta.total=0", body["meta"]["total"], 0)


def test_api_search_invalid_wafer():
    section("接口2 HTTP - wafer_id=99 超出范围 → 400")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 10, "equipment": "SSB8000", "wafers": [99]
    })
    assert_eq("HTTP 400", resp.status_code, 400)


def test_api_search_record_fields():
    section("接口2 HTTP - 记录字段完整性")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 5, "equipment": "SSB8000"
    })
    assert_eq("HTTP 200", resp.status_code, 200)
    records = resp.json().get("data", [])
    if records:
        rec = records[0]
        for field in ["id", "failureId", "chuckId", "lotId", "waferIndex",
                      "rejectReason", "rejectReasonId", "time"]:
            assert_true(f"字段 '{field}' 存在", field in rec)
        assert_true("time 为 13 位", len(str(rec["time"])) == 13, str(rec["time"]))


# ═══════════════════════════════════════════════════════════════════════════
# 接口 3 HTTP 层
# ═══════════════════════════════════════════════════════════════════════════

def test_api_metrics_404():
    section("接口3 HTTP - 不存在 ID → 404")
    resp = client.get("/api/v1/reject-errors/999999999/metrics")
    assert_eq("HTTP 404", resp.status_code, 404)
    assert_true("detail 字段存在", "detail" in resp.json())


def test_api_metrics_400_invalid_request_time():
    section("接口3 HTTP - requestTime=0（极小值）→ 400")
    resp = client.get("/api/v1/reject-errors/1/metrics", params={"requestTime": 0})
    assert_eq("HTTP 400", resp.status_code, 400)


def test_api_metrics_400_request_time_too_large():
    section("接口3 HTTP - requestTime 极大值 → 400")
    resp = client.get("/api/v1/reject-errors/1/metrics", params={"requestTime": 9_999_999_999_999_999})
    assert_eq("HTTP 400", resp.status_code, 400)


def _get_first_failure_id() -> int:
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 1, "equipment": "SSB8000"
    })
    records = resp.json().get("data", [])
    if not records:
        raise RuntimeError("无测试数据")
    return records[0]["id"]


def _get_first_coarse_failure():
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 50, "equipment": "SSB8000"
    })
    records = resp.json().get("data", [])
    coarse = [r for r in records if r.get("rejectReasonId") == 6]
    if not coarse:
        raise RuntimeError("无 COARSE_ALIGN_FAILED 测试数据")
    return coarse[0]


def test_api_metrics_200():
    section("接口3 HTTP - 正常请求 200")
    fid = _get_first_failure_id()
    resp = client.get(f"/api/v1/reject-errors/{fid}/metrics")
    assert_eq("HTTP 200", resp.status_code, 200)
    body = resp.json()
    assert_true("返回 data 字段", "data" in body)
    assert_true("返回 meta 字段", "meta" in body)
    data = body["data"]
    for field in ["failureId", "rejectReason", "rejectReasonId", "time", "metrics"]:
        assert_true(f"data.{field} 存在", field in data)
    assert_true("data.metrics 是列表", isinstance(data["metrics"], list))


def test_api_metrics_response_structure():
    section("接口3 HTTP - 指标字段结构完整性")
    fid = _get_first_failure_id()

    # 找 COARSE_ALIGN_FAILED 记录
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 50, "equipment": "SSB8000"
    })
    records = resp.json().get("data", [])
    coarse = [r for r in records if r.get("rejectReasonId") == 6]
    if not coarse:
        print("    ⚠️  无 COARSE_ALIGN_FAILED 记录，跳过指标结构验证")
        return

    fid = coarse[0]["id"]
    resp = client.get(f"/api/v1/reject-errors/{fid}/metrics")
    assert_eq("HTTP 200", resp.status_code, 200)
    metrics = resp.json()["data"].get("metrics", [])
    if metrics:
        m = metrics[0]
        for field in ["name", "value", "unit", "status", "threshold"]:
            assert_true(f"指标字段 '{field}' 存在", field in m)
        assert_true("status 为 NORMAL 或 ABNORMAL",
                    m["status"] in ("NORMAL", "ABNORMAL"), m["status"])
        assert_true("threshold.operator 存在", "operator" in m["threshold"])
        assert_true("threshold.limit 存在", "limit" in m["threshold"])


def test_api_metrics_abnormal_first():
    section("接口3 HTTP - ABNORMAL 指标排在最前")
    resp = client.post("/api/v1/reject-errors/search", json={
        "pageNo": 1, "pageSize": 50, "equipment": "SSB8000"
    })
    records = resp.json().get("data", [])
    coarse = [r for r in records if r.get("rejectReasonId") == 6]
    if not coarse:
        print("    ⚠️  无 COARSE_ALIGN_FAILED 记录，跳过")
        return

    fid = coarse[0]["id"]
    resp = client.get(f"/api/v1/reject-errors/{fid}/metrics")
    metrics = resp.json()["data"].get("metrics", [])
    if len(metrics) < 2:
        print("    ⚠️  指标不足 2 条，跳过排序验证")
        return

    has_abnormal = any(m["status"] == "ABNORMAL" for m in metrics)
    if has_abnormal:
        first_abnormal_idx = next(i for i, m in enumerate(metrics) if m["status"] == "ABNORMAL")
        first_normal_idx_before = next(
            (i for i, m in enumerate(metrics[:first_abnormal_idx]) if m["status"] == "NORMAL"),
            -1
        )
        assert_eq("ABNORMAL 排在所有 NORMAL 之前", first_normal_idx_before, -1)
    else:
        print("    ⚠️  此记录无 ABNORMAL 指标，跳过排序验证")


def test_api_metrics_same_request_time_matches_cached_result():
    section("接口3 HTTP - requestTime 等于发生时间时复用缓存结果")
    record = _get_first_coarse_failure()
    fid = record["id"]
    occurred_ms = record["time"]

    # 先请求一次默认详情，确保缓存已准备好
    baseline = client.get(f"/api/v1/reject-errors/{fid}/metrics")
    assert_eq("baseline HTTP 200", baseline.status_code, 200)

    same_time = client.get(
        f"/api/v1/reject-errors/{fid}/metrics",
        params={"requestTime": occurred_ms}
    )
    assert_eq("same-time HTTP 200", same_time.status_code, 200)

    baseline_body = baseline.json()
    same_time_body = same_time.json()
    assert_eq("rootCause 一致",
              same_time_body["data"].get("rootCause"),
              baseline_body["data"].get("rootCause"))
    assert_eq("system 一致",
              same_time_body["data"].get("system"),
              baseline_body["data"].get("system"))
    assert_eq("指标总数一致",
              same_time_body["meta"].get("total"),
              baseline_body["meta"].get("total"))


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global PASS_COUNT, FAIL_COUNT
    PASS_COUNT = 0
    FAIL_COUNT = 0

    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  HTTP 层契约测试（TestClient）".center(56) + "  █")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    test_health()

    print("\n▶ 接口 1")
    test_api_metadata_200()
    test_api_metadata_400_invalid_equipment()
    test_api_metadata_400_missing_equipment()

    print("\n▶ 接口 2")
    test_api_search_200()
    test_api_search_400_invalid_equipment()
    test_api_search_empty_array()
    test_api_search_invalid_wafer()
    test_api_search_record_fields()

    print("\n▶ 接口 3")
    test_api_metrics_404()
    test_api_metrics_400_invalid_request_time()
    test_api_metrics_400_request_time_too_large()
    test_api_metrics_200()
    test_api_metrics_response_structure()
    test_api_metrics_abnormal_first()
    test_api_metrics_same_request_time_matches_cached_result()

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
