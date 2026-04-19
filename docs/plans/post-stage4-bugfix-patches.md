# Stage4 落地后待 apply 的 bug 修复 patch

> ## ✅ 全部已 apply(2026-04-19,K1–K7,共 7 笔 commit)
>
> stage4 wip 已 commit `13cf121`,本文档计划的 7 个 bug 已全部修复并通过 190 个非 DB 测试:
>
> | Bug | Commit | 测试 |
> |-----|--------|------|
> | #1 jsonpath name[N] | `5e9d274` | +6 |
> | #2 EQUIPMENT_WHITELIST 配置化 | `56beaae` | +8 |
> | #3 _METRIC_ALIAS_MAP → metric.alias_of | `e6d97b5` | +5 |
> | #4 rejected_detailed_records.config_version 失效 | `94f5280` | +8 |
> | #5 删 legacy_ranges/_mock_intermediate_value 改为 mock_value/mock_range | `741702e` | +5 |
> | #6 max_steps 截断专门日志 | `44ef155` | (纯日志增强) |
> | #7 _render_extraction_template list 边界 | `f376c27` | +4 |
>
> **共 +36 个测试**,零回归。`python scripts/check_config.py` 仍 [OK]。
>
> 本文档保留作为历史档案,记录每个 bug 的设计决策与 patch 思路。

---

## 历史触发条件

> ~~你 commit 完当前 stage4 in-progress 的 25 个 modified + 4 个 untracked 改动后,本文档里的 patch 就可以 apply。~~
>
> ~~**为什么不能现在 apply**:这 6 个 bug 都位于你 stage4 改动的代码区域...~~
>
> 已不适用。stage4 wip 已 `13cf121` commit,所有 patch 已 apply。

---

## 总览(优先级与依赖)

| # | Bug | 文件 | 工作量 | 优先级 | 依赖 |
|---|-----|------|--------|--------|------|
| 1 | jsonpath `name[N]` segment 不识别 | [`engine/metric_fetcher.py`](../../src/backend/app/engine/metric_fetcher.py) | 10 行 + 6 测试 | **P0** | stage4 落地 |
| 2 | `EQUIPMENT_WHITELIST` 硬编码 | [`service/reject_error_service.py`](../../src/backend/app/service/reject_error_service.py) | 15 行 + 5 测试 | **P0** | stage4 落地;基础设施 [`config/equipments.json`](../../config/equipments.json) 已就绪 |
| 3 | `_METRIC_ALIAS_MAP` 硬编码 | [`engine/diagnosis_engine.py`](../../src/backend/app/engine/diagnosis_engine.py) | 20 行 | **P1** | stage4 落地 |
| 4 | 缓存表无 `config_version` 列 | [`models/reject_errors_db.py`](../../src/backend/app/models/reject_errors_db.py) + [`service/reject_error_service.py`](../../src/backend/app/service/reject_error_service.py) + [`scripts/init_docker_db.sql`](../../scripts/init_docker_db.sql) | 40 行 + 3 测试 | **P1** | stage4 落地(service 部分);model/SQL 部分**现在就可独立做** |
| 5 | `_mock_intermediate_value` / `legacy_ranges` 硬编码 | [`engine/metric_fetcher.py`](../../src/backend/app/engine/metric_fetcher.py) | 30 行 | **P2** | stage4 落地 |
| 6 | `max_steps` 截断时日志不区分 | [`engine/diagnosis_engine.py`](../../src/backend/app/engine/diagnosis_engine.py) | 5 行 | **P3** | stage4 落地 |
| 7 | `_render_extraction_template` 模板 `{var}` 解析到 list 时拼错 | [`engine/metric_fetcher.py`](../../src/backend/app/engine/metric_fetcher.py) | 8 行 + 2 测试 | **P2** | stage4 落地 |

---

## Bug #1:jsonpath `name[N]` segment

### 问题

`config/reject_errors.diagnosis.json` 中 `Sx` / `Sy` 用了:

```json
"extraction_rule": "jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x"
```

`MetricFetcher._render_extraction_template` 渲染 `{chuck_index0}` 后变成 `chuck_message[0]`,按 `/` split 后第二段是 `"chuck_message[0]"` —— 既不是纯数字(无法走数组下标分支)也不是 dict key(因为内网真实 JSON 里 key 是 `chuck_message`)。**任何 jsonpath 配置带 `name[N]` 都跑不通**。

当前 commit F 的 mock 用 `"chuck_message[0]"` 字符串 key 作 hack 适配。

### 修复

在 `metric_fetcher._extract_json_path_value` 里加一个分支:如果 segment 形如 `name[N]`(`re.fullmatch(r"(\w+)\[(\d+)\]", segment)`),就先用 `name` 作 dict key 取出列表,再用 `N` 作下标。

### Patch(stage4 commit 后 apply)

文件:[`src/backend/app/engine/metric_fetcher.py`](../../src/backend/app/engine/metric_fetcher.py)

找 `_extract_json_path_value` 函数(stage4 中应在 ~L648),把内部循环改为:

```python
import re as _re  # 已在文件顶部 import

@staticmethod
def _extract_json_path_value(data: Any, path: str) -> Any:
    current = data
    name_idx_re = _re.compile(r"^(\w+)\[(\d+)\]$")
    for segment in [part for part in str(path or "").split("/") if part]:
        # 兼容 name[N] 形式:先 dict 查 name,再 list 取 N
        m = name_idx_re.match(segment)
        if m:
            key, idx_str = m.group(1), m.group(2)
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if not isinstance(current, list):
                return None
            idx = int(idx_str)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                return None
            index = int(segment)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current
```

### 同步改动

- [`scripts/init_docker_db.sql`](../../scripts/init_docker_db.sql) 里 `mc_config_commits_history` 的 `data` 字段改回**标准 nested array** 形式:

  ```json
  {"static_wafer_load_offset":{"chuck_message":[{"static_load_offset":{"x":0.001234,"y":-0.005678}},{"static_load_offset":{"x":0.002000,"y":-0.003000}}]}}
  ```

- [`docs/intranet/databases/mysql_datacenter.md`](../intranet/databases/mysql_datacenter.md) §mc_config_commits_history 的「⚠ 已知 issue」段改为「已修复(name[N] 与 name/N 两种 jsonpath 写法都支持)」

### 测试

新增 6 个测试到 [`src/backend/tests/test_metric_fetcher_window.py`](../../src/backend/tests/test_metric_fetcher_window.py):

```python
def test_extract_json_path_supports_name_bracket_index():
    fetcher = ...
    data = {"chuck_message": [{"x": 1}, {"x": 2}]}
    assert fetcher._extract_json_path_value(data, "chuck_message[0]/x") == 1
    assert fetcher._extract_json_path_value(data, "chuck_message[1]/x") == 2

def test_extract_json_path_name_bracket_out_of_range_returns_none():
    fetcher = ...
    data = {"chuck_message": [{"x": 1}]}
    assert fetcher._extract_json_path_value(data, "chuck_message[5]/x") is None

def test_extract_json_path_old_slash_index_still_works():
    """向后兼容:name/N 写法仍然有效。"""
    fetcher = ...
    data = {"chuck_message": [{"x": 1}, {"x": 2}]}
    assert fetcher._extract_json_path_value(data, "chuck_message/0/x") == 1
```

---

## Bug #2:EQUIPMENT_WHITELIST 配置化

### 问题

```python
# src/backend/app/service/reject_error_service.py:36-39
EQUIPMENT_WHITELIST = [
    "SSB8000", "SSB8001", "SSB8002", "SSB8005",
    "SSC8001", "SSC8002", "SSC8003", "SSC8004", "SSC8005", "SSC8006"
]
```

加机台必须改 Python 代码 → 违反"配置驱动"原则。

### 修复

[`config/equipments.json`](../../config/equipments.json) 已 commit J 中创建好,可直接读取。

### Patch

文件:[`src/backend/app/service/reject_error_service.py`](../../src/backend/app/service/reject_error_service.py)

```python
import json
import os
from pathlib import Path
from threading import Lock

class RejectErrorService:
    _equipments_cache: Optional[List[str]] = None
    _equipments_lock = Lock()

    @classmethod
    def _load_equipments(cls) -> List[str]:
        """从 config/equipments.json 懒加载机台白名单(线程安全 + 进程内缓存)。"""
        with cls._equipments_lock:
            if cls._equipments_cache is not None:
                return cls._equipments_cache
            uix_root = os.environ.get("UIX_ROOT")
            if uix_root:
                config_path = Path(uix_root) / "config" / "equipments.json"
            else:
                config_path = Path(__file__).resolve().parents[4] / "config" / "equipments.json"
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data.get("equipments") or []
                cls._equipments_cache = [str(x).strip() for x in items if str(x).strip()]
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                logger.error("无法加载 config/equipments.json: %s;退化到内置默认列表", exc)
                cls._equipments_cache = [
                    "SSB8000", "SSB8001", "SSB8002", "SSB8005",
                    "SSC8001", "SSC8002", "SSC8003", "SSC8004", "SSC8005", "SSC8006",
                ]
            return cls._equipments_cache

    @classmethod
    def reload_equipments(cls) -> None:
        """供热更新使用(改完 JSON 后调用此方法刷新)。"""
        with cls._equipments_lock:
            cls._equipments_cache = None

    # 原 EQUIPMENT_WHITELIST 改为属性
    @classmethod
    def equipment_whitelist(cls) -> List[str]:
        return list(cls._load_equipments())

    @classmethod
    def validate_equipment(cls, equipment: str) -> bool:
        return equipment in cls._load_equipments()
```

**保留** `EQUIPMENT_WHITELIST = ...` 这一行作为 BC alias(以防外部代码引用),用 `property` 或 `__getattr__` 委托到 `equipment_whitelist()`。最简单是直接保留常量但每次进程重启时被覆盖:在 class 体外加一句 `RejectErrorService.EQUIPMENT_WHITELIST = RejectErrorService._load_equipments()`(模块加载时执行)。

### 同步改动

- [`docs/CONFIG_REVIEW_CHECKLIST.md`](../CONFIG_REVIEW_CHECKLIST.md) 第 4 节加一行「机台白名单变化只改 [`config/equipments.json`](../../config/equipments.json),禁止再改 service.py 的 EQUIPMENT_WHITELIST 常量」
- [`docs/STRUCTURE.md`](../STRUCTURE.md) §7 表加一行「加新机台 → 改 `config/equipments.json` 后跑 `python scripts/check_config.py`」

### 测试

```python
def test_equipment_whitelist_loaded_from_json(tmp_path, monkeypatch):
    fake_root = tmp_path / "uix-fake"
    (fake_root / "config").mkdir(parents=True)
    (fake_root / "config" / "equipments.json").write_text(
        '{"equipments":["FAKE001","FAKE002"]}', encoding="utf-8"
    )
    monkeypatch.setenv("UIX_ROOT", str(fake_root))
    RejectErrorService.reload_equipments()
    assert RejectErrorService.validate_equipment("FAKE001")
    assert not RejectErrorService.validate_equipment("SSB8000")
```

---

## Bug #3:_METRIC_ALIAS_MAP 配置化

### 问题

```python
# src/backend/app/engine/diagnosis_engine.py:758-763
_METRIC_ALIAS_MAP = {
    "output_Tx": "Tx",
    "output_Ty": "Ty",
    "output_Rw": "Rw",
}
```

新增建模产物的别名映射必须改 Python。

### 修复

把 alias 表达式挪到 metric 元数据的 `alias_of` 字段:

```json
"output_Tx": {
  "description": "COWA建模输出上片偏差Tx",
  "source_kind": "intermediate",
  "alias_of": "Tx",
  "approximate": true
}
```

`_find_threshold` 改为遍历 `metrics` 字典自动构建 alias 映射:

```python
def _build_alias_map(self) -> Dict[str, str]:
    out = {}
    for mid, meta in self.rule_loader.metrics.items():
        alias = meta.get("alias_of")
        if alias:
            out[mid] = str(alias)
    return out

def _find_threshold(self, metric_id: str) -> Optional[Dict[str, Any]]:
    alias_map = self._build_alias_map()
    lookup_id = alias_map.get(metric_id, metric_id)
    # ... 后续逻辑不变
```

### 同步改动

- [`src/backend/app/engine/rule_validator.py`](../../src/backend/app/engine/rule_validator.py) 增加 `alias_of` 字段校验(必须指向已存在的 metric_id)

---

## Bug #4:缓存按 config 版本失效

### 问题

`config/reject_errors.diagnosis.json` 改了之后,`rejected_detailed_records` 表里旧数据的 `root_cause` / `metrics_data` 仍然返回,**永不失效**。

### 修复(分两步)

**Step 1(可现在做,不依赖 stage4)**:加 `config_version` 列到 ORM + SQL

文件:
- [`src/backend/app/models/reject_errors_db.py`](../../src/backend/app/models/reject_errors_db.py) `class RejectedDetailedRecord` 加:
  ```python
  config_version = Column(String(50), nullable=True, index=True, comment="写入时的 pipeline version,供按版本失效")
  ```
- [`scripts/init_docker_db.sql`](../../scripts/init_docker_db.sql) `rejected_detailed_records` 表 DDL 加:
  ```sql
  `config_version` VARCHAR(50) DEFAULT NULL COMMENT '写入时的 pipeline version',
  INDEX `IDX_config_version` (`config_version`),
  ```

**Step 2(必须等 stage4 落地)**:`_save_to_cache` 写入时填 `config_version`,`_batch_get_cache` / `_build_detail_from_cache` 读取时比较 `DiagnosisConfigStore` 当前 version,不一致直接当 cache miss。

```python
# service/reject_error_service.py
@classmethod
def _save_to_cache(cls, db, source_record, diagnosis):
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    cached_record = RejectedDetailedRecord(
        ...
        config_version=str(pipeline.get("version", "unknown")),
    )

@classmethod
def _build_detail_from_cache(cls, cached, page_no, page_size):
    store = DiagnosisConfigStore()
    pipeline = store.get_pipeline("reject_errors")
    current_version = str(pipeline.get("version", "unknown"))
    if cached.config_version and cached.config_version != current_version:
        # 缓存配置版本与当前不一致,视为 miss
        return None  # 调用方需 handle None → 重新走诊断引擎
    # ... 其他逻辑不变
```

调用方 `get_failure_details` 在拿到 `None` 时跳过 cache 走诊断引擎(自动重写一份新 version 的缓存)。

---

## Bug #5:`_mock_intermediate_value` / `legacy_ranges` 硬编码

### 问题

```python
# metric_fetcher.py:944-984
def _mock_value(self, ...):
    legacy_ranges = {
        "Mwx_0": (0.99985, 1.00015),
        ...
    }

def _mock_intermediate_value(self, metric_id, meta):
    values = {
        "n_88um": 3.0,
        "output_Mw": 5.0,
        ...
    }
```

新指标想要 mock 必须改 Python。

### 修复

完全删除 `legacy_ranges` 和 `_mock_intermediate_value` 字典,只用 `meta.get("mock_value")` / `meta.get("mock_range")` —— **这两个字段已存在**,只需要在 [`config/reject_errors.diagnosis.json`](../../config/reject_errors.diagnosis.json) 里给每个 mock 用得到的 metric 显式填:

```json
"Mwx_0": {
  ...,
  "mock_range": [0.99985, 1.00015]
},
"n_88um": {
  ...,
  "mock_value": 3.0
}
```

`_mock_value` 改简化版:

```python
def _mock_value(self, metric_id: str, meta: Dict[str, Any]) -> Any:
    if "mock_value" in meta:
        return meta["mock_value"]
    if isinstance(meta.get("mock_range"), list) and len(meta["mock_range"]) == 2:
        low, high = meta["mock_range"]
        return round(random.uniform(float(low), float(high)), 6)
    # 通用 fallback:[-10, 10] 随机
    return round(random.uniform(-10.0, 10.0), 4)
```

### 同步改动

- [`src/backend/app/engine/rule_validator.py`](../../src/backend/app/engine/rule_validator.py) 增加 `mock_value` / `mock_range` 字段校验(类型与长度)
- [`config/CONFIG_GUIDE.md`](../../config/CONFIG_GUIDE.md) 加「Mock 数据写法」章节

---

## Bug #6:`max_steps` 截断日志

### 问题

```python
# diagnosis_engine.py:_walk_subtree
for _ in range(max_steps):
    ...
return (None, None, trace, abnormal_metrics, context)  # ← 这里没说是 max_steps 截断了
```

专家配置如果错误地形成长循环,看日志只看到「诊断中断」,无法判断是「分支真没命中」还是「max_steps 截断」。

### 修复

```python
def _walk_subtree(self, ...):
    current_node = start_node
    iterations = 0
    for iterations in range(1, max_steps + 1):
        ...
    # 如果 for 正常结束(没 break / return),说明走满了 max_steps
    if iterations >= max_steps:
        logger.warning(
            "_walk_subtree: 步骤 %s 起诊断在 max_steps=%d 处被强制截断,"
            "可能配置形成了循环;trace=%s",
            start_node, max_steps, trace,
        )
        detail_trace.warning(
            "max_steps 截断 | start_node=%s | max_steps=%d | trace=%s",
            start_node, max_steps, trace,
        )
    return (None, None, trace, abnormal_metrics, context)
```

---

## Bug #7:`_render_extraction_template` list 边界

### 问题

```python
# metric_fetcher._render_extraction_template
def _replace(match):
    value = self._resolve_context_value(match.group(1), ...)
    if value is None:
        missing = True; return ""
    return str(value)  # ← 如果 value 是 list,变成 "[1.0, 2.0]" 拼到 path 里
```

模板里 `{var}` 如果碰巧解析到一个 list(window 类指标的常态),会拼出错误 jsonpath,**静默失败**(返回 None)。

### 修复

```python
def _replace(match):
    value = self._resolve_context_value(match.group(1), ...)
    if value is None:
        missing = True
        return ""
    if isinstance(value, list):
        # 取第一个非 None 元素;若全 None,视为缺失
        non_null = [v for v in value if v is not None]
        if not non_null:
            missing = True
            return ""
        logger.warning(
            "extraction template var=%s 解析到 list(len=%d),取第一个非空元素 %r;"
            "如希望按完整列表行为,请避免在 jsonpath 模板里直接引用 window 类指标",
            match.group(1), len(value), non_null[0],
        )
        return str(non_null[0])
    return str(value)
```

### 测试

```python
def test_render_extraction_template_with_list_var_warns_and_picks_first():
    fetcher = ...
    template = "static_wafer_load_offset/chuck_message[{some_id}]/x"
    result = fetcher._render_extraction_template(template, {"some_id": [0, 1, 2]})
    assert result == "static_wafer_load_offset/chuck_message[0]/x"
```

---

## Apply 顺序建议(stage4 落地后)

1. **第一波(基础设施 + 高 ROI)**:Bug #1 + Bug #2 + Bug #4 Step1
2. **第二波(配置驱动深化)**:Bug #3 + Bug #5
3. **第三波(可观测性)**:Bug #6 + Bug #7 + Bug #4 Step2

每波是独立 commit,可单独 revert。一波内部 hunk 不重叠,可同一笔 commit。

总工作量预估:**1.5–2 天**(含测试与文档同步)。

---

## 跟现有 commit A–J 的关系

本文档中所有 patch **不会**与 commit A–J 冲突;反之 commit J 已经为 Bug #2 准备了 [`config/equipments.json`](../../config/equipments.json),为 Bug #1 准备了 [`scripts/init_docker_db.sql`](../../scripts/init_docker_db.sql) commit F 的 mock 数据形态(届时改回 array 即可)。
