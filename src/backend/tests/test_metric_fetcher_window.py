"""
MetricFetcher 按指标 duration 计算时间窗（无需数据库）
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.engine.metric_fetcher import MetricFetcher


def test_window_uses_duration_from_meta():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_minutes=5,
    )
    start, end = f.window_for_metric({"duration": "1000"})
    assert end == T
    assert start == T - timedelta(minutes=1000)


def test_window_fallback_when_no_duration():
    T = datetime(2026, 3, 25, 12, 0, 0)
    f = MetricFetcher(
        equipment="SSB8000",
        reference_time=T,
        fallback_duration_minutes=7,
    )
    start, end = f.window_for_metric({})
    assert end == T
    assert start == T - timedelta(minutes=7)


if __name__ == "__main__":
    test_window_uses_duration_from_meta()
    test_window_fallback_when_no_duration()
    print("OK: test_metric_fetcher_window")
