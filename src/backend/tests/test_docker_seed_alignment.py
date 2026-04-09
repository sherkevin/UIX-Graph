"""
Docker 种子数据与接口 3 指标对齐（可选集成测试）。

设置 DOCKER_E2E=1 且 docker compose 已启动、MySQL/CH 已 init 后运行；
并设置 METRIC_SOURCE_MODE=real（本模块在 import app 前写入）。
"""
import os

if os.environ.get("DOCKER_E2E") == "1":
    os.environ["METRIC_SOURCE_MODE"] = "real"
    os.environ.setdefault("APP_ENV", "local")

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCKER_E2E") != "1",
    reason="仅在本机已 docker compose up 且需联调时设置 DOCKER_E2E=1",
)


def _anchor_failure_id():
    from app.models.reject_errors_db import LoBatchEquipmentPerformance, get_db_session

    db = get_db_session()
    try:
        rows = (
            db.query(LoBatchEquipmentPerformance)
            .filter(
                LoBatchEquipmentPerformance.equipment == "SSB8000",
                LoBatchEquipmentPerformance.reject_reason == 6,
            )
            .order_by(LoBatchEquipmentPerformance.id.desc())
            .all()
        )
        for row in rows:
            if str(row.chuck_id) == "1" and str(row.lot_id) == "101" and str(row.wafer_index) == "7":
                return row.id
        return None
    finally:
        db.close()


def test_anchor_failure_row_exists():
    fid = _anchor_failure_id()
    assert fid is not None, "未找到锚点行：请确认已执行 scripts/init_docker_db.sql"


def test_failure_details_metrics_match_seeded_clickhouse_and_mysql():
    from app.service.reject_error_service import RejectErrorService

    fid = _anchor_failure_id()
    assert fid is not None

    record = None
    from app.models.reject_errors_db import LoBatchEquipmentPerformance, get_db_session

    db = get_db_session()
    try:
        record = db.query(LoBatchEquipmentPerformance).filter(LoBatchEquipmentPerformance.id == fid).first()
    finally:
        db.close()
    assert record is not None
    request_time_ms = int(record.wafer_product_start_time.timestamp() * 1000)

    detail, meta = RejectErrorService.get_failure_details(
        fid, page_no=1, page_size=100, request_time_ms=request_time_ms
    )
    assert detail is not None
    assert detail.get("failureId") == fid
    by_name = {m["name"]: m["value"] for m in detail.get("metrics", [])}

    assert pytest.approx(by_name.get("Mwx_0"), rel=1e-5) == 1.00003
    assert pytest.approx(float(by_name.get("ws_pos_x")), rel=1e-5) == 0.11
    assert pytest.approx(float(by_name.get("ws_pos_y")), rel=1e-5) == -0.22
    assert pytest.approx(float(by_name.get("mark_pos_x")), rel=1e-5) == 0.055
    assert pytest.approx(float(by_name.get("mark_pos_y")), rel=1e-5) == -0.063
    assert pytest.approx(float(by_name.get("Msx")), rel=1e-5) == 1.00005
    assert pytest.approx(float(by_name.get("Msy")), rel=1e-5) == 0.99996
    assert pytest.approx(float(by_name.get("e_ws_x")), rel=1e-5) == -1.15
    assert pytest.approx(float(by_name.get("e_ws_y")), rel=1e-5) == 2.34
    assert pytest.approx(float(by_name.get("Sx")), rel=1e-5) == 0.001234
    assert pytest.approx(float(by_name.get("Sy")), rel=1e-5) == -0.005678

    assert meta.get("total", 0) >= 10
    assert meta.get("metricDiagnosticTotal") is not None
    assert meta.get("metricModelParamTotal") is not None
    assert meta["metricDiagnosticTotal"] + meta["metricModelParamTotal"] == meta["total"]
