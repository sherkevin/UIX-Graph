"""
DOCKER_E2E=1 时扩展 HTTP 契约（需 docker compose MySQL 已 init）。

与 test_docker_seed_alignment 相同环境变量约定。
"""
import os

if os.environ.get("DOCKER_E2E") == "1":
    os.environ["METRIC_SOURCE_MODE"] = "real"
    os.environ.setdefault("APP_ENV", "local")

import pytest
import httpx

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCKER_E2E") != "1",
    reason="设置 DOCKER_E2E=1 且 MySQL 就绪后运行",
)


@pytest.fixture(scope="module")
def client():
    c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)
    try:
        yield c
    finally:
        c.close()


def test_metadata_rejects_unknown_equipment(client):
    r = client.get("/api/v1/reject-errors/metadata", params={"equipment": "NOT_A_REAL_TOOL"})
    assert r.status_code == 400


def test_search_empty_chucks_returns_empty(client):
    r = client.post(
        "/api/v1/reject-errors/search",
        json={
            "pageNo": 1,
            "pageSize": 20,
            "equipment": "SSB8000",
            "chucks": [],
            "startTime": 1704067200000,
            "endTime": 1893484800000,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] == 0
    assert body["data"] == []


def test_metrics_includes_diagnostic_and_model_param_meta(client):
    from app.models.reject_errors_db import LoBatchEquipmentPerformance, get_db_session

    db = get_db_session()
    try:
        rows = (
            db.query(LoBatchEquipmentPerformance)
            .filter(
                LoBatchEquipmentPerformance.equipment == "SSB8000",
                LoBatchEquipmentPerformance.reject_reason == 6,
            )
            .all()
        )
        fid = None
        for row in rows:
            if str(row.chuck_id) == "1" and str(row.lot_id) == "101" and str(row.wafer_index) == "7":
                fid = row.id
                break
    finally:
        db.close()
    if fid is None:
        pytest.skip("锚点故障不存在")

    r = client.get(f"/api/v1/reject-errors/{fid}/metrics", params={"pageNo": 1, "pageSize": 20})
    assert r.status_code == 200
    body = r.json()
    meta = body["meta"]
    assert "metricDiagnosticTotal" in meta
    assert "metricModelParamTotal" in meta
    assert meta["metricDiagnosticTotal"] + meta["metricModelParamTotal"] == meta["total"]
    if meta["metricDiagnosticTotal"] > 0:
        assert meta["totalPages"] == (meta["metricDiagnosticTotal"] + 19) // 20
