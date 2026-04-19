# 内网数据库元信息(供外网开发 mock)

本目录是**内网数据库的字段级权威参考**,用于外网开发时:

1. 写 mock SQL / mock fixture(`scripts/init_docker_db.sql`、`scripts/init_clickhouse_local.sql`)
2. 写新的诊断指标(`config/reject_errors.diagnosis.json` 的 `metrics.*.table_name / column_name / linking`)
3. 校对前后端字段命名(避免大小写、单复数、命名风格不一致)
4. 内网联调前自查 `linking.keys` / `extraction_rule` 是否真的对得上内网 DDL

> **权威级别**:本目录 > [`docs/intranet/schema_reference.md`](../schema_reference.md)(后者保留为历史,内容已收敛进本目录,后续以这里为准更新)。

---

## 1. 数据库一览

| 文件 | 数据库类型 | 数据库名 | 主要用途 | 本地 mock 状态 |
|------|-----------|---------|---------|---------------|
| [`mysql_datacenter.md`](./mysql_datacenter.md) | MySQL 8.0 | `datacenter` | 拒片故障主数据 + 诊断结果缓存 + 配置历史 | **有完整 mock**(`scripts/init_docker_db.sql`),覆盖 5 张表 |
| [`clickhouse_las.md`](./clickhouse_las.md) | ClickHouse | `las` | 设备日志类(`LOG_EH_UNION_VIEW` 是核心) | 有最小 mock,只插了 1 行触发样例 |
| [`clickhouse_src.md`](./clickhouse_src.md) | ClickHouse | `src` | WAA(Wafer Alignment Algorithm)对准/标记/SA 结果 | 有最小 mock,各表 1 行,与 docker-mysql 主表的 `(SSB8000, lot=101, chuck=1, wafer=7, T=2026-01-10 08:45)` 这个锚点对齐 |

> **内网真实表数**远不止上面这 3 个 db(还有 `sedc`、`prod`、`stage4` 计划接入的 `LO_wafer_result` 等),本目录会随业务推进**逐步补全**。所有"业务确认中"的列表见 [`../linking_tbd.md`](../linking_tbd.md)。

---

## 2. 用法:外网开发 mock 数据的标准流程

### 2.1 改一个诊断指标(已有表)

1. 打开本目录对应库的 markdown,找到表 → 找到列 → 抄列名/类型/含义
2. 改 `config/reject_errors.diagnosis.json` 里 `metrics.<metric_id>` 的 `table_name`、`column_name`、`extraction_rule`、`linking.keys/filters`
3. 如果该列在 `scripts/init_docker_db.sql` / `init_clickhouse_local.sql` 里**还没有建表或没插值**,补一行 `INSERT`,**值要和 docker MySQL 里的样例 `(SSB8000, 1, 101, 7, T=2026-01-10 08:45)` 这一锚点对齐**,否则 `linking.exact_keys` 拼出来的 SQL 永远空集
4. `cd src/backend && python -m pytest tests/test_metric_fetcher_window.py tests/test_diagnosis_config_store.py -q`
5. 启动后端 + 浏览器,跑一遍接口 3 详情页,确认 `metrics_data` 里这个 metric 不是 mock 也不是 None

### 2.2 加一张全新的内网表(未在本目录登记)

1. **先在本目录加文档**(本节这一段就是"先文档后代码"的契约入口)
2. 在对应 db 的 markdown 里追加表小节(模板见 §3)
3. 同步在 `scripts/init_docker_db.sql` / `init_clickhouse_local.sql` 里加 `CREATE TABLE` + 至少 1 行 `INSERT`
4. 如果是 MySQL 表,顺便补 `src/backend/app/models/<xxx>.py` 的 ORM 类
5. 然后才动 `config/reject_errors.diagnosis.json`

### 2.3 mock 数据的"锚点"约定

为了让所有 mock 之间能拼成一条**端到端可诊断的拒片样例**,我们约定:

| 字段 | 锚点值 | 含义 |
|------|--------|------|
| `equipment` | `SSB8000` | 机台 |
| `chuck_id` | `1` | Chuck |
| `lot_id` | `101` | Lot |
| `wafer_index` / `wafer_id` | `7` | Wafer |
| `wafer_product_start_time` (T) | `2026-01-10 08:45:00` | 故障基准时间 |
| `reject_reason` | `6` (`COARSE_ALIGN_FAILED`) | 触发 COWA 诊断场景 |
| `recipe_id` | `RCP-DOCKER-001` | 工艺配方 |

所有「时间窗类指标」(ClickHouse `LOG_EH_UNION_VIEW.detail` 等)的 `file_time` 都应该落在 `[T - 7天, T]` 之内才会被 `MetricFetcher` 取到。新加 mock 时,**优先把 `file_time` 设为 `2026-01-10 08:44:30 ~ 08:44:58`**(即 T 前 0~30 秒),保证 `nearest_in_window` 能命中。

---

## 3. 单表文档模板(每张表必填)

新增表时,在对应 db 文件里复制以下模板:

```markdown
## <table_name>

### 元信息

| 项 | 值 |
|---|---|
| 全名 | `<database>.<table_name>` |
| 类型 | Table / View / MaterializedView |
| 引擎 | InnoDB / MergeTree / ReplicatedMergeTree / … |
| 主键 / 唯一约束 | … |
| 主要时间列 | `<col>` |
| 主要关联键 | `equipment`, `lot_id`, `chuck_id`, `wafer_id` |
| 拒片诊断里的角色 | 主数据源 / 触发指标 / 取值指标 / 缓存表 / 仅触发用 |
| 内网负责人 | 待补 |

### 列定义

| # | 列名 | 类型 | 可空 | 业务说明 | 在诊断中怎么用 |
|---|------|------|------|---------|---------------|
| 1 | `xxx` | INT | NO | … | `metrics.<id>.linking.keys[].target` |
| ... | | | | | |

### 关联

- 与 `<other_table>` 的关联键: `<col>=<col>`
- 关联待业务确认: 见 [`../linking_tbd.md`](../linking_tbd.md) `<small section>`

### 诊断引擎引用

| metric_id | 用法 | linking | 提取 |
|-----------|------|---------|------|
| `Tx` | failure_record_field | — | 直接读 `wafer_translation_x` |

### Mock 建议(本地 docker)

\`\`\`sql
-- 锚点:SSB8000, chuck=1, lot=101, wafer=7, T=2026-01-10 08:45
INSERT INTO `<table>` (...) VALUES (...);
\`\`\`

### 引用位置(代码 / 配置)

- `scripts/init_docker_db.sql`(行号 / 段落)
- `src/backend/app/models/<file>.py`(类 / 方法)
- `src/backend/app/ods/<file>.py`(查询)
- `config/reject_errors.diagnosis.json`(metric_id 列表)
```

---

## 4. 与已有文档的关系

| 文档 | 用途 | 与本目录的关系 |
|------|------|----------------|
| [`docs/data_source.md`](../../data_source.md) | API 字段 → DB 字段映射(面向接口) | 仍保留;**只描述映射,不重复列定义** |
| [`docs/stage3/database_schema.md`](../../stage3/database_schema.md) | Stage3 拒片表的 DDL 历史方案 | 已归档为历史;DDL 以 `scripts/init_docker_db.sql` 为准 |
| [`../schema_reference.md`](../schema_reference.md) | 老版「内网字段标准参考」 | **已被本目录取代**,后续以本目录文件为准更新 |
| [`../linking_tbd.md`](../linking_tbd.md) | 「待业务确认」的关联清单 | 继续保留,本目录每张表的「关联」段落引用它 |
| [`docs/stage4/reject_errors_config_mapping.md`](../../stage4/reject_errors_config_mapping.md) | `reject_errors.diagnosis.json` 字段说明 | 仍保留;描述 JSON 字段语义,本目录描述底层 DB |

---

## 5. 维护人/审计

- 任何改动需要在 PR 描述里写**"内网 DDL 已二次核对"**
- 列名大小写、字符集、可空性必须与内网 `SHOW CREATE TABLE` 一致(已知 ClickHouse 视图列名常带大小写,如 `WS_pos_x`)
- 已确认列的`类型`列写**真实类型**;界面图标推断类型放进备注列,不要混
