# MySQL `datacenter`

> 本文件描述内网 MySQL 实例下的 `datacenter` 数据库;外网开发的所有 mock 都基于本文件复刻。
>
> **读法**:每张表分四块——元信息 / 列定义 / 关联 / 诊断引擎引用 / Mock 建议。
> **类型来源**:已确认列以内网 `SHOW CREATE TABLE` 为准,Docker mock 与之对齐。

---

## 0. 数据库概要

| 项 | 值 |
|---|---|
| 实例类型 | MySQL 8.0(本地 docker)/ 内网 MySQL(版本待补) |
| 字符集 | `utf8mb4` `utf8mb4_unicode_ci` |
| 本地端口 | `3307`(`config/connections.json` 的 `local.mysql.port`) |
| 内网测试地址 | `172.16.70.171:3306`(`config/connections.json` 的 `test.mysql`) |
| 内网生产地址 | `mysql.datacenter.smee.com.cn:30888`(`prod.mysql`) |
| 在拒片诊断中的角色 | **主数据源 + 配置历史 + 应用缓存** 三件事一站式 |

### 表清单

| 表名 | 类型 | 用途 | 拒片诊断中的角色 | 本地 mock 完整度 |
|------|------|------|------------------|------------------|
| [`lo_batch_equipment_performance`](#lo_batch_equipment_performance) | Table | 机台 / 批次 / 性能 / 拒片原始数据 | **主数据源**;接口 1/2/3 都从这里取;`Tx/Ty/Rw` 直接是 `wafer_translation_*` / `wafer_rotation` | 高:96 列里前 ~70 列已建表,COARSE 样例已注入 |
| [`reject_reason_state`](#reject_reason_state) | Table | 拒片原因枚举(`reject_reason_id` ↔ `reject_reason_value`) | 接口 2 列表 `rejectReason` 文案来源 | 完整,11 个枚举值 |
| [`mc_config_commits_history`](#mc_config_commits_history) | Table | MC 配置提交历史(JSON 大字段) | `Sx/Sy` 静态上片偏差从 `data` 列里 jsonpath 抽取 | 最小 mock,1 行 |
| [`rejected_detailed_records`](#rejected_detailed_records) | Table | **应用层缓存表**(本系统创建,不是业务源表) | 接口 3 诊断结果落地 + 接口 2 反查 `rootCause/system` | 不需要 mock,运行时自填 |
| [`LO_wafer_result`](#lo_wafer_result-计划接入)*(计划接入)* | Table | 单 wafer 上片偏差结果 | 计划用于 `D_x/D_y`(Stage4)| **未 mock**,等内网确认表名 |
| [`lo_batch_equipment_performance_temp`](#lo_batch_equipment_performance_temp-计划接入)*(计划接入)* | Table | performance 历史快照(可能按日期分表) | 计划用于 `Tx/Ty/Rw` 的历史窗口 | **未 mock**,等内网确认 |

---

## `lo_batch_equipment_performance`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `datacenter.lo_batch_equipment_performance` |
| 类型 | Table |
| 引擎 | InnoDB |
| 主键 | `id` AUTO_INCREMENT |
| 主要时间列 | `wafer_product_start_time`(故障基准时间 T 的来源)、`lot_start_time`、`lot_end_time` |
| 主要关联键 | `equipment`, `chuck_id`, `lot_id`, `wafer_index`(注意:**不是** `wafer_id`) |
| 索引 | `IDX_equipment`、`IDX_chuck_lot_wafer (chuck_id, lot_id, wafer_index)`、`IDX_wafer_product_start_time`、`IDX_lot_start_end_time`、`IDX_reject_reason` |
| 拒片诊断中的角色 | **主数据源**;接口 1/2/3 全部依赖;`Tx/Ty/Rw/Tx_history/Ty_history/Rw_history` 6 个 metric 都查本表 |
| 内网真实列数 | 96 列(序号 58–96 内网清单未给出,Docker mock 暂略) |

### 列定义

| # | 列名 | 类型 | 可空 | 业务说明 | 在诊断中怎么用 |
|---|------|------|------|---------|---------------|
| 1 | `id` | INT AUTO_INCREMENT | NO | 故障记录 ID(主键) | 接口 2/3 主键;缓存表 `failure_id` 引用此值 |
| 2 | `equipment` | VARCHAR(50) | NO | 机台名称(`SSB8000`/`SSC8001` 等) | `linking.keys[].source = "equipment"` 的来源 |
| 3 | `lot_start_time` | DATETIME(6) | YES | Lot 开始时间 | **接口 1** `metadata` 的 `startTime` 过滤列 |
| 4 | `lot_end_time` | DATETIME(6) | YES | Lot 结束时间 | **接口 1** `endTime` 过滤列 |
| 5 | `seq_id_lo_wafer_mamsd_result` | INT | YES | 内网原表字段 | 暂未使用 |
| 6 | `recipe_id` | VARCHAR(500) | YES | 工艺配方 ID | ClickHouse `mark_pos_x/y` 的 `linking.keys` 候选 |
| 7 | `layer_id` | VARCHAR(500) | YES | 层 ID | 暂未使用 |
| 8 | `lot_id` | INT | NO | Lot ID | `linking.keys[].source = "lot_id"` 的来源 |
| 9 | `lot_name` | VARCHAR(500) | YES | Lot 名称 | 列表展示 |
| 10 | `substrate_lot_id` | VARCHAR(500) | YES | Substrate lot ID | 暂未使用 |
| 11 | `wafer_index` | INT | NO | **Wafer 序号 1–25(注意是 index 不是 id)** | `chuck_lot_wafer` 索引一员;接口 1/2 筛选 |
| 12 | `wafer_id` | VARCHAR(500) | YES | Wafer ID(字符串型) | 与 ClickHouse 侧 `wafer_id` 的语义对齐**待确认** |
| 13 | `chuck_id` | INT | NO | Chuck ID | 接口 1/2/3 + `linking.keys[].source = "chuck_id"` |
| 14 | `wafer_translation_x` | DECIMAL(18,9) | YES | **COWA 建模输出 Tx(um)** | metric `Tx` / `Tx_history` 直接读这一列 |
| 15 | `wafer_translation_y` | DECIMAL(18,9) | YES | **COWA 建模输出 Ty(um)** | metric `Ty` / `Ty_history` |
| 16 | `wafer_expansion_x` | DECIMAL(18,9) | YES | Wafer expansion x | 暂未使用 |
| 17 | `wafer_expansion_y` | DECIMAL(18,9) | YES | Wafer expansion y | 暂未使用 |
| 18 | `wafer_rotation` | DECIMAL(18,3) | YES | **COWA 建模输出 Rw(urad)** | metric `Rw` / `Rw_history` |
| 19 | `wafer_non_orthogonal` | DECIMAL(18,3) | YES | Wafer non orthogonal | 暂未使用 |
| 20 | `std_wafer_translation_x` | DECIMAL(18,9) | YES | Std wafer translation x | 暂未使用 |
| 21 | `std_wafer_translation_y` | DECIMAL(18,9) | YES | Std wafer translation y | 暂未使用 |
| 22 | `std_wafer_rotation` | DECIMAL(18,3) | YES | Std wafer rotation | 暂未使用 |
| 23-32 | `max_ws_*_ma/msd` 系列 | DECIMAL(18,6/9) | YES | WS 最大移动平均 / 移动标准差(8 列 × 2) | 暂未使用 |
| 33-42 | `max_ws_*_total_ma/msd` 系列 | DECIMAL(18,6) | YES | WS 总和 ma/msd | 暂未使用 |
| 43-56 | `max_rs_*_ma/msd` 系列 | DECIMAL(18,6/9) | YES | RS 系列指标 | 暂未使用 |
| 57 | `max_rs_y_total_msd` | DECIMAL(18,6) | YES | (Docker mock 到此为止) | — |
| 58–96 | *(内网真实列,清单未给出)* | — | — | **待业务侧补 DDL** | — |
| 73 | `lot_end_lens_temp` | DECIMAL(18,6) | YES | Lot 结束镜头温度 | 暂未使用 |
| 74 | `lot_end_lens_pressure` | DECIMAL(18,6) | YES | Lot 结束镜头压力 | 暂未使用 |
| 75 | `lot_start_lens_temp` | DECIMAL(18,6) | YES | Lot 开始镜头温度 | 暂未使用 |
| 76 | `lot_start_lens_pressure` | DECIMAL(18,6) | YES | Lot 开始镜头压力 | 暂未使用 |
| 77 | `dose_err_ilpe_min` | DECIMAL(18,9) | YES | 曝光剂量误差 ILPE min | 暂未使用 |
| 78 | `dose_err_ilpe_max` | DECIMAL(18,9) | YES | 曝光剂量误差 ILPE max | 暂未使用 |
| 79 | `dose_err_ilpe_mean` | DECIMAL(18,9) | YES | 曝光剂量误差 ILPE mean | 暂未使用 |
| 80 | `dose_err_elpe_max` | DECIMAL(18,9) | YES | 曝光剂量误差 ELPE max | 暂未使用 |
| 81 | `dose_err_elpe_min` | DECIMAL(18,9) | YES | 曝光剂量误差 ELPE min | 暂未使用 |
| 82 | `dose_err_elpe_mean` | DECIMAL(18,9) | YES | 曝光剂量误差 ELPE mean | 暂未使用 |
| 83 | `actual_energy` | DECIMAL(18,9) | YES | 实际曝光能量 | 暂未使用 |
| 84 | `focus_z` | DECIMAL(18,9) | YES | 对焦 Z | 暂未使用 |
| 85 | `image_size_x` | DECIMAL(18,9) | YES | 图像 X 尺寸 | 暂未使用 |
| 86 | `image_size_y` | DECIMAL(18,9) | YES | 图像 Y 尺寸 | 暂未使用 |
| 87 | `creation_date` | DATETIME | YES | 记录创建时间 | 暂未使用 |
| 88 | `wafer_product_start_time` | DATETIME(6) | NO | **Wafer 生产开始时间(故障基准时间 T 来源)** | 接口 2 `time` 字段;接口 3 `requestTime` 缺省值;所有 ClickHouse 时间窗的右端 |
| 89 | `wafer_state` | BIGINT | YES | Wafer 状态 | 暂未使用 |
| 90 | `reject_reason` | BIGINT | NO | **拒片原因 ID(外键到 `reject_reason_state`)** | 触发 metric `trigger_reject_reason_cowa_6`;诊断场景命中依据 |
| 91 | `insert_time` | DATETIME | YES | 插入时间 | 暂未使用 |

> **重点列**(高亮):`equipment`、`chuck_id`、`lot_id`、`wafer_index`、`wafer_product_start_time`、`reject_reason`、`wafer_translation_x/y`、`wafer_rotation`、`recipe_id`。这 9 列**任何 mock 都必须填**。

### 关联

| 关联到 | 关联字段 | 状态 |
|--------|----------|------|
| `datacenter.reject_reason_state` | `reject_reason` ↔ `reject_reason_id` | ✅ 已落地 |
| `datacenter.rejected_detailed_records` | `id` ↔ `failure_id` | ✅ 已落地 |
| `clickhouse las.LOG_EH_UNION_VIEW` | `equipment` + 时间窗;**单次拒片 ↔ 单条日志的精确键待业务确认** | ⚠️ 见 [`linking_tbd.md`](../linking_tbd.md) |
| `clickhouse src.RPT_WAA_SET_OFL` | `equipment` + `lot_id` + `chuck_id` + `wafer_index` ↔ `wafer_id`(语义待确认) | ⚠️ 见 [`linking_tbd.md`](../linking_tbd.md) |
| `clickhouse src.RPT_WAA_SA_RESULT_OFL` | 同上 | ⚠️ 同上 |

### 诊断引擎引用

来自 `config/reject_errors.diagnosis.json` 的 `metrics` 字典(直接访问本表):

| metric_id | source_kind | column_name | linking | 说明 |
|-----------|-------------|-------------|---------|------|
| `trigger_reject_reason_cowa_6` | `failure_record_field` | `reject_reason` (transform: `equals 6`) | — | 场景触发(布尔) |
| `Tx` | `failure_record_field` | `wafer_translation_x` | — | 直接读 |
| `Ty` | `failure_record_field` | `wafer_translation_y` | — | 直接读 |
| `Rw` | `failure_record_field` | `wafer_rotation` | — | 直接读 |
| `Tx_history` | `mysql_nearest_row` | `wafer_translation_x` | `chuck_id` | 30 天窗口列表,`role: internal` |
| `Ty_history` | `mysql_nearest_row` | `wafer_translation_y` | `chuck_id` | 30 天窗口列表,`role: internal` |
| `Rw_history` | `mysql_nearest_row` | `wafer_rotation` | `chuck_id` | 30 天窗口列表,`role: internal` |

### Mock 建议(Docker MySQL)

最小可诊断 mock(已在 `scripts/init_docker_db.sql` 落地):

```sql
-- 锚点 COARSE 样例:SSB8000, chuck=1, lot=101, wafer=7, T=2026-01-10 08:45
-- reject_reason=6 即 COARSE_ALIGN_FAILED → 进入 COWA 诊断场景
INSERT INTO `lo_batch_equipment_performance`
  (`equipment`, `chuck_id`, `lot_id`, `wafer_index`,
   `lot_start_time`, `lot_end_time`, `wafer_product_start_time`,
   `reject_reason`, `wafer_translation_x`, `wafer_translation_y`,
   `wafer_rotation`, `recipe_id`)
VALUES
('SSB8000', 1, 101, 7,
 '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000',
 '2026-01-10 08:45:00.000000',
 6,           -- COARSE_ALIGN_FAILED
 25.5,        -- Tx 超限(>20)→ 上片工艺适应性问题
 3.2,
 150.0,
 'RCP-DOCKER-001');
```

> **`Tx_history`/`Ty_history`/`Rw_history` 的 mock**:让同一个 `chuck_id=1`、`equipment='SSB8000'` 在 T 前 30 天内有多条记录(`scripts/init_docker_db.sql` 已经在第 145 行起注入了 60+ 条数据,覆盖)。

### 引用位置

| 文件 | 位置 | 用途 |
|------|------|------|
| `scripts/init_docker_db.sql` | L13–L98 (建表) / L146–L250 (数据) | Docker mock |
| `src/backend/app/models/reject_errors_db.py` | `class LoBatchEquipmentPerformance` | ORM |
| `src/backend/app/ods/datacenter_ods.py` | `query_chuck_lot_wafer` / `query_failure_records` / `get_failure_record_by_id` | 接口 1/2/3 取数 |
| `config/reject_errors.diagnosis.json` | `metrics.{trigger_reject_reason_cowa_6, Tx, Ty, Rw, Tx_history, Ty_history, Rw_history}` | 诊断引擎 |

---

## `reject_reason_state`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `datacenter.reject_reason_state` |
| 类型 | Table |
| 引擎 | InnoDB |
| 主键 | `reject_reason_id` |
| 拒片诊断中的角色 | 接口 2 列表的 `rejectReason` 文案来源 |

### 列定义

| # | 列名 | 类型 | 可空 | 业务说明 | 在诊断中怎么用 |
|---|------|------|------|---------|---------------|
| 1 | `reject_reason_id` | BIGINT | NO | 拒片原因 ID(主键) | 与 `lo_batch_equipment_performance.reject_reason` 关联 |
| 2 | `reject_reason_value` | VARCHAR(50) | NO | 拒片原因英文枚举值 | 接口 2 `rejectReason` 字段 |

### 已知枚举值(Docker mock 完整)

| `reject_reason_id` | `reject_reason_value` | 是否触发诊断 |
|-------------------:|----------------------|-------------|
| `6` | `COARSE_ALIGN_FAILED` | ✅ **触发 COWA 诊断场景** |
| `5001` | `MEASURE_FAILED` | 否 |
| `5002` | `ALIGNMENT_FAILED` | 否 |
| `5003` | `OVERLAY_EXCEEDED` | 否 |
| `5004` | `FOCUS_FAILED` | 否 |
| `5005` | `WAFER_ROTATION_EXCEEDED` | 否 |
| `5006` | `MAGNIFICATION_EXCEEDED` | 否 |
| `5007` | `RESIDUAL_EXCEEDED` | 否 |
| `5008` | `VACUUM_FAILED` | 否 |
| `5009` | `MARK_RECOGNITION_FAILED` | 否 |
| `5010` | `SCAN_ERROR` | 否 |

> **`NONE_REJECTED` 未注入**(因为接口 1/2 已经在 SQL 层过滤掉「无拒片」记录,见 `datacenter_ods.query_chuck_lot_wafer`)。

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_docker_db.sql` | L8–L11(表)、L127–L138(枚举值) |
| `src/backend/app/models/reject_errors_db.py` | `class RejectReasonState` |
| `src/backend/app/ods/datacenter_ods.py` | `_reason_map_cache` 启动时缓存 |

---

## `mc_config_commits_history`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `datacenter.mc_config_commits_history` |
| 类型 | Table |
| 引擎 | InnoDB |
| 主键 | `id` AUTO_INCREMENT |
| 主要时间列 | `last_modify_date`(**注意:`VARCHAR(50)` 不是 datetime**) |
| 拒片诊断中的角色 | `Sx` / `Sy` 静态上片偏差从 `data` 列里 jsonpath 提取 |

### 列定义

| # | 列名 | 类型 | 可空 | 业务说明 | 在诊断中怎么用 |
|---|------|------|------|---------|---------------|
| 1 | `table_name` | VARCHAR(50) | NO | 配置归属的表名(如 `COMC`、`SCAN`) | `linking.filters[].target = "table_name"` 固定为 `"COMC"` |
| 2 | `last_modifier` | VARCHAR(50) | YES | 最后修改人 | 暂未使用 |
| 3 | `last_modify_date` | VARCHAR(50) | NO | 最后修改时间(字符串) | `metric.time_column = "last_modify_date"` |
| 4 | `commit` | VARCHAR(50) | YES | 提交标识 | 暂未使用 |
| 5 | `env_id` | VARCHAR(50) | YES | 环境 ID(包含机台名子串,如 `local_SSB8000`)| `linking.filters[]`:`env_id contains equipment`(用 SQL `INSTR`) |
| 6 | `data` | LONGTEXT | NO | **配置 JSON 大字段** | `metric.column_name = "data"`,`extraction_rule = jsonpath:...` |
| 7 | `id` | INT AUTO_INCREMENT | NO | 主键 | — |

### 关联

- 内网 DDL **没有** `equipment` 列,因此查询时 `mysql_omit_equipment_filter: true`,不在 WHERE 里加 `equipment = ?`,改用 `env_id contains equipment` 模糊匹配
- 与机台/批次/wafer 的精确关联见 [`linking_tbd.md`](../linking_tbd.md)

### 诊断引擎引用

| metric_id | column_name | extraction_rule | linking |
|-----------|-------------|-----------------|---------|
| `Sx` | `data` | `jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x` | `table_name = 'COMC'` + `env_id contains {equipment}` |
| `Sy` | `data` | `jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/y` | 同上 |

> `chuck_index0 = chuck_id - 1`,用于 JSON 数组下标。`MetricFetcher._resolve_context_value` 会在解析 jsonpath 模板时自动算这个值。

### Mock 数据形态(Docker MySQL 已注入 1 行,已修复)

```sql
INSERT INTO `mc_config_commits_history`
  (`table_name`, `last_modifier`, `last_modify_date`, `commit`, `env_id`, `data`)
VALUES
('COMC',                                  -- 匹配 linking.filters table_name='COMC'
 'docker_seed', '2026-01-10 08:40:00', 'seed1',
 'local_SSB8000',                         -- 匹配 linking.filters env_id contains equipment(SSB8000)
 '{"static_wafer_load_offset":{"chuck_message[0]":{"static_load_offset":{"x":0.001234,"y":-0.005678}},"chuck_message[1]":{"static_load_offset":{"x":0.002000,"y":-0.003000}}}}');
```

> **重点**:`table_name` 与 `env_id` 都对齐了 diagnosis.json 的 filter 条件,`data` 是 nested JSON,本地 jsonpath 能命中。

### ⚠ 已知 issue:jsonpath 模板与 fetcher 实现不兼容

诊断配置 `extraction_rule = jsonpath:static_wafer_load_offset/chuck_message[{chuck_index0}]/static_load_offset/x`

`MetricFetcher._render_extraction_template` 渲染后变成 `static_wafer_load_offset/chuck_message[0]/static_load_offset/x`,按 `/` split 后第二段 `"chuck_message[0]"` 既不是纯数字(无法走数组下标分支),也不会自动剥离方括号——`_extract_json_path_value` 会到 dict 里找名为 `"chuck_message[0]"` 的字符串 key。

**两条出路**(stage4 选一):

1. **改 fetcher**:让 `_extract_json_path_value` 识别 `name[N]` 这种 segment(剥离方括号、N 当数组下标)。改 [`src/backend/app/engine/metric_fetcher.py`](../../../src/backend/app/engine/metric_fetcher.py) `_extract_json_path_value`。
2. **改 jsonpath**:把 `chuck_message[{chuck_index0}]` 改成 `chuck_message/{chuck_index0}`(去掉方括号)——这跟 [`docs/stage4/reject_errors_config_mapping.md`](../../stage4/reject_errors_config_mapping.md) §2.7「路径中纯数字段表示 JSON 数组下标」的官方约定一致。改 [`config/reject_errors.diagnosis.json`](../../../config/reject_errors.diagnosis.json) 的 `metrics.Sx.extraction_rule` 和 `metrics.Sy.extraction_rule`。

**当前 mock 用 `"chuck_message[0]"` 字符串 key**(不是 array)是为了**适配现状下 fetcher 实际行为**——本地能跑通,等 stage4 二选一落地后再把 mock 改回 array 形式。

### 真实内网 JSON 结构(预期,待 SHOW + 业务确认)

```json
{
  "static_wafer_load_offset": {
    "chuck_message": [
      { "static_load_offset": { "x": 0.001234, "y": -0.005678 } },
      { "static_load_offset": { "x": 0.002000, "y": -0.003000 } }
    ]
  }
}
```

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_docker_db.sql` | L256–L267 |
| `config/reject_errors.diagnosis.json` | `metrics.Sx` / `metrics.Sy` |

---

## `rejected_detailed_records`

> **应用层缓存表**——**业务源表里没有这张表**,是本系统创建的「诊断结果落地」。

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `datacenter.rejected_detailed_records` |
| 类型 | Table |
| 引擎 | InnoDB |
| 主键 | `id` AUTO_INCREMENT |
| 唯一约束 | `UK_failure_id (failure_id)` ⚠️ 高并发下可能触发冲突,见 service 层乐观幂等策略 |
| 拒片诊断中的角色 | 接口 3 诊断完成后**写入**;接口 2 列表批量**反查** `rootCause/system` |

### 列定义

| # | 列名 | 类型 | 可空 | 业务说明 | 写入/读取入口 |
|---|------|------|------|---------|--------------|
| 1 | `id` | BIGINT AUTO_INCREMENT | NO | 自增主键 | — |
| 2 | `failure_id` | BIGINT | NO **UNIQUE** | 关联源表 `lo_batch_equipment_performance.id` | `_save_to_cache` 写;`_batch_get_cache` 读 |
| 3 | `equipment` | VARCHAR(50) | NO | 机台 | 同上(供独立查询) |
| 4 | `chuck_id` | INT | NO | Chuck | 同上 |
| 5 | `lot_id` | INT | NO | Lot | 同上 |
| 6 | `wafer_id` | INT | NO | Wafer(注意:这里**不是** index) | 同上 |
| 7 | `occurred_at` | DATETIME(6) | NO | 故障发生时间 = 源表 `wafer_product_start_time` | — |
| 8 | `reject_reason` | VARCHAR(50) | NO | 拒片原因英文 | — |
| 9 | `reject_reason_id` | BIGINT | NO | 拒片原因 ID | — |
| 10 | `root_cause` | VARCHAR(255) | YES | **诊断引擎叶子结论 `rootCause`** | `RejectErrorService._save_to_cache` |
| 11 | `system` | VARCHAR(50) | YES | **诊断引擎叶子结论 `system`** | 同上 |
| 12 | `error_field` | VARCHAR(255) | YES | 异常 metric 列表(逗号分隔) | 同上 |
| 13 | `metrics_data` | JSON | YES | **完整指标数组**(含 status/threshold/value 等) | 同上 |
| 14 | `created_at` | DATETIME(6) | YES default `CURRENT_TIMESTAMP(6)` | 创建时间 | DB 自动 |
| 15 | `updated_at` | DATETIME(6) | YES default+update | 更新时间 | DB 自动 |

### 索引

| 索引名 | 字段 | 用途 |
|--------|------|------|
| `UK_failure_id` | `failure_id` | 防止同一故障重复写入 |
| `IDX_equipment` | `equipment` | 按机台批查 |
| `IDX_occurred_at` | `occurred_at` | 时间范围 |
| `IDX_chuck_lot_wafer` | `chuck_id, lot_id, wafer_id` | 多维度筛选 |
| `IDX_reject_reason` | `reject_reason` | 按拒片原因聚合 |

### 写入策略(注意!)

`RejectErrorService._save_to_cache` 实现是 **「先 SELECT 后 INSERT,失败静默」**:

- 命中 `UK_failure_id` 时不覆盖,**首次诊断结果优先**
- 并发 INSERT 触发 duplicate key 时 try/except 吞掉,不影响用户响应
- **没有按 config 版本失效**——规则改了,缓存里的 `rootCause` 也不会自动更新
- 后续优化方向:加 `config_version` 列 + 按版本失效(见 `docs/stage3/feature_todo.md`)

### 不需要 mock

应用启动后,接口 3 第一次访问每条故障会自动写入。本地不必预灌数据。

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_docker_db.sql` | L101–L122(建表,无 INSERT) |
| `src/backend/app/models/reject_errors_db.py` | `class RejectedDetailedRecord` |
| `src/backend/app/service/reject_error_service.py` | `_save_to_cache` / `_batch_get_cache` / `_build_detail_from_cache` |

---

## `LO_wafer_result` *(计划接入)*

### 元信息(预期)

| 项 | 值 |
|---|---|
| 全名 | `datacenter.LO_wafer_result`(可能带机台后缀,如 `LO_wafer_result_<machine>`,**待业务确认**) |
| 类型 | Table |
| 拒片诊断中的角色 | `D_x` / `D_y`(动态上片偏差) |

### 预期列(来自 `docs/stage4/prd.md` §其他相关参数 → D_x/D_y)

| 列名 | 类型 | 业务说明 | 用途 |
|------|------|---------|------|
| `lot_id` | ? | Lot ID | linking |
| `wafer_id` | ? | Wafer ID | linking |
| `chuck_id` | ? | Chuck ID | linking |
| `wafer_load_offset_x` | DECIMAL(?,?) | 动态上片偏差 X(um) | metric `D_x` |
| `wafer_load_offset_y` | DECIMAL(?,?) | 动态上片偏差 Y(um) | metric `D_y` |

### 待确认

- 物理表名:`LO_wafer_result` 还是 `LO_wafer_result_<machine>`?(`docs/plans/2026-04-13-cowa-metric-source-fixes.md` Task 7)
- 时间列名(`creation_date`?`insert_time`?)
- 关联键是否包含 `equipment` / `recipe_id`

### 现状

- `config/reject_errors.diagnosis.json` 中 `metrics.D_x` / `metrics.D_y` 当前为 `source_kind: intermediate`(本地由 `_mock_intermediate_value` 兜底)
- **未在 `init_docker_db.sql` 建表,未注入数据**

---

## `lo_batch_equipment_performance_temp` *(计划接入)*

### 元信息(预期)

| 项 | 值 |
|---|---|
| 全名 | `datacenter.lo_batch_equipment_performance_temp`(**可能带日期后缀如 `_20230530`,待业务确认**) |
| 类型 | Table |
| 拒片诊断中的角色 | `Tx` / `Ty` / `Rw` 改为从此表按一个月内最近行取值,而不是直接读 `failure_record_field` |

### 预期列

至少包含 performance 主表的核心列子集:

| 列名 | 类型 | 用途 |
|------|------|------|
| `equipment` | VARCHAR | linking |
| `lot_start_time` 或 `lot_end_time` | DATETIME | 时间窗右端,**待业务确认哪个是权威** |
| `wafer_translation_x` | DECIMAL | metric `Tx` |
| `wafer_translation_y` | DECIMAL | metric `Ty` |
| `wafer_rotation` | DECIMAL | metric `Rw` |

### 待确认

见 `docs/plans/2026-04-13-cowa-metric-source-fixes.md` Task 8 与 Open Questions §6/§7。

### 现状

- 未建表,未 mock,未在 diagnosis.json 引用
- 当前 `Tx/Ty/Rw` 从 performance 主表行直接取(`source_kind: failure_record_field`)
