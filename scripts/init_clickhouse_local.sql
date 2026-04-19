-- ClickHouse 本地种子：与 scripts/init_docker_db.sql 中 COARSE 样例对齐
-- 锚点：SSB8000, chuck_id=1, lot_id=101, wafer_index=7, T=2026-01-10 08:45:00, recipe_id=RCP-DOCKER-001
-- 由 docker-compose 挂载到 docker-entrypoint-initdb.d 首次启动执行

CREATE DATABASE IF NOT EXISTS las;
CREATE DATABASE IF NOT EXISTS src;

CREATE TABLE IF NOT EXISTS las.LOG_EH_UNION_VIEW (
    machine_id Nullable(String),
    release_version Nullable(String),
    process_name Nullable(String),
    method_name Nullable(String),
    process_id Nullable(String),
    system_event_code Nullable(String),
    source_file_name Nullable(String),
    line_number Nullable(String),
    event_type Nullable(String),
    event_level Nullable(String),
    component_name Nullable(String),
    linked_component_name Nullable(String),
    linked_event_code Nullable(String),
    detail Nullable(String),
    repeat Nullable(Int32),
    env_id String,
    equipment LowCardinality(String),
    file_time DateTime64(3, 'UTC')
) ENGINE = MergeTree ORDER BY (equipment, file_time);

-- Mwx_0 倍率值样本(regex:Mwx\s*\(\s*([\d\.]+)\s*\) 捕获组 1)
INSERT INTO las.LOG_EH_UNION_VIEW (
    machine_id, release_version, process_name, method_name, process_id, system_event_code,
    source_file_name, line_number, event_type, event_level, component_name,
    linked_component_name, linked_event_code, detail, repeat, env_id, equipment, file_time
) VALUES (
    NULL, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, 'Mwx ( 1.00003 )', NULL, 'local', 'SSB8000', '2026-01-10 08:44:30.000'
);

-- 触发场景 1001 (COWA 倍率超限) 的关键日志行:
-- detail 必须包含 'Mwx out of range,CGG6_check_parameter_ranges',
-- trigger_log_mwx_cgg6_range 这条 trigger metric 才会评估为 true,COWA 诊断才会启动。
INSERT INTO las.LOG_EH_UNION_VIEW (
    machine_id, release_version, process_name, method_name, process_id, system_event_code,
    source_file_name, line_number, event_type, event_level, component_name,
    linked_component_name, linked_event_code, detail, repeat, env_id, equipment, file_time
) VALUES (
    NULL, NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, 'Mwx out of range,CGG6_check_parameter_ranges (Mwx=1.00012)',
    NULL, 'local', 'SSB8000', '2026-01-10 08:44:35.000'
);

CREATE TABLE IF NOT EXISTS src.RPT_WAA_SET_OFL (
    lot_id Nullable(Int32),
    wafer_id Nullable(Int32),
    chuck_id Nullable(Int32),
    scan_id Nullable(Int32),
    mark_id Nullable(Int32),
    x_enable Nullable(Int32),
    y_enable Nullable(Int32),
    `WS_pos_x` Nullable(String),
    `WS_pos_y` Nullable(String),
    env_id LowCardinality(String),
    equipment LowCardinality(String),
    file_id String,
    row_id String,
    file_time DateTime64(3, 'UTC'),
    insert_time DateTime64(3, 'UTC'),
    partition_time String
) ENGINE = MergeTree ORDER BY (equipment, file_time);

INSERT INTO src.RPT_WAA_SET_OFL (
    lot_id, wafer_id, chuck_id, scan_id, mark_id, x_enable, y_enable,
    `WS_pos_x`, `WS_pos_y`, env_id, equipment, file_id, row_id, file_time, insert_time, partition_time
) VALUES (
    101, 7, 1, 0, 0, 1, 1,
    '0.11', '-0.22', 'local', 'SSB8000', 'seed-set', 'row-1',
    '2026-01-10 08:44:50.000', '2026-01-10 08:44:50.000', ''
);

CREATE TABLE IF NOT EXISTS src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA (
    lot_id Nullable(String),
    chuck_id Nullable(String),
    mark_id Nullable(String),
    mark_type Nullable(String),
    usage Nullable(String),
    recipe_id Nullable(String),
    mark_pos_x Nullable(String),
    mark_pos_y Nullable(String),
    env_id Nullable(String),
    equipment Nullable(String),
    file_id Nullable(String),
    row_id Nullable(String),
    file_time DateTime64(3, 'UTC'),
    insert_time DateTime64(3, 'UTC'),
    partition_time Nullable(String)
) ENGINE = MergeTree ORDER BY (equipment, file_time) SETTINGS allow_nullable_key = 1;

INSERT INTO src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA (
    lot_id, chuck_id, mark_id, mark_type, usage, recipe_id, mark_pos_x, mark_pos_y,
    env_id, equipment, file_id, row_id, file_time, insert_time, partition_time
) VALUES (
    '101', '1', 'm1', 'standard', 'align', 'RCP-DOCKER-001', '0.055', '-0.063',
    'local', 'SSB8000', 'seed-mark', 'row-1', '2026-01-10 08:44:55.000', '2026-01-10 08:44:55.000', ''
);

CREATE TABLE IF NOT EXISTS src.RPT_WAA_SA_RESULT_OFL (
    file_name Nullable(String),
    lot_id Nullable(String),
    lot_name Nullable(String),
    wafer_id Nullable(String),
    chuck_id Nullable(String),
    phase Nullable(String),
    e_ws_x Nullable(Float64),
    e_ws_y Nullable(Float64),
    ms_x Nullable(Float64),
    ms_y Nullable(Float64),
    env_id LowCardinality(String),
    equipment LowCardinality(String),
    file_id String,
    file_time DateTime64(3, 'UTC'),
    insert_time DateTime64(3, 'UTC'),
    row_id String
) ENGINE = MergeTree ORDER BY (equipment, file_time);

INSERT INTO src.RPT_WAA_SA_RESULT_OFL (
    file_name, lot_id, lot_name, wafer_id, chuck_id, phase,
    e_ws_x, e_ws_y, ms_x, ms_y, env_id, equipment, file_id, file_time, insert_time, row_id
) VALUES (
    'sa_seed.tsv', '101', 'LOT101', '7', '1', 'align',
    -1.15, 2.34, 1.00005, 0.99996, 'local', 'SSB8000', 'seed-sa',
    '2026-01-10 08:44:58.000', '2026-01-10 08:44:58.000', 'row-1'
);

-- ============================================================
-- src.RPT_WAA_SET_UNION_VIEW (stage4 候选,WS_pos_x/y 当前指向此表)
-- 与 RPT_WAA_SET_OFL 列结构一致,但额外有 phase 列(diagnosis.json 用 phase='1ST_COWA' filter)。
-- 内网真实是 View(union 多个分表),本地用 MergeTree 表仿真。
-- 详见 docs/intranet/databases/clickhouse_src.md "RPT_WAA_SET_UNION_VIEW" 段落。
-- ============================================================
CREATE TABLE IF NOT EXISTS src.RPT_WAA_SET_UNION_VIEW (
    lot_id Nullable(Int32),
    wafer_id Nullable(Int32),
    chuck_id Nullable(Int32),
    scan_id Nullable(Int32),
    mark_id Nullable(Int32),
    x_enable Nullable(Int32),
    y_enable Nullable(Int32),
    `WS_pos_x` Nullable(String),
    `WS_pos_y` Nullable(String),
    mark_pos_x Nullable(String),
    mark_pos_y Nullable(String),
    phase Nullable(String),                          -- 关键:union view 比 OFL 多这一列
    env_id LowCardinality(String),
    equipment LowCardinality(String),
    file_id String,
    row_id String,
    file_time DateTime64(3, 'UTC'),
    insert_time DateTime64(3, 'UTC'),
    partition_time String
) ENGINE = MergeTree ORDER BY (equipment, file_time);

-- 锚点对齐:SSB8000 / lot=101 / chuck=1 / wafer=7 / phase='1ST_COWA' / file_time 接近 T
INSERT INTO src.RPT_WAA_SET_UNION_VIEW (
    lot_id, wafer_id, chuck_id, scan_id, mark_id, x_enable, y_enable,
    `WS_pos_x`, `WS_pos_y`, mark_pos_x, mark_pos_y, phase,
    env_id, equipment, file_id, row_id, file_time, insert_time, partition_time
) VALUES (
    101, 7, 1, 0, 0, 1, 1,
    '0.11', '-0.22', '0.055', '-0.063', '1ST_COWA',
    'local', 'SSB8000', 'seed-union', 'row-1',
    '2026-01-10 08:44:50.000', '2026-01-10 08:44:50.000', ''
);
