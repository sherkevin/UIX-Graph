# 内网数据库字段标准（参考）

本文档汇总内网实际库表字段名与类型，供诊断配置 `linking`、`filter_condition` 及 ODS 对齐使用。  
**约定**：后续你每提供一张表，在本文件按「库.表名」新增一节，保持与内网 DDL 一致。

---

## `datacenter.lo_batch_equipment_performance`

**说明**：拒片故障主数据源；详情页 `failure_id`、机台/批次/wafer、Tx/Ty/Rw 等均来自此表。  
**来源**：内网字段清单（用户提供）。序号 58–96 在原表中未提供，此处留空待补。

| 列名 | 数据类型 |
| :--- | :--- |
| id | int |
| equipment | varchar(50) |
| lot_start_time | datetime(6) |
| lot_end_time | datetime(6) |
| seq_id_lo_wafer_mamsd_result | int |
| recipe_id | varchar(500) |
| layer_id | varchar(500) |
| lot_id | int |
| lot_name | varchar(500) |
| substrate_lot_id | varchar(500) |
| wafer_index | int |
| wafer_id | varchar(500) |
| chuck_id | int |
| wafer_translation_x | decimal(18,9) |
| wafer_translation_y | decimal(18,9) |
| wafer_expansion_x | decimal(18,9) |
| wafer_expansion_y | decimal(18,9) |
| wafer_rotation | decimal(18,3) |
| wafer_non_orthogonal | decimal(18,3) |
| std_wafer_translation_x | decimal(18,9) |
| std_wafer_translation_y | decimal(18,9) |
| std_wafer_rotation | decimal(18,3) |
| max_ws_x_ma | decimal(18,6) |
| max_ws_x_msd | decimal(18,6) |
| max_ws_y_ma | decimal(18,6) |
| max_ws_y_msd | decimal(18,6) |
| max_ws_rz_ma | decimal(18,9) |
| max_ws_rz_msd | decimal(18,9) |
| max_ws_z_ma | decimal(18,6) |
| max_ws_z_msd | decimal(18,6) |
| max_ws_x_total_ma | decimal(18,6) |
| max_ws_x_total_msd | decimal(18,6) |
| max_ws_y_total_ma | decimal(18,6) |
| max_ws_y_total_msd | decimal(18,6) |
| max_ws_z_total_ma | decimal(18,6) |
| max_ws_z_total_msd | decimal(18,6) |
| max_rs_x_ma | decimal(18,6) |
| max_rs_x_msd | decimal(18,6) |
| max_rs_y_ma | decimal(18,6) |
| max_rs_y_msd | decimal(18,6) |
| max_rs_rz_ma | decimal(18,9) |
| max_rs_rz_msd | decimal(18,9) |
| max_rs_diff_x_ma | decimal(18,6) |
| max_rs_diff_x_msd | decimal(18,6) |
| max_rs_diff_y_ma | decimal(18,6) |
| max_rs_diff_y_msd | decimal(18,6) |
| max_rs_diff_rz_ma | decimal(18,9) |
| max_rs_diff_rz_msd | decimal(18,9) |
| max_rs_z_ma | decimal(18,6) |
| max_rs_z_msd | decimal(18,6) |
| max_rs_rx_ma | decimal(18,9) |
| max_rs_rx_msd | decimal(18,9) |
| max_rs_ry_ma | decimal(18,9) |
| max_rs_ry_msd | decimal(18,9) |
| max_rs_x_total_ma | decimal(18,6) |
| max_rs_x_total_msd | decimal(18,6) |
| max_rs_y_total_ma | decimal(18,6) |
| *(序号 58–96：待补全)* | |
| lot_end_lens_temp | decimal(18,6) |
| lot_end_lens_pressure | decimal(18,6) |
| lot_start_lens_temp | decimal(18,6) |
| lot_start_lens_pressure | decimal(18,6) |
| dose_err_ilpe_min | decimal(18,9) |
| dose_err_ilpe_max | decimal(18,9) |
| dose_err_ilpe_mean | decimal(18,9) |
| dose_err_elpe_max | decimal(18,9) |
| dose_err_elpe_min | decimal(18,9) |
| dose_err_elpe_mean | decimal(18,9) |
| actual_energy | decimal(18,9) |
| focus_z | decimal(18,9) |
| image_size_x | decimal(18,9) |
| image_size_y | decimal(18,9) |
| creation_date | datetime |
| wafer_product_start_time | datetime(6) |
| wafer_state | bigint |
| reject_reason | bigint |
| insert_time | datetime |

### 与诊断上下文的对应关系（便于写 `linking.source`）

应用从该表加载故障行后，常用字段在内存中的键名与上表列名一致，例如：`equipment`、`chuck_id`、`lot_id`、`wafer_index`、`wafer_id`、`wafer_product_start_time`、`reject_reason`、`wafer_translation_x`、`wafer_translation_y`、`wafer_rotation` 等。

---

## `datacenter.reject_reason_state`

**说明**：拒片原因枚举；`lo_batch_equipment_performance.reject_reason` 与其 `reject_reason_id` 对应。列表/详情里 `rejectReason` 文案来自 `reject_reason_value`。  
**来源**：内网字段清单（用户提供）；类型列为 UI 推测，正式环境以 DDL 为准。

| 列名 | 数据类型 | 备注 |
| :--- | :--- | :--- |
| reject_reason_id | int | 主键或业务 ID，如 1、2、3… |
| reject_reason_value | varchar | 文本枚举，如 `NONE_REJECTED`、`COARSE_ALIGN_FAILED` |

---

## `datacenter.mc_config_commits_history`

**说明**：内网表**无** `equipment`、`committed_at`。仓库中 `Sx` / `Sy` 已对齐为：`time_column` = `last_modify_date`，`mysql_omit_equipment_filter` = true（WHERE 不再带机台条件），`extraction_rule` 仍为 `json:Sx` / `json:Sy`（仅 MySQL 路径）。与 performance 的 `table_name` / `env_id` 等关联见 [linking_tbd.md](linking_tbd.md)。  
**来源**：内网字段清单（用户提供）。

| 序号 | 列名 | 数据类型 |
| :--- | :--- | :--- |
| 1 | table_name | varchar(50) |
| 2 | last_modifier | varchar(50) |
| 3 | last_modify_date | varchar(50) |
| 4 | commit | varchar(50) |
| 5 | env_id | varchar(50) |
| 6 | data | longtext |
| 7 | id | int |

---

## `las.LOG_EH_UNION_VIEW`（ClickHouse）

**说明**：诊断里 `Mwx out of range...`、`Mwx_0` 等日志类指标从此表取 `detail`，时间列内网为 `file_time`，机台列为 `equipment`（与 `config/reject_errors.diagnosis.json` 中配置一致）。  
**来源**：内网字段清单（用户提供）；`推测实际数据类型` 列为工具图标推断，以 `SHOW CREATE TABLE` 为准。

| 序号 | 列名 | 界面显示数据类型 | 长度 | 推测实际数据类型 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | machine_id | Nullable | | Nullable(String) |
| 2 | release_version | Nullable | | Nullable(String) |
| 3 | process_name | Nullable | | Nullable(String) |
| 4 | method_name | Nullable | | Nullable(String) |
| 5 | process_id | Nullable | | Nullable(String) |
| 6 | system_event_code | Nullable | | Nullable(String) |
| 7 | source_file_name | Nullable | | Nullable(String) |
| 8 | line_number | Nullable | | Nullable(String) |
| 9 | event_type | Nullable | | Nullable(String) |
| 10 | event_level | Nullable | | Nullable(String) |
| 11 | component_name | Nullable | | Nullable(String) |
| 12 | linked_component_name | Nullable | | Nullable(String) |
| 13 | linked_event_code | Nullable | | Nullable(String) |
| 14 | detail | Nullable | | Nullable(String) |
| 15 | repeat | Nullable | 10 | Nullable(Int32) |
| 16 | env_id | String | | String |
| 17 | equipment | LowCardinality | | LowCardinality(String) |
| 18 | file_time | DateTime64 | 29 | DateTime64 |

**关联提示**：若要把日志与 `lo_batch_equipment_performance` 精确对齐，可优先核对是否可用 `process_id`、`source_file_name`、`system_event_code`、`linked_event_code` 等与 performance 或工艺上下文有对应关系的列，并在 `linking.keys` 中声明（`source` 为故障记录或扩展字段，`target` 为上表列名）。

---

## `src.RPT_WAA_SET_OFL`（ClickHouse，视图）

**表类型**：View（视图）。  
**说明**：诊断里 `ws_pos_x` / `ws_pos_y` 使用 `table_name: src.RPT_WAA_SET_OFL`；内网视图列为 **`WS_pos_x`、`WS_pos_y`**，时间列为 **`file_time`**。仓库配置已对齐上述列名与时间列，并对 `equipment` / `lot_id` / `chuck_id` 启用 `linking.exact_keys`（缺键时仍可按 `fallback.policy` 退回时间窗）。  
**来源**：内网字段清单（用户提供）；类型以 `SHOW CREATE VIEW` 为准。

| 序号 | 列名 | 界面显示数据类型 | 长度 | 推测实际数据类型 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | lot_id | Nullable | 10 | Nullable(Int32) |
| 2 | wafer_id | Nullable | 10 | Nullable(Int32) |
| 3 | chuck_id | Nullable | 10 | Nullable(Int32) |
| 4 | scan_id | Nullable | 10 | Nullable(Int32) |
| 5 | mark_id | Nullable | 10 | Nullable(Int32) |
| 6 | x_enable | Nullable | 10 | Nullable(Int32) |
| 7 | y_enable | Nullable | 10 | Nullable(Int32) |
| 8 | WS_pos_x | Nullable | | Nullable(String) |
| 9 | WS_pos_y | Nullable | | Nullable(String) |
| 10 | env_id | LowCardinality | | LowCardinality(String) |
| 11 | equipment | LowCardinality | | LowCardinality(String) |
| 12 | file_id | String | | String |
| 13 | row_id | String | | String |
| 14 | file_time | DateTime64 | 29 | DateTime64 |
| 15 | insert_time | DateTime | 29 | DateTime |
| 16 | partition_time | String | | String |

**关联提示**：与 `datacenter.lo_batch_equipment_performance` 对齐时，可尝试 `linking.keys`：`lot_id`↔`lot_id`、`chuck_id`↔`chuck_id`；`wafer_index`（performance）与视图 `wafer_id` 是否同一语义需你内网确认后再写映射。

---

## `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA`（ClickHouse）

**说明**：诊断里 `mark_pos_x` / `mark_pos_y` 使用 `table_name: src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA`，列名与下表一致。仓库配置中 `time_column` 已改为 **`file_time`**（内网清单无 `time` 列），并对 `equipment` / `lot_id` / `chuck_id` / `recipe_id` 启用 `linking.exact_keys`。  
**来源**：内网字段清单（用户提供）；类型按界面 `ABC` 图标统一推测为 `Nullable(String)`，实际可能含 `DateTime`/`LowCardinality` 等，以 DDL 为准。

| 序号 | 列名 | 界面显示数据类型 | 推测实际数据类型 |
| :--- | :--- | :--- | :--- |
| 1 | lot_id | Nullable | Nullable(String) |
| 2 | mark_id | Nullable | Nullable(String) |
| 3 | mark_type | Nullable | Nullable(String) |
| 4 | usage | Nullable | Nullable(String) |
| 5 | recipe_id | Nullable | Nullable(String) |
| 6 | mark_pos_x | Nullable | Nullable(String) |
| 7 | mark_pos_y | Nullable | Nullable(String) |
| 8 | env_id | Nullable | Nullable(String) |
| 9 | equipment | Nullable | Nullable(String) |
| 10 | file_id | Nullable | Nullable(String) |
| 11 | row_id | Nullable | Nullable(String) |
| 12 | file_time | Nullable | Nullable(String) |
| 13 | insert_time | Nullable | Nullable(String) |
| 14 | partition_time | Nullable | Nullable(String) |

**关联提示**：可与 performance 尝试 `lot_id`、`recipe_id` 等键；`mark_id` / `mark_type` / `usage` 是否与单次拒片事件一一对应需内网业务确认后再写入 `linking.keys`。

---

## `src.RPT_WAA_SA_RESULT_OFL`（ClickHouse）

**说明**：台对准结果表；引擎为 Replicated*（ClickHouse）。下列字段来自内网界面导出（图标含义：ABC→字符串、123→数值、时钟→时间）；**推测类型**以 `SHOW CREATE TABLE` 为准。

| 序号 | 列名 | 界面显示数据类型 | 长度 | 推测实际数据类型 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | file_name | Nullable | | Nullable(String) |
| 2 | lot_id | Nullable | | Nullable(String) |
| 3 | lot_name | Nullable | | Nullable(String) |
| 4 | wafer_id | Nullable | | Nullable(String) |
| 5 | chuck_id | Nullable | | Nullable(String) |
| 6 | phase | Nullable | | Nullable(String) |
| 7 | e_ws_x | Nullable | 25 | Nullable（数值型） |
| 8 | e_ws_y | Nullable | 25 | Nullable（数值型） |
| 9 | ms_x | Nullable | 25 | Nullable（数值型） |
| 10 | ms_y | Nullable | 25 | Nullable（数值型） |
| 11 | env_id | LowCardinality | | LowCardinality(String) |
| 12 | equipment | LowCardinality | | LowCardinality(String) |
| 13 | file_id | String | | String |
| 14 | file_time | DateTime64 | 29 | DateTime64 |
| 15 | insert_time | DateTime64 | 29 | DateTime64 |
| 16 | row_id | String | | String |

**诊断配置**（`config/reject_errors.diagnosis.json`）：指标 ID 仍为 `Msx`/`Msy`（流程内变量名），`column_name` 为内网列名 **`ms_x`** / **`ms_y`**；`e_ws_x`/`e_ws_y` 列名与表一致。`time_column` = `file_time`，`equipment_column` = `equipment`。`linking.exact_keys`：`equipment`、`lot_id`、`chuck_id`、`wafer_id`（与 `lo_batch_equipment_performance` 对齐；类型为 int vs String 时需在联调中验证）。

**关联待确认**：performance 的 `wafer_index` 与 SA 表 `wafer_id` 是否同语义 — 见 [linking_tbd.md](linking_tbd.md)。

---

## 后续追加

新表请继续在本文件追加小节，标题格式：`## <database>.<table_name>`。

**Linking 待确认项**（与已验证 DDL 分文件维护）：[linking_tbd.md](linking_tbd.md)。
