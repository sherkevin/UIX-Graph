import copy
import json
import logging
import os
from typing import Any, Dict, Optional

from app.engine.actions import has_action
from app.engine.condition_evaluator import _extract_vars_from_definition
from app.engine.rule_validator import validate_rules_config
from app.utils import detail_trace


logger = logging.getLogger(__name__)
SUPPORTED_INDEX_VERSIONS = {"3"}
SUPPORTED_PIPELINE_VERSIONS = {"3"}


def _get_config_dir() -> str:
    uix_root = os.environ.get("UIX_ROOT")
    if uix_root:
        return os.path.join(uix_root, "config")
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class DiagnosisConfigStore:
    """统一诊断配置存储（仅支持 structured pipeline）。"""

    _instance: Optional["DiagnosisConfigStore"] = None

    def __new__(cls) -> "DiagnosisConfigStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.config_dir = _get_config_dir()
        self.root_path = os.path.join(self.config_dir, "diagnosis.json")
        self.version = "unknown"
        self.pipeline_defs: Dict[str, Dict[str, Any]] = {}
        self.pipeline_cache: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        with open(self.root_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.version = data.get("version", "unknown")
        self._validate_version("diagnosis.json", self.version, SUPPORTED_INDEX_VERSIONS)
        self.pipeline_defs = data.get("pipelines", {}) or {}
        self.metrics_meta_notes = self._load_metrics_meta_notes()
        self.pipeline_cache = {}
        logger.info(
            "DiagnosisConfigStore loaded: version=%s pipelines=%s",
            self.version,
            ",".join(self.pipeline_defs.keys()),
        )
        detail_trace.info(
            "诊断索引已加载 | diagnosis.json version=%s | pipelines=%s | config_dir=%s",
            self.version,
            list(self.pipeline_defs.keys()),
            self.config_dir,
        )

    def get_pipeline(self, pipeline_id: str) -> Dict[str, Any]:
        if pipeline_id in self.pipeline_cache:
            return self.pipeline_cache[pipeline_id]
        pipeline_def = self.pipeline_defs.get(pipeline_id)
        if pipeline_def is None:
            raise KeyError(f"未知诊断 pipeline: {pipeline_id}")
        bundle = self._normalize_pipeline(pipeline_id, pipeline_def)
        self.pipeline_cache[pipeline_id] = bundle
        detail_trace.info(
            "pipeline 装配完成 | id=%s | metrics=%s | scenes=%s | steps=%s",
            pipeline_id,
            len(bundle.get("metrics") or {}),
            len(bundle.get("diagnosis_scenes") or []),
            len(bundle.get("steps") or []),
        )
        return bundle

    def has_pipeline(self, pipeline_id: str) -> bool:
        return pipeline_id in self.pipeline_defs

    def list_pipelines(self):
        return list(self.pipeline_defs.keys())

    def _load_json_file(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_metrics_meta_notes(self) -> Dict[str, Dict[str, Any]]:
        path = os.path.join(self.config_dir, "metrics_meta.yaml")
        if not os.path.exists(path):
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        current_key: Optional[str] = None
        current_notes = []
        current_status: Optional[str] = None

        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and stripped.endswith(":"):
                    if current_key is not None:
                        result[current_key] = {"notes": current_notes}
                        if current_status is not None:
                            result[current_key]["status"] = current_status
                    current_key = stripped[:-1].strip().strip('"').strip("'")
                    current_notes = []
                    current_status = None
                    continue
                if current_key is None:
                    continue
                if stripped.startswith("status:"):
                    current_status = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                    continue
                if stripped.startswith("- "):
                    current_notes.append(stripped[2:].strip().strip('"').strip("'"))

        if current_key is not None:
            result[current_key] = {"notes": current_notes}
            if current_status is not None:
                result[current_key]["status"] = current_status
        return result

    def _normalize_pipeline(self, pipeline_id: str, pipeline_def: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(pipeline_def.get("mode", "structured")).strip().lower()
        if mode != "structured":
            raise ValueError(f"pipeline {pipeline_id} mode={mode} 不再受支持，仅允许 structured")

        if pipeline_def.get("config_file"):
            file_def = self._load_json_file(str(pipeline_def["config_file"]))
            merged_def = _deep_merge(file_def, {"mode": mode})
        else:
            merged_def = copy.deepcopy(pipeline_def)
        return self._normalize_structured_pipeline(pipeline_id, merged_def)

    def _normalize_structured_pipeline(self, pipeline_id: str, pipeline_def: Dict[str, Any]) -> Dict[str, Any]:
        pipeline_version = pipeline_def.get("version", self.version)
        self._validate_version(f"{pipeline_id}.diagnosis.json", pipeline_version, SUPPORTED_PIPELINE_VERSIONS)

        metrics = copy.deepcopy(pipeline_def.get("metrics", {}) or {})
        scenes = copy.deepcopy(pipeline_def.get("diagnosis_scenes", []) or [])
        steps = copy.deepcopy(pipeline_def.get("steps", []) or [])

        self._backfill_metrics_from_steps(metrics, steps)
        for metric_id, meta in metrics.items():
            meta.setdefault("id", metric_id)
            meta.setdefault("role", "diagnostic")
            meta.setdefault("source_kind", "intermediate")
            linking = meta.setdefault("linking", {})
            if isinstance(linking, dict):
                linking.setdefault("mode", "time_window_only")
                linking.setdefault("keys", [])
                linking.setdefault("filters", [])
            fallback = meta.setdefault("fallback", {})
            if isinstance(fallback, dict):
                fallback.setdefault("policy", "none")
            if metric_id in self.metrics_meta_notes:
                metrics[metric_id] = _deep_merge(meta, self.metrics_meta_notes[metric_id])

        validation_errors = validate_rules_config(
            {"diagnosis_scenes": scenes, "steps": steps},
            action_exists=has_action,
            metrics=metrics,
        )
        if validation_errors:
            raise ValueError(
                f"diagnosis pipeline {pipeline_id} 校验失败:\n- " + "\n- ".join(validation_errors)
            )

        return {
            "id": pipeline_id,
            "mode": "structured",
            "version": pipeline_version,
            "diagnosis_scenes": scenes,
            "steps": steps,
            "steps_map": {str(step.get("id")): step for step in steps if "id" in step},
            "metrics": metrics,
            "default_scene_id": next(
                (scene.get("id") for scene in scenes if scene.get("default")),
                None,
            ),
        }

    @staticmethod
    def _validate_version(filename: str, version: Any, supported_majors: set) -> None:
        raw = str(version or "").strip()
        if not raw:
            return
        major = raw.split(".", 1)[0]
        if major not in supported_majors:
            raise ValueError(
                f"{filename} version={raw} 不受支持，当前仅支持 major in {sorted(supported_majors)}"
            )

    @staticmethod
    def _backfill_metrics_from_steps(normalized_metrics: Dict[str, Dict[str, Any]], steps: Any) -> None:
        def ensure_metric(metric_id: Optional[str], role: str = "derived") -> None:
            if not metric_id:
                return
            normalized_metrics.setdefault(
                str(metric_id),
                {
                    "id": str(metric_id),
                    "role": role,
                    "source_kind": "intermediate",
                },
            )

        for step in steps or []:
            ensure_metric(step.get("metric_id"), "diagnostic")
            for param_name in ((step.get("params") or {}) if isinstance(step.get("params"), dict) else {}).keys():
                ensure_metric(param_name, "derived")
            for detail in step.get("details") or []:
                if not isinstance(detail, dict):
                    continue
                for param_name in (detail.get("params") or {}).keys():
                    ensure_metric(param_name, "derived")
                for output_name in (detail.get("results") or {}).keys():
                    ensure_metric(output_name, "derived")
            for branch in step.get("next") or []:
                if not isinstance(branch, dict):
                    continue
                for result_key in (branch.get("results") or {}).keys():
                    ensure_metric(result_key, "derived")
                for var_name in _extract_vars_from_definition(branch.get("condition")):
                    ensure_metric(var_name, "diagnostic")
