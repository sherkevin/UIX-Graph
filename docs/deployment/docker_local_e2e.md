# 外网本地：Docker 数据库替身 + 联调 / Chrome 验收

## 环境与边界（请先读）

| 环境 | 前后端 | 数据库 |
|------|--------|--------|
| **内网** | 可按内网部署方式运行前后端（可使用内网自己的 Docker/发布链路），但**不是**用本仓库这个 compose 起本地替身库 | 始终连接真实 MySQL、ClickHouse |
| **外网本地开发** | 本机 `npm run dev`（前端）+ `uvicorn`（后端） | 连不到内网库时，用本仓库 [`docker-compose.yml`](../../docker-compose.yml) **仅启动 MySQL + ClickHouse**，库名/表名与内网对齐并灌种子数据 |

**重要**：本仓库 `docker-compose.yml` 的职责仅限 **外网本地测试时提供数据库替身**。内网若使用 Docker，作用也是启动应用代码；数据库仍然是内网真实库，而不是这里的容器数据。

用于验证 [`config/reject_errors.diagnosis.json`](../../config/reject_errors.diagnosis.json) 在 **`METRIC_SOURCE_MODE=real`** 下接口 3 的指标值与种子一致，并做 FaultRecords 页面与 Network 验收。

**FaultRecords 时间窗与种子**：锚点拒片时间为 **2026-01-10**（见 §4）。若当前系统日期较晚，点「**最近 30 天**」得到的时间范围**可能不包含元月**，列表会为 0 条——属正常。请在时间范围中**手动包含 2026-01-01～2026-01-31**（或至少覆盖 2026-01-10）再点查询，才能看到种子行并验详情。

---

## 1. 启动数据库容器

仓库根目录：

```bash
docker compose up -d
```

- **MySQL**：`localhost:3307`，库 `datacenter`，首次启动执行 [`scripts/init_docker_db.sql`](../../scripts/init_docker_db.sql)。
- **ClickHouse**：`localhost:8123`，首次启动执行 [`scripts/init_clickhouse_local.sql`](../../scripts/init_clickhouse_local.sql)（`las` / `src`）。**说明**：compose **不再映射宿主 `9000→9000`**（部分 Windows 环境 `9000` 被系统保留会导致容器启动失败）；后端通过 **HTTP `8123`** 访问 ClickHouse 即可。

若 ClickHouse 未自动执行 init：

```bash
docker exec -i uix-clickhouse clickhouse-client --multiquery < scripts/init_clickhouse_local.sql
```

### 重置数据卷（曾用旧版 `wafer_id` 表结构时）

```bash
docker compose down -v
docker compose up -d
```

---

## 2. 库表覆盖（与内网同名）

权威字段说明见 [`docs/intranet/schema_reference.md`](../intranet/schema_reference.md)。

当前种子已覆盖拒片闭环最小集：

- **MySQL**：`reject_reason_state`、`lo_batch_equipment_performance`（`wafer_index`、`recipe_id`）、`rejected_detailed_records`、`mc_config_commits_history`
- **ClickHouse**：`las.LOG_EH_UNION_VIEW`，`src.RPT_WAA_SET_OFL`、`RPT_WAA_LOT_MARK_INFO_OFL_KAFKA`、`src.RPT_WAA_SA_RESULT_OFL`

`lo_batch_equipment_performance` 文档中 58–96 等列未全部建全，一般不影响当前诊断规则本地验证。

---

## 3. 后端环境变量与进程

```powershell
$env:APP_ENV = "local"
$env:METRIC_SOURCE_MODE = "real"
$env:UIX_ROOT = "D:\Codes\UIX-Graph"   # 改为你的仓库根
cd src/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd src/frontend && npm run dev
```

前端开发服务器默认将 `/api` 代理到 `http://localhost:8000`（见 `vite.config.js`）。详情页打开后仍会带 `requestTime`，与发生时间一致时也会**绕过缓存**重算指标（见 `reject_error_service.get_failure_details`）。

---

## 4. 锚点故障与期望值

种子对齐：**SSB8000 / chuck 1 / lot 101 / wafer_index 7 / reject_reason=6**，`wafer_product_start_time = 2026-01-10 08:45:00`。

| 指标名（API） | 种子来源 | 期望值（约） |
|---------------|----------|----------------|
| `Mwx_0` | `las.LOG_EH_UNION_VIEW.detail` | `1.00003` |
| `ws_pos_x` / `ws_pos_y` | `src.RPT_WAA_SET_OFL` | `0.11` / `-0.22` |
| `mark_pos_x` / `mark_pos_y` | `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA` | `0.055` / `-0.063` |
| `Msx` / `Msy` / `e_ws_x` / `e_ws_y` | `src.RPT_WAA_SA_RESULT_OFL` | `1.00005` / `0.99996` / `-1.15` / `2.34` |
| `Sx` / `Sy` | `mc_config_commits_history.data` | `0.001234` / `-0.005678` |

接口 3 的 **`meta`**：

- `total`：诊断类 + 建模参数合计条数。
- `metricDiagnosticTotal` / `metricModelParamTotal`：分项计数；**诊断指标表分页仅按诊断类切片**，建模参数在每页响应中完整附带（见详情 Modal 折叠区）。

---

## 5. Chrome DevTools 全面验收清单

在 **`http://localhost:3000/records`** 打开拒片页（路由见 [`App.jsx`](../../src/frontend/src/App.jsx)）。DevTools → **Network**，建议勾选 **Preserve log**。

### 5.1 筛选与元数据

1. 未选机台、未选时间：表格空状态文案合理；不应发 search。
2. 选择机台 **SSB8000**、时间范围覆盖 **2026-01-10**，点 **查询**。
3. 确认请求：
   - `GET /api/v1/reject-errors/metadata?equipment=SSB8000&...` → 200，响应为 Chuck→Lot→Wafer 结构。
   - `POST /api/v1/reject-errors/search` → 200，`data` 非空（种子足够时）。

### 5.2 列表

1. 分页：改页码后 `pageNo`/`pageSize` 与响应 `meta` 一致。
2. 排序：按时间 / 按 Reject Reason 列排序，请求中带 `sortedBy`/`orderedBy`，结果顺序变化合理。
3. **空数组短路**（可选）：若 API 支持 `chucks: []` 返回空列表，可在 Network 用 Replay 或临时改前端验证 `meta.total=0`。

### 5.3 详情 Modal（重点）

1. 点击某一行的 **详情**。
2. 确认 `GET /api/v1/reject-errors/{id}/metrics?requestTime=...&pageNo=1&pageSize=20`：
   - `data.failureId` / `rejectReason` / `time` 与列表行一致。
   - `data.rootCause`、`data.system`、`data.errorField` 存在且与诊断预期大致一致（锚点行可对照种子）。
3. **诊断指标表**（有阈值、`NORMAL`/`ABNORMAL`）：
   - 与种子表核对关键指标数值（尤其 `Mwx_0`、`ws_pos_*`、`mark_pos_*`、`Msx`/`Msy`、`Sx`/`Sy`）。
   - `ABNORMAL` 行排在前列（与后端排序一致，前端勿重算 status）。
4. **建模参数**折叠区：展示 `type === model_param'` 的项；数量应与 `meta.metricModelParamTotal` 一致。
5. **诊断指标数 / 分页**：
   - 文案 **「诊断指标数」** = `meta.metricDiagnosticTotal`。
   - 表脚 **「共 N 条诊断指标」** 的 N 与 `metricDiagnosticTotal` 一致。
   - 若诊断项数 > `pageSize`，翻页后第 2 页 `metrics` 中诊断类名称与第 1 页不重复；建模参数名称可在多页重复出现（设计如此）。

### 5.4 非法参数（可选）

在 Network 中重放：`GET .../metrics?requestTime=0` → 期望 **400**。

---

## 6. 自动化测试（可选）

```powershell
$env:DOCKER_E2E = "1"
$env:METRIC_SOURCE_MODE = "real"
$env:APP_ENV = "local"
$env:UIX_ROOT = "D:\Codes\UIX-Graph"
cd src/backend
python -m pytest tests/test_docker_seed_alignment.py tests/test_docker_e2e_extend.py -v --tb=short
```

未设置 `DOCKER_E2E=1` 时上述用例 **skip**。

---

## 7. 一键 HTTP 探测（可选）

[`scripts/verify_docker_e2e.ps1`](../../scripts/verify_docker_e2e.ps1)：解析锚点 `failure_id` 并请求接口 3（需后端已监听 `8000`）。
