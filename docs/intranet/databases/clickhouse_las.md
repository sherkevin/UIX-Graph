# ClickHouse `las`

> 内网 ClickHouse 实例下的 `las` 数据库,用于**设备日志、对准结果**类海量时序数据。
> 外网 mock 量极小(每张表 1 行),只为打通诊断流程,**不做性能 mock**。

---

## 0. 数据库概要

| 项 | 值 |
|---|---|
| 数据库类型 | ClickHouse |
| 库名 | `las`(`las` = log analysis system 的内网命名) |
| 本地端口 | `8123`(HTTP),`config/connections.json` 的 `local.clickhouse` |
| 内网测试地址 | `172.16.70.103:8123`(`test.clickhouse`) |
| 内网生产地址 | `clickhouse.datacenter.smee.com.cn:8123`(`prod.clickhouse`) |
| 在拒片诊断中的角色 | **触发指标 + 倍率指标 Mwx_0** 来源;未来 mark 信息也可能落 `las.*` |
| ClickHouse 引擎家族 | `MergeTree` / `ReplicatedMergeTree`(内网真实表) |

### 表清单

| 表名 | 类型 | 拒片诊断中的角色 | 本地 mock 完整度 |
|------|------|------------------|------------------|
| [`LOG_EH_UNION_VIEW`](#log_eh_union_view) | Table(MergeTree) | **触发指标 `trigger_log_mwx_cgg6_range`** + **倍率 `Mwx_0`** | 1 行 mock,值为 `'Mwx ( 1.00003 )'` |
| `RPT_WAA_RESULT_OFL` *(stage4 计划)* | Table | 计划用于 mark_id 解析(stage4 §1 Task) | **未 mock**,见 [`linking_tbd.md`](../linking_tbd.md) |
| `RTP_WAA_LOT_MARK_INFO_UNION_VIEW` *(stage4 计划)* | View | 计划替代 `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA` 作 `mark_pos_x/y` 来源(stage4 §1) | **未 mock** |

---

## `LOG_EH_UNION_VIEW`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `las.LOG_EH_UNION_VIEW` |
| 类型 | Table(本地 MergeTree;内网为 UNION VIEW,聚合多个分片) |
| 引擎(本地) | `MergeTree ORDER BY (equipment, file_time)` |
| 主键 / 排序键 | `(equipment, file_time)` |
| 主要时间列 | `file_time`(`DateTime64(3, 'UTC')`) |
| 主要关联键 | `equipment`(`LowCardinality(String)`) |
| 拒片诊断中的角色 | 1) 场景触发判断(`trigger_log_mwx_cgg6_range`)2) 倍率值提取(`Mwx_0`) |
| **关键说明** | `detail` 是日志正文大字符串,从中用 **regex 抠值**(不是结构化数据) |

### 列定义(内网 18 列)

| # | 列名 | ClickHouse 类型 | 业务说明 | 在诊断中怎么用 |
|---|------|----------------|---------|---------------|
| 1 | `machine_id` | `Nullable(String)` | 设备号 | 暂未使用(用 `equipment` 代替) |
| 2 | `release_version` | `Nullable(String)` | 软件发布版本 | 暂未使用 |
| 3 | `process_name` | `Nullable(String)` | 工艺名 | 暂未使用 |
| 4 | `method_name` | `Nullable(String)` | 方法名 | 暂未使用 |
| 5 | `process_id` | `Nullable(String)` | 工艺 ID | **关联候选**(可能与 performance 行精确对齐,见 [`linking_tbd.md`](../linking_tbd.md)) |
| 6 | `system_event_code` | `Nullable(String)` | 系统事件码 | **关联候选** |
| 7 | `source_file_name` | `Nullable(String)` | 源文件名 | **关联候选** |
| 8 | `line_number` | `Nullable(String)` | 行号 | 暂未使用 |
| 9 | `event_type` | `Nullable(String)` | 事件类型 | 暂未使用 |
| 10 | `event_level` | `Nullable(String)` | 日志级别 | 暂未使用 |
| 11 | `component_name` | `Nullable(String)` | 组件名 | 暂未使用 |
| 12 | `linked_component_name` | `Nullable(String)` | 关联组件名 | 暂未使用 |
| 13 | `linked_event_code` | `Nullable(String)` | 关联事件码 | **关联候选** |
| 14 | `detail` | `Nullable(String)` | **日志正文大字段**(关键!) | 两个 metric 都从这一列 regex 抠值 |
| 15 | `repeat` | `Nullable(Int32)` | 重复次数 | 暂未使用 |
| 16 | `env_id` | `String` | 环境标识 | 暂未使用 |
| 17 | `equipment` | `LowCardinality(String)` | **机台名**(主关联键) | `linking.keys`(场景触发指标当前没启用 keys,只用时间窗 + equipment) |
| 18 | `file_time` | `DateTime64(3, 'UTC')` | **日志时间**(主时间列) | 时间窗右端 = T,左端 = T - duration |

> **重点列**:`equipment`、`file_time`、`detail`,这三列**任何 mock 都必须填**。

### 关联

- 内网当前关联仅按 `equipment + 时间窗`,**没有跟单次拒片精确对应的键**
- 待业务确认是否可用 `process_id` / `source_file_name` / `system_event_code` / `linked_event_code` 等做精确关联,详见 [`linking_tbd.md`](../linking_tbd.md)

### 诊断引擎引用

| metric_id | column_name | extraction_rule | linking | duration | 用途 |
|-----------|-------------|-----------------|---------|---------:|------|
| `trigger_log_mwx_cgg6_range` | `detail` | `regex:Mwx out of range,CGG6_check_parameter_ranges` | `time_window_only` | 7 天 | 场景 1001 的触发条件之一(布尔) |
| `Mwx_0` | `detail` | `regex:Mwx\s*\(\s*([\d\.]+)\s*\)` | `time_window_only` | 7 天 | 倍率实测值,捕获组 1 = 浮点数 |

### regex 规则的工作机制

`MetricFetcher._apply_extraction_rule` 处理 `regex:` 前缀:

- **有捕获组** → 取第 1 组(`Mwx_0` 用这种)
- **无捕获组** → 匹配成功 = `True`,失败 = `False`(`trigger_log_mwx_cgg6_range` 用这种)

`fetch_all` 会把 `Mwx_0` 的多行结果作为 list 返回,然后 `select_window_metric` action 选距 T 最近的一条。

### Mock 数据形态(本地 docker ClickHouse 已注入 1 行)

```sql
INSERT INTO las.LOG_EH_UNION_VIEW (
    machine_id, release_version, process_name, method_name, process_id, system_event_code,
    source_file_name, line_number, event_type, event_level, component_name,
    linked_component_name, linked_event_code,
    detail,        -- <<< 关键字段
    repeat, env_id, equipment, file_time
) VALUES (
    NULL, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL,
    'Mwx ( 1.00003 )',  -- regex 会抠出 "1.00003" 作为 Mwx_0
    NULL, 'local', 'SSB8000',
    '2026-01-10 08:44:30.000'  -- file_time 必须在 [T - 7 天, T = 08:45] 内
);
```

> **已修复**:`scripts/init_clickhouse_local.sql` 现在同时插入两行,既给 `Mwx_0` 提供值,也给场景 1001 的 trigger 提供必要的 `'Mwx out of range,CGG6_check_parameter_ranges'` 日志行。`select_scene` 在本地 docker 环境下能正常命中 COWA 场景,接口 3 会走完整诊断路径。

```sql
-- Mwx_0 倍率值样本(regex 捕获 1.00003)
INSERT INTO las.LOG_EH_UNION_VIEW (..., detail, ..., file_time)
VALUES (..., 'Mwx ( 1.00003 )', ..., '2026-01-10 08:44:30.000');

-- 触发场景 1001 的关键日志(regex 子串匹配)
INSERT INTO las.LOG_EH_UNION_VIEW (..., detail, ..., file_time)
VALUES (..., 'Mwx out of range,CGG6_check_parameter_ranges (Mwx=1.00012)', ..., '2026-01-10 08:44:35.000');
```

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_clickhouse_local.sql` | L8–L37 |
| `src/backend/app/ods/clickhouse_ods.py` | `query_metric_in_window` |
| `config/reject_errors.diagnosis.json` | `metrics.trigger_log_mwx_cgg6_range`、`metrics.Mwx_0` |

---

## `RPT_WAA_RESULT_OFL` *(Stage4 计划接入)*

### 来源

`docs/stage4/prd.md` §具体步骤 第 2 步:
> 在 `las.RPT_WAA_RESULT_OFL` 表中查询 `mark_id`,查询条件是 `lot_id = l && wafer_id = w && chuck_id = c && phase = '1ST_COWA'`

### 预期列(待业务确认)

| 列名 | 预期类型 | 用途 |
|------|---------|------|
| `lot_id` | ? | linking |
| `wafer_id` | ? | linking |
| `chuck_id` | ? | linking |
| `phase` | `String` | 固定 filter `phase = '1ST_COWA'` |
| `mark_id` | ? | **要返回的字段**(预期返回 4 个值,按 `row_id ASC` 取前 4 条) |
| `row_id` | `String` | 排序用 |

### 现状

- 未在 `init_clickhouse_local.sql` 建表
- diagnosis.json 中 `mark_pos_x / mark_pos_y` 当前是从 `src.RPT_WAA_SET_OFL` 取值,**不走 `las.RPT_WAA_RESULT_OFL` 这条路径**
- `linking_tbd.md` 已记录该 gap

---

## `RTP_WAA_LOT_MARK_INFO_UNION_VIEW` *(Stage4 计划接入)*

### 来源

`docs/stage4/prd.md` §具体步骤 第 3 步:
> 在 `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW` 中查询对应的四个坐标值,查询条件是 `lot_id = l, mark_id IN (m1, m2, m3, m4)`

### 现状

- 未建表
- 当前 `mark_pos_x / mark_pos_y` 从 `src.RPT_WAA_SET_OFL` 取(用业务最新口径,不走 stage4 设计)
- 等业务确认 stage4 取数路径是否最终采纳后,在 `init_clickhouse_local.sql` 与本文件补 DDL
