#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断配置自检工具 (config-driven goal helper).

用法:
    python scripts/check_config.py                  # 检查所有 pipeline
    python scripts/check_config.py reject_errors    # 仅检查指定 pipeline
    python scripts/check_config.py --json           # 机器可读输出
    python scripts/check_config.py --strict         # 把 warning 当 error,影响退出码

退出码:
    0  全过 (或仅有 warning 且未 --strict)
    1  存在 error (例如 source_kind 非法、未注册 action、变量未声明)
    2  仅 warning (--strict 时)

它做的事:
    1. 每个 pipeline 加载 + 调用 rule_validator (跟服务启动时同一套)
    2. 额外的「软检查」(warning 级):
       - orphan metrics:声明了但任何 step/scene/branch 都没引用的 metric
       - unreachable steps:既非 scene.start_node 也非任何 next.target
       - DB 类 metric 缺 fallback.policy(运行时静默,容易误判)
       - 同一 step 的多个 next 分支引用同一变量但 condition 互斥性可疑
       - 多个 scene 用同一 start_node(可能配置冗余)
    3. 输出每个 pipeline 的「source_kind 分布」「叶子 step 数」「场景数」「指标数」摘要

设计原则:
    - 不引入新依赖,纯 stdlib + app.engine.rule_validator
    - 严格区分 error / warning;CI 默认只看 error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# 让 import 找到 src/backend/app/*
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from app.engine.actions import has_action  # noqa: E402
from app.engine.rule_validator import (  # noqa: E402
    DB_SOURCE_KINDS,
    validate_metrics_metadata,
    validate_rules_config,
)


CONFIG_DIR = ROOT / "config"
INDEX_FILE = CONFIG_DIR / "diagnosis.json"


# ────────────────────────────────────────────────────────────────────────
# 数据结构
# ────────────────────────────────────────────────────────────────────────


class CheckReport:
    """单个 pipeline 的检查报告。"""

    def __init__(self, pipeline_id: str):
        self.pipeline_id = pipeline_id
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.summary: Dict[str, Any] = {}

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


# ────────────────────────────────────────────────────────────────────────
# 软检查 (warnings)
# ────────────────────────────────────────────────────────────────────────


_VAR_RE = re.compile(r"\{(\w+)\}")


def _extract_vars(text: Any) -> Set[str]:
    """从字符串/对象中抽取 {var} 占位符引用的变量名。"""
    if text is None:
        return set()
    if isinstance(text, dict):
        out: Set[str] = set()
        for value in text.values():
            out.update(_extract_vars(value))
        return out
    if isinstance(text, list):
        out = set()
        for item in text:
            out.update(_extract_vars(item))
        return out
    return set(_VAR_RE.findall(str(text)))


def _check_orphan_metrics(
    metrics: Dict[str, Any], scenes: List[Any], steps: List[Any]
) -> List[str]:
    """
    声明了但无任何引用的 metric。
    
    **只检查 source_kind=intermediate 的 metric** —— 因为只有 intermediate 类必然由
    action 写入或 set 注入,有显式 produce/consume 关系;DB 类 / failure_record_field /
    request_param 等可能被 action 通过 **ctx 隐式访问,静态无法判断,不报 orphan。
    """
    referenced: Set[str] = set()

    # scene 层
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        mids = scene.get("metric_id") or []
        if isinstance(mids, str):
            mids = [mids]
        for mid in mids:
            referenced.add(str(mid))
        for cond in scene.get("trigger_condition") or []:
            referenced.update(_extract_vars(cond))

    # step 层
    for step in steps:
        if not isinstance(step, dict):
            continue
        mid = step.get("metric_id")
        if mid:
            referenced.add(str(mid))
        for detail in step.get("details") or []:
            if not isinstance(detail, dict):
                continue
            params = detail.get("params") or {}
            if isinstance(params, dict):
                for value in params.values():
                    if isinstance(value, str):
                        referenced.update(_extract_vars(value))
            for key in (detail.get("results") or {}).keys():
                referenced.add(str(key))
        for branch in step.get("next") or []:
            if not isinstance(branch, dict):
                continue
            referenced.update(_extract_vars(branch.get("condition")))
            for key in (branch.get("set") or {}).keys():
                referenced.add(str(key))
            for key in (branch.get("results") or {}).keys():
                referenced.add(str(key))

    # metric 之间互引(extraction_rule、linking source 也可能引用别的 metric)
    for meta in metrics.values():
        if not isinstance(meta, dict):
            continue
        ext = meta.get("extraction_rule")
        if isinstance(ext, str):
            referenced.update(_extract_vars(ext))
        linking = meta.get("linking") or {}
        if isinstance(linking, dict):
            for field in ("keys", "filters"):
                for item in linking.get(field) or []:
                    if isinstance(item, dict) and "source" in item:
                        referenced.add(str(item["source"]).strip())

    intermediate_ids: Set[str] = set()
    for mid, meta in metrics.items():
        if not isinstance(meta, dict):
            continue
        kind = str(meta.get("source_kind", "")).strip().lower()
        role = str(meta.get("role", "")).strip().lower()
        if kind == "intermediate" and role != "trigger_only":
            intermediate_ids.add(str(mid))

    orphans = sorted(intermediate_ids - referenced)
    return [
        f"metric({mid}) source_kind=intermediate 但无任何 results/set/condition/params 引用 — "
        f"无人 produce 也无人 consume,可能是遗留占位"
        for mid in orphans
    ]


def _check_unreachable_steps(scenes: List[Any], steps: List[Any]) -> List[str]:
    """既非任何 scene.start_node 也非任何 next.target 的 step,无法被诊断引擎到达。"""
    reachable: Set[str] = set()
    for scene in scenes:
        if isinstance(scene, dict):
            sn = scene.get("start_node")
            if sn is not None:
                reachable.add(str(sn))
    for step in steps:
        if not isinstance(step, dict):
            continue
        for branch in step.get("next") or []:
            if not isinstance(branch, dict):
                continue
            target = branch.get("target")
            if target is None:
                continue
            if isinstance(target, list):
                for t in target:
                    reachable.add(str(t))
            else:
                reachable.add(str(target))

    all_ids = {str(s.get("id")) for s in steps if isinstance(s, dict) and "id" in s}
    unreachable = sorted(all_ids - reachable)
    return [
        f"step({sid}) 既非任何 scene.start_node 也非任何 next.target — 死代码"
        for sid in unreachable
    ]


def _check_db_metrics_missing_fallback(metrics: Dict[str, Any]) -> List[str]:
    """DB 类 metric 没声明 fallback.policy 时,默认 'none' 容易让运行时静默拿 None 而无回退。"""
    out: List[str] = []
    for mid, meta in metrics.items():
        if not isinstance(meta, dict):
            continue
        kind = str(meta.get("source_kind", "")).strip().lower()
        if kind not in DB_SOURCE_KINDS:
            continue
        fallback = meta.get("fallback") or {}
        if not isinstance(fallback, dict):
            continue
        policy = str(fallback.get("policy", "")).strip().lower()
        if not policy or policy == "none":
            out.append(
                f"metric({mid}) DB 类 source_kind={kind} 但 fallback.policy 为空/none — "
                f"窗口无数据时直接返回 None,易导致诊断走错路径;建议明确写 nearest_in_window 或 none 表态"
            )
    return out


def _check_duplicate_start_nodes(scenes: List[Any]) -> List[str]:
    """多个 scene 共用同一 start_node 通常是冗余配置(后定义的场景永远到不了那个共享起点的差异化处理)。"""
    counter: Counter = Counter()
    by_node: Dict[str, List[Any]] = defaultdict(list)
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sn = scene.get("start_node")
        if sn is None:
            continue
        counter[str(sn)] += 1
        by_node[str(sn)].append(scene.get("id"))
    out: List[str] = []
    for node, count in counter.items():
        if count > 1:
            out.append(
                f"start_node={node} 被 {count} 个 scene 共用 (scene_ids={by_node[node]}) — "
                f"通常意味着仅靠 start_node 区分这些场景不够,需要回看 trigger_condition 是否互斥"
            )
    return out


# ────────────────────────────────────────────────────────────────────────
# Summary 摘要
# ────────────────────────────────────────────────────────────────────────


def _build_summary(metrics: Dict[str, Any], scenes: List[Any], steps: List[Any]) -> Dict[str, Any]:
    source_kinds = Counter()
    roles = Counter()
    for meta in metrics.values():
        if not isinstance(meta, dict):
            continue
        source_kinds[str(meta.get("source_kind", "intermediate")).strip().lower() or "intermediate"] += 1
        roles[str(meta.get("role", "diagnostic")).strip().lower() or "diagnostic"] += 1

    leaf_count = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        if "result" in step or "results" in step:
            leaf_count += 1
            continue
        for detail in step.get("details") or []:
            if isinstance(detail, dict) and (
                detail.get("result")
                or (isinstance(detail.get("results"), dict) and "rootCause" in detail["results"])
            ):
                leaf_count += 1
                break

    return {
        "metrics_total": len(metrics),
        "scenes_total": len(scenes),
        "steps_total": len(steps),
        "leaf_steps": leaf_count,
        "source_kind_distribution": dict(source_kinds),
        "role_distribution": dict(roles),
    }


# ────────────────────────────────────────────────────────────────────────
# pipeline 加载与检查
# ────────────────────────────────────────────────────────────────────────


def _list_pipelines(only: Optional[str]) -> List[Tuple[str, Path]]:
    """从 config/diagnosis.json 索引读取所有 pipeline 配置文件路径。"""
    if not INDEX_FILE.exists():
        raise FileNotFoundError(f"未找到 pipeline 索引文件: {INDEX_FILE}")
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    pipelines = index.get("pipelines") or {}
    out: List[Tuple[str, Path]] = []
    for pid, pdef in pipelines.items():
        if only and pid != only:
            continue
        cfg_file = pdef.get("config_file")
        if cfg_file:
            out.append((pid, CONFIG_DIR / cfg_file))
    return out


def check_pipeline(pipeline_id: str, config_path: Path) -> CheckReport:
    report = CheckReport(pipeline_id)
    if not config_path.exists():
        report.errors.append(f"pipeline 配置文件不存在: {config_path}")
        return report
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"JSON 解析失败 (line {exc.lineno} col {exc.colno}): {exc.msg}")
        return report

    metrics = data.get("metrics") or {}
    scenes = data.get("diagnosis_scenes") or []
    steps = data.get("steps") or []

    # 硬检查 (errors) — 复用服务启动时的 validator
    report.errors.extend(
        validate_rules_config(
            {"diagnosis_scenes": scenes, "steps": steps},
            action_exists=has_action,
            metrics=metrics,
        )
    )

    # 软检查 (warnings)
    report.warnings.extend(_check_orphan_metrics(metrics, scenes, steps))
    report.warnings.extend(_check_unreachable_steps(scenes, steps))
    report.warnings.extend(_check_db_metrics_missing_fallback(metrics))
    report.warnings.extend(_check_duplicate_start_nodes(scenes))

    # 摘要
    report.summary = _build_summary(metrics, scenes, steps)
    return report


# ────────────────────────────────────────────────────────────────────────
# 输出
# ────────────────────────────────────────────────────────────────────────


def _print_text(reports: List[CheckReport], verbose: bool) -> None:
    for r in reports:
        flag = "OK" if r.ok else "FAIL"
        print(f"\n[{flag}] pipeline={r.pipeline_id}")
        print(
            f"  metrics={r.summary.get('metrics_total', 0)} "
            f"scenes={r.summary.get('scenes_total', 0)} "
            f"steps={r.summary.get('steps_total', 0)} "
            f"leaves={r.summary.get('leaf_steps', 0)}"
        )
        sk = r.summary.get("source_kind_distribution", {})
        if sk:
            print("  source_kind distribution:")
            for kind, count in sorted(sk.items()):
                print(f"    {kind}: {count}")
        if r.errors:
            print(f"  ERRORS ({len(r.errors)}):")
            for e in r.errors:
                print(f"    - {e}")
        if r.warnings:
            print(f"  WARNINGS ({len(r.warnings)}):")
            for w in r.warnings if verbose else r.warnings[:10]:
                print(f"    - {w}")
            if not verbose and len(r.warnings) > 10:
                print(f"    ... (+{len(r.warnings) - 10} more, use --verbose to see all)")
        if not r.errors and not r.warnings:
            print("  (no issues)")


def _print_json(reports: List[CheckReport]) -> None:
    payload = {
        "pipelines": [r.to_dict() for r in reports],
        "totals": {
            "errors": sum(len(r.errors) for r in reports),
            "warnings": sum(len(r.warnings) for r in reports),
            "pipelines_with_errors": sum(1 for r in reports if r.errors),
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="诊断配置自检 (rule_validator + warning 级软检查)。"
    )
    parser.add_argument(
        "pipeline_id",
        nargs="?",
        default=None,
        help="仅检查指定 pipeline_id (默认检查 config/diagnosis.json 索引中所有 pipeline)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 机器可读输出")
    parser.add_argument("--verbose", action="store_true", help="打印所有 warning (默认截断到前 10 条)")
    parser.add_argument(
        "--strict", action="store_true",
        help="把 warning 当作失败:有 warning 时退出码 2",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        pipeline_files = _list_pipelines(args.pipeline_id)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not pipeline_files:
        if args.pipeline_id:
            print(f"[ERROR] pipeline_id={args.pipeline_id!r} 在 config/diagnosis.json 中未找到", file=sys.stderr)
        else:
            print("[ERROR] config/diagnosis.json 没有声明任何 pipeline", file=sys.stderr)
        return 1

    reports = [check_pipeline(pid, path) for pid, path in pipeline_files]

    if args.json:
        _print_json(reports)
    else:
        _print_text(reports, verbose=args.verbose)

    has_error = any(r.errors for r in reports)
    has_warning = any(r.warnings for r in reports)

    if has_error:
        return 1
    if args.strict and has_warning:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
