# Linking 待业务确认清单

与 [`schema_reference.md`](schema_reference.md) 中已核对字段区分：下列项依赖内网语义或缺失 DDL，**未写入** `config/reject_errors.diagnosis.json` 的 `linking.exact_keys`，或仅保留时间窗兜底。

| 数据源 | 待确认项 | 说明 |
|--------|----------|------|
| `datacenter.lo_batch_equipment_performance` ↔ `src.RPT_WAA_SET_OFL` | `wafer_index` 与 `wafer_id` | performance 为 `wafer_index`（int），SET 视图为 `wafer_id`（Nullable Int32）；是否同一语义、是否在 exact_keys 中映射，需工艺/数据侧确认。 |
| `las.LOG_EH_UNION_VIEW` | 与单次拒片的一一对应键 | 当前为时间窗 + `equipment`；是否可用 `process_id`、`source_file_name`、`system_event_code` 等与 performance 对齐，待确认。 |
| `datacenter.mc_config_commits_history` | 与机台、批次的关联 | 表无 `equipment`；是否用 `table_name`、`env_id`、`commit` 与故障上下文关联，是否增加 `linking.filters` / `filter_condition`，待内网规则。 |
| `src.RPT_WAA_SA_RESULT_OFL` ↔ performance | 键类型与 `wafer_id` 语义 | 表结构已写入 `schema_reference.md`；`exact_keys` 已用 `equipment`/`lot_id`/`chuck_id`/`wafer_id`。MySQL `lot_id`/`chuck_id` 为数值、CH 多为 String，是否需 CAST 需内网样例查询确认；`wafer_index` 是否应对 `wafer_id` 见下行。 |
| `datacenter.lo_batch_equipment_performance` | 序号 58–96 列 | 若后续规则依赖该区字段，需补 schema 与配置。 |
