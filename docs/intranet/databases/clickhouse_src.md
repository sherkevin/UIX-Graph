# ClickHouse `src`

> 内网 ClickHouse 实例下的 `src` 数据库,用于 **WAA(Wafer Alignment Algorithm)对准、标记、SA 结果**。
> 核心 metric:`ws_pos_x/y`、`mark_pos_x/y`、`Msx/Msy`、`e_ws_x/y`,COWA 建模链路的所有外部输入都在这里。

---

## 0. 数据库概要

| 项 | 值 |
|---|---|
| 数据库类型 | ClickHouse |
| 库名 | `src`(`src` = source/raw 数据,内网命名) |
| 在拒片诊断中的角色 | COWA 建模链 6 个外部输入(`ws_pos_x/y` `mark_pos_x/y` `Msx/Msy` `e_ws_x/y`)的来源 |

### 表清单

| 表名 | 类型 | 拒片诊断中的角色 | 本地 mock 完整度 |
|------|------|------------------|------------------|
| [`RPT_WAA_SET_OFL`](#rpt_waa_set_ofl) | **View** | `ws_pos_x` / `ws_pos_y` 来源(列名是 `WS_pos_x` 大写)+ 当前业务口径下也作为 `mark_pos_x/y` 来源 | 1 行 mock,与 docker-mysql 锚点对齐 |
| [`RPT_WAA_LOT_MARK_INFO_OFL_KAFKA`](#rpt_waa_lot_mark_info_ofl_kafka) | Table | 旧版 `mark_pos_x` / `mark_pos_y` 来源(已被 stage4 重路由)| 1 行 mock,但 diagnosis.json 已不指向 |
| [`RPT_WAA_SA_RESULT_OFL`](#rpt_waa_sa_result_ofl) | Table(Replicated*) | `Msx`、`Msy`、`e_ws_x`、`e_ws_y` 来源(SA = Stage Alignment) | 1 行 mock |
| `RPT_WAA_SET_UNION_VIEW` *(Stage4 候选)* | View | stage4 计划用作 `WS_pos_x/y` 的实际表(替代 `RPT_WAA_SET_OFL`) | **未 mock** |
| `RPT_WAA_V2_SET_OFL` *(Stage4 候选)* | Table | stage4 计划用作 `WS_pos_x/y` 的另一可选源 | **未 mock** |

---

## `RPT_WAA_SET_OFL`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `src.RPT_WAA_SET_OFL` |
| 类型 | **View**(内网),本地 mock 用 MergeTree 模拟 |
| 引擎(本地) | `MergeTree ORDER BY (equipment, file_time)` |
| 主要时间列 | `file_time`(`DateTime64(3, 'UTC')`) |
| 主要关联键 | `equipment`(`LowCardinality`)、`lot_id`(`Nullable Int32`)、`chuck_id`(`Nullable Int32`)、`wafer_id`(`Nullable Int32`)|
| 拒片诊断中的角色 | `ws_pos_x` / `ws_pos_y` + 当前 `mark_pos_x` / `mark_pos_y` 都从这里 |
| **关键提醒** | 列名是**驼峰大小写**`WS_pos_x` / `WS_pos_y`(不是全小写),`SHOW CREATE VIEW` 后必须**带反引号**写 |

### 列定义(内网 16 列)

| # | 列名 | ClickHouse 类型 | 业务说明 | 在诊断中怎么用 |
|---|------|----------------|---------|---------------|
| 1 | `lot_id` | `Nullable(Int32)` | Lot ID | `linking.keys[].target = "lot_id"` |
| 2 | `wafer_id` | `Nullable(Int32)` | Wafer ID(注意是 `Int32`,**不是字符串**)| `linking.keys[].target = "wafer_id"` |
| 3 | `chuck_id` | `Nullable(Int32)` | Chuck ID | `linking.keys[].target = "chuck_id"` |
| 4 | `scan_id` | `Nullable(Int32)` | 扫描 ID | 暂未使用 |
| 5 | `mark_id` | `Nullable(Int32)` | 标记 ID(stage4 候选过滤键) | 计划 `linking.filters` |
| 6 | `x_enable` | `Nullable(Int32)` | X 方向使能(0/1) | 暂未使用 |
| 7 | `y_enable` | `Nullable(Int32)` | Y 方向使能(0/1) | 暂未使用 |
| 8 | **`WS_pos_x`** | `Nullable(String)` | **WS 位置 X(字符串型!)** | metric `ws_pos_x` `column_name` |
| 9 | **`WS_pos_y`** | `Nullable(String)` | **WS 位置 Y(字符串型!)** | metric `ws_pos_y` `column_name` |
| 10 | `env_id` | `LowCardinality(String)` | 环境 ID | 暂未使用 |
| 11 | `equipment` | `LowCardinality(String)` | 机台名 | `linking.keys[].source = "equipment"` |
| 12 | `file_id` | `String` | 文件 ID | 暂未使用 |
| 13 | `row_id` | `String` | 行 ID | stage4 mark_id 路径里 `ORDER BY row_id ASC LIMIT 4` |
| 14 | `file_time` | `DateTime64(3, 'UTC')` | 时间(主时间列) | 时间窗右端 |
| 15 | `insert_time` | `DateTime64(3, 'UTC')` | 入库时间 | 暂未使用 |
| 16 | `partition_time` | `String` | 分区时间(字符串型) | 暂未使用 |

> **重点列**:`equipment`、`lot_id`、`chuck_id`、`wafer_id`、`WS_pos_x`、`WS_pos_y`、`file_time`,**任何 mock 都必须填**。

### 关联

- 与 `datacenter.lo_batch_equipment_performance` 的 `wafer_index`(int) ↔ `wafer_id`(`Nullable Int32`) 是否同语义,**待业务确认**(见 `linking_tbd.md`)
- 类型不一致:MySQL `lot_id` 是 INT,这里是 `Nullable(Int32)`;`MetricFetcher._build_linking_clauses` 在 ClickHouse 路径上对 `=`/`!=` 包了 `toString()` 兜底

### 诊断引擎引用

| metric_id | column_name | linking | duration | filter |
|-----------|-------------|---------|---------:|--------|
| `ws_pos_x` | `WS_pos_x` | `equipment`+`lot_id`+`chuck_id`+`wafer_id` | 7 天 | `phase = '1ST_COWA'` (注:本表无 `phase` 列?**待核对**) |
| `ws_pos_y` | `WS_pos_y` | 同上 | 7 天 | 同上 |
| `mark_pos_x` | `mark_pos_x` | `equipment`+`lot_id`+`chuck_id`+`wafer_id` | 7 天 | — |
| `mark_pos_y` | `mark_pos_y` | 同上 | 7 天 | — |

> ⚠️ **当前配置中存在不一致**:`config/reject_errors.diagnosis.json` 的 `ws_pos_x / ws_pos_y` 在 `linking.filters` 里加了 `phase = '1ST_COWA'`,但本表的内网列定义里**没有 `phase` 列**(SA 表才有)。这意味着:
> - **要么**目标表应改为 `RPT_WAA_SET_UNION_VIEW`(stage4 候选,有 phase 列)
> - **要么**这条 filter 在内网 SQL 里会触发 `Unknown identifier: phase` 报错,只能靠 mock 兜底
>
> 见 `linking_tbd.md` 与 `docs/plans/2026-04-13-cowa-metric-source-fixes.md` Task 2。

> ⚠️ **`mark_pos_x / mark_pos_y` 引用了本表 `mark_pos_x / mark_pos_y` 列**,但内网视图 schema 没有这两列。要么是配置写错(应使用 `RPT_WAA_LOT_MARK_INFO_*` 表的 `mark_pos_x/y`),要么内网视图实际有这两列(本地 mock 没建)。**强烈建议在内网 `SHOW CREATE VIEW` 一次以确认**。

### Mock 数据形态

```sql
INSERT INTO src.RPT_WAA_SET_OFL (
    lot_id, wafer_id, chuck_id, scan_id, mark_id, x_enable, y_enable,
    `WS_pos_x`, `WS_pos_y`,                  -- 注意反引号 + 大小写
    env_id, equipment, file_id, row_id, file_time, insert_time, partition_time
) VALUES (
    101, 7, 1, 0, 0, 1, 1,
    '0.11', '-0.22',                          -- 字符串型!引号包起来
    'local', 'SSB8000', 'seed-set', 'row-1',
    '2026-01-10 08:44:50.000', '2026-01-10 08:44:50.000', ''
);
```

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_clickhouse_local.sql` | L39–L65 |
| `src/backend/app/ods/clickhouse_ods.py` | `query_metric_in_window` |
| `config/reject_errors.diagnosis.json` | `metrics.{ws_pos_x, ws_pos_y, mark_pos_x, mark_pos_y}` |

---

## `RPT_WAA_LOT_MARK_INFO_OFL_KAFKA`

> ⚠️ **当前 diagnosis.json 已不再引用本表**(`mark_pos_x/y` 改用 `RPT_WAA_SET_OFL`)。本表保留 mock 仅供历史诊断路径回归。

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA` |
| 类型 | Table |
| 引擎(本地) | `MergeTree ORDER BY (equipment, file_time) SETTINGS allow_nullable_key = 1` |
| 主要时间列 | `file_time`(`DateTime64(3, 'UTC')`)|
| 主要关联键 | `equipment`、`lot_id`、`chuck_id`、`recipe_id` |

### 列定义(内网 14 列,均 Nullable)

| # | 列名 | 类型 | 业务说明 |
|---|------|------|---------|
| 1 | `lot_id` | `Nullable(String)` | Lot ID(注意:**字符串型**,与 SET_OFL 的 `Int32` 不同) |
| 2 | `chuck_id` | `Nullable(String)` | Chuck ID(字符串) |
| 3 | `mark_id` | `Nullable(String)` | 标记 ID |
| 4 | `mark_type` | `Nullable(String)` | 标记类型(如 `standard`) |
| 5 | `usage` | `Nullable(String)` | 用途(如 `align`) |
| 6 | `recipe_id` | `Nullable(String)` | 工艺配方 ID |
| 7 | `mark_pos_x` | `Nullable(String)` | 标记位置 X(字符串型) |
| 8 | `mark_pos_y` | `Nullable(String)` | 标记位置 Y(字符串型) |
| 9 | `env_id` | `Nullable(String)` | 环境 ID |
| 10 | `equipment` | `Nullable(String)` | 机台 |
| 11 | `file_id` | `Nullable(String)` | 文件 ID |
| 12 | `row_id` | `Nullable(String)` | 行 ID |
| 13 | `file_time` | `DateTime64(3, 'UTC')` | 时间 |
| 14 | `insert_time` | `DateTime64(3, 'UTC')` | 入库时间 |
| 15 | `partition_time` | `Nullable(String)` | 分区时间 |

> **注意类型差异**:本表所有 ID 都是 `Nullable(String)`,而 `RPT_WAA_SET_OFL` 是 `Nullable(Int32)`。跟 MySQL 主表的 INT `lot_id` 联调时,**ClickHouse 侧 SQL 必须 `toString` / `CAST`**(`MetricFetcher` 已经在 `_build_linking_clauses` 处理了)。

### Mock 数据形态

```sql
INSERT INTO src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA (
    lot_id, chuck_id, mark_id, mark_type, usage, recipe_id,
    mark_pos_x, mark_pos_y,
    env_id, equipment, file_id, row_id,
    file_time, insert_time, partition_time
) VALUES (
    '101', '1', 'm1', 'standard', 'align', 'RCP-DOCKER-001',
    '0.055', '-0.063',
    'local', 'SSB8000', 'seed-mark', 'row-1',
    '2026-01-10 08:44:55.000', '2026-01-10 08:44:55.000', ''
);
```

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_clickhouse_local.sql` | L67–L91 |

---

## `RPT_WAA_SA_RESULT_OFL`

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `src.RPT_WAA_SA_RESULT_OFL` |
| 类型 | Table |
| 引擎(内网) | Replicated*(本地用 `MergeTree ORDER BY (equipment, file_time)` 仿真) |
| 主要时间列 | `file_time` |
| 主要关联键 | `equipment`、`lot_id`(String)、`chuck_id`(String)、`wafer_id`(String) |
| 拒片诊断中的角色 | **SA(Stage Alignment)结果**——`Msx/Msy/e_ws_x/e_ws_y` 4 个 metric |

### 列定义(内网 16 列)

| # | 列名 | 类型 | 业务说明 | 在诊断中怎么用 |
|---|------|------|---------|---------------|
| 1 | `file_name` | `Nullable(String)` | 文件名 | 暂未使用 |
| 2 | `lot_id` | `Nullable(String)` | Lot ID(**String**) | linking |
| 3 | `lot_name` | `Nullable(String)` | Lot 名称 | 暂未使用 |
| 4 | `wafer_id` | `Nullable(String)` | Wafer ID(**String**) | linking |
| 5 | `chuck_id` | `Nullable(String)` | Chuck ID(**String**) | linking |
| 6 | `phase` | `Nullable(String)` | 阶段(如 `align`、`1ST_COWA`)| 候选固定 filter |
| 7 | `e_ws_x` | `Nullable(Float64)` | WS 误差 X | metric `e_ws_x` |
| 8 | `e_ws_y` | `Nullable(Float64)` | WS 误差 Y | metric `e_ws_y` |
| 9 | `ms_x` | `Nullable(Float64)` | **建模放大比 X**(注:diagnosis 配置里 metric_id 叫 `Msx`,但 column_name 是 `ms_x` 全小写)| metric `Msx` `column_name` |
| 10 | `ms_y` | `Nullable(Float64)` | **建模放大比 Y** | metric `Msy` `column_name` |
| 11 | `env_id` | `LowCardinality(String)` | 环境 ID | 暂未使用 |
| 12 | `equipment` | `LowCardinality(String)` | 机台 | linking |
| 13 | `file_id` | `String` | 文件 ID | 暂未使用 |
| 14 | `file_time` | `DateTime64(3, 'UTC')` | 时间 | 时间窗右端 |
| 15 | `insert_time` | `DateTime64(3, 'UTC')` | 入库时间 | 暂未使用 |
| 16 | `row_id` | `String` | 行 ID | 暂未使用 |

### 关联

- 与 `datacenter.lo_batch_equipment_performance` 的 `wafer_index`(int)↔ `wafer_id`(String)语义对齐**待确认**
- `linking_tbd.md` 已记录:同一 `(equipment, lot_id, chuck_id, wafer_id)` 在内网清单显示**返回多行**(可能是 `phase` 不同),需要业务侧补一个 disambiguator

### 诊断引擎引用

| metric_id | column_name | linking |
|-----------|-------------|---------|
| `Msx` | `ms_x` | `equipment`+`lot_id`+`chuck_id`+`wafer_id` |
| `Msy` | `ms_y` | 同上 |
| `e_ws_x` | `e_ws_x` | 同上 |
| `e_ws_y` | `e_ws_y` | 同上 |

### Mock 数据形态

```sql
INSERT INTO src.RPT_WAA_SA_RESULT_OFL (
    file_name, lot_id, lot_name, wafer_id, chuck_id, phase,
    e_ws_x, e_ws_y, ms_x, ms_y,
    env_id, equipment, file_id, file_time, insert_time, row_id
) VALUES (
    'sa_seed.tsv', '101', 'LOT101', '7', '1', 'align',
    -1.15, 2.34, 1.00005, 0.99996,
    'local', 'SSB8000', 'seed-sa',
    '2026-01-10 08:44:58.000', '2026-01-10 08:44:58.000', 'row-1'
);
```

### 引用位置

| 文件 | 位置 |
|------|------|
| `scripts/init_clickhouse_local.sql` | L93–L119 |
| `config/reject_errors.diagnosis.json` | `metrics.{Msx, Msy, e_ws_x, e_ws_y}` |

---

## `RPT_WAA_SET_UNION_VIEW` *(Stage4 候选)*

### 来源

`docs/plans/2026-04-13-cowa-metric-source-fixes.md` Task 2:
> 把 `WS_pos_x/y` 的 `table_name` 改为 `src.RPT_WAA_SET_UNION_VIEW`,加 `phase = '1ST_COWA'` 固定 filter。

### 与 `RPT_WAA_SET_OFL` 的关系

- 一般是 `*_UNION_VIEW` 是 `*_OFL` 的聚合视图(union 多个分表),列结构应基本一致
- **多了一列 `phase`**(关键!这就是为什么 stage4 把目标表切到 union view)

### 现状

- 未在 `init_clickhouse_local.sql` 建表
- diagnosis.json 当前 `ws_pos_x / ws_pos_y` 的 `table_name` 已经是 `src.RPT_WAA_SET_UNION_VIEW`(见 `_note`),但本地 mock 是 `RPT_WAA_SET_OFL` ⚠️ **本地诊断会查到空集**,只能靠 `mock_value` 兜底
- 待业务给出 DDL 后,在本目录与 `init_clickhouse_local.sql` 同步补全

### 建议下一步

1. 内网 `SHOW CREATE VIEW src.RPT_WAA_SET_UNION_VIEW`
2. 把 DDL 复刻到 `init_clickhouse_local.sql`
3. 在本文件加完整列定义
4. 把 mock INSERT 锚点对齐到 `(SSB8000, lot=101, chuck=1, wafer=7, phase='1ST_COWA', file_time=2026-01-10 08:44:50)`

---

## `RPT_WAA_V2_SET_OFL` *(Stage4 候选)*

### 来源

`docs/stage4/prd.md` §前置工作:
> "WS_pos_x"(WS大写)字段所在表修改为 clickhouse 里的 `src.RPT_WAA_V2_SET_OFL`

### 与 `RPT_WAA_SET_OFL` / `RPT_WAA_SET_UNION_VIEW` 的关系

- `V2` 后缀通常表示新版采集结构;列名/语义可能跟 V1 不完全一致
- stage4 给出的 V2 路径与 `2026-04-13-cowa-metric-source-fixes.md` 的 union_view 路径**不一致**——这是当前的悬而未决项,业务确认后才能定哪个为准

### 现状

- 未建表,未 mock
- 优先级低于 `RPT_WAA_SET_UNION_VIEW`(后者已写入 diagnosis.json `_note`)
