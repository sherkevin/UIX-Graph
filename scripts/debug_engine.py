"""Debug script to trace the diagnosis engine step by step"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'backend'))

import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(message)s')

from app.engine.rule_loader import RuleLoader
from app.engine.metric_fetcher import MetricFetcher
from app.engine.diagnosis_engine import DiagnosisEngine
from datetime import datetime

# Simulate source record for id=59
source_record = {
    "id": 59,
    "equipment": "SSB8000",
    "chuck_id": 1,
    "lot_id": 101,
    "wafer_id": 7,
    "wafer_product_start_time": datetime(2026, 1, 10, 8, 45, 0),
    "reject_reason": 6,
    "reject_reason_value": "COARSE_ALIGN_FAILED",
    "wafer_translation_x": 25.5,
    "wafer_translation_y": 3.2,
    "wafer_rotation": 150.0,
}

# Load rules
loader = RuleLoader()
scene = loader.get_scene_by_reject_reason(6)
print(f"\n=== Scene: {scene.get('id')} ===")
print(f"  start_node: {scene.get('start_node')}")
print(f"  metric_id: {scene.get('metric_id')}")

# Get all metric IDs
metric_ids = loader.get_all_scene_metric_ids(scene)
print(f"\n=== All metric IDs ({len(metric_ids)}): {metric_ids}")

# Fetch values
fetcher = MetricFetcher(
    equipment="SSB8000",
    reference_time=datetime(2026, 1, 10, 8, 45, 0),
    chuck_id=1,
    fallback_duration_minutes=5,
)
metric_values = fetcher.fetch_from_source_record(source_record, metric_ids)
print(f"\n=== Metric Values ===")
for k, v in sorted(metric_values.items()):
    print(f"  {k}: {v}")

# Run diagnosis
engine = DiagnosisEngine(time_window_minutes=5)
result = engine.diagnose(source_record)
print(f"\n=== Diagnosis Result ===")
print(f"  rootCause: {result.root_cause}")
print(f"  system: {result.system}")
print(f"  errorField: {result.error_field}")
print(f"  trace: {result.trace}")
print(f"  is_diagnosed: {result.is_diagnosed}")
print(f"  metrics count: {len(result.metrics)}")
for m in result.metrics:
    print(f"    {m['name']}: {m['value']} {m['unit']} [{m['status']}] threshold={m['threshold']}")
