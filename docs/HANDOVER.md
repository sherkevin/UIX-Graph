# SXEE-LITHO-RCA（UIX）项目交接文档

**文档版本**: 1.1  
**更新日期**: 2026-03-25  
**适用范围**: 仓库根目录 `D:/Codes/UIX`（光刻机拒片根因分析系统）

> v1.1：补充「维护须知与已知边界」，收录代码走查结论，便于后续排坑。

---

## 1. 项目在做什么

本仓库 **SXEE-LITHO-RCA**（内部路径常标为 UIX）是一套 **光刻机拒片根因分析（Reject Cause Analysis）** 系统，主要能力包括：

- **知识图谱 / 本体 / 诊断推理（早期能力）**：FastAPI 提供 ontology、diagnosis、visualization、propagation 等路由，面向通用故障知识建模与推理。
- **Stage3 拒片故障管理（当前研发主线）**：在「机台 + 时间 + Chuck / Lot / Wafer」维度上查询 **拒片记录**，对特定拒片原因（当前实现为 **COARSE_ALIGN_FAILED，`reject_reason_id = 6`**）运行基于 **`config/rules.json`** 的决策树诊断，结合 **`config/metrics.json`** 从 MySQL / ClickHouse（后者本地多为 mock）拉取指标，将 **`rootCause`、`system`、指标明细** 写入缓存表 **`rejected_detailed_records`**，供列表接口展示与详情弹窗使用。

业务目标：帮助工程师快速定位拒片相关的数据上下文与规则化根因结论，并为后续异步预计算、真实 ClickHouse 连通等演进留接口。

---

## 2. 需求与任务来源

| 来源 | 内容 |
|------|------|
| [docs/stage3/prd3.md](stage3/prd3.md) | 拒片模块 API 契约：接口 1 元数据、接口 2 搜索、接口 3 详情+指标；时间戳规范、分页、`rootCause`/`system` 与缓存关系。 |
| [docs/data_source.md](data_source.md) | 各接口字段到 MySQL 表（以 `datacenter.lo_batch_equipment_performance` 为主）的映射；接口 3 指标与 `metrics.json` 的对应关系。 |
| [docs/stage3/database_schema.md](stage3/database_schema.md) | 相关表 DDL 与字段约定。 |
| [docs/stage3/feature_todo.md](stage3/feature_todo.md) | **未来改进**：读写解耦、MQ + 异步预计算、分布式锁、REST/时间格式统一、胖服务端分页与状态判定、OpenAPI 契约化等。 |
| [docs/stage3/frontend_backend_integration.md](stage3/frontend_backend_integration.md) | FaultRecords 页面与三接口的触发关系、联调说明。 |

---

## 3. 当前已完成内容（实现方式概要）

### 3.1 后端（Stage3）

- **路由**: [src/backend/app/handler/reject_errors.py](../src/backend/app/handler/reject_errors.py) — `GET .../metadata`、`POST .../search`、`GET .../{id}/metrics`。
- **业务层**: [src/backend/app/service/reject_error_service.py](../src/backend/app/service/reject_error_service.py) — 元数据/搜索/详情；空数组筛选短路；接口 3 诊断与缓存。
- **诊断引擎**: [src/backend/app/engine/](../src/backend/app/engine/) — `rule_loader.py` 加载 `rules.json` + `metrics.json`；`metric_fetcher.py` 按指标配置取数；`diagnosis_engine.py` 遍历决策树并组装 `metrics`（含 `status`、阈值、ABNORMAL 置顶）。
- **数据访问**: [src/backend/app/ods/datacenter_ods.py](../src/backend/app/ods/datacenter_ods.py) 等。
- **模型**: [src/backend/app/models/reject_errors_db.py](../src/backend/app/models/reject_errors_db.py) — 源表 + `rejected_detailed_records` 缓存表。

### 3.2 接口 3 扩展（本交接版本）

- **请求时间 `requestTime`（可选）**：13 位毫秒时间戳。未传或与该条 **`wafer_product_start_time`** 一致时，**仍走原缓存逻辑**；仅当传入的 `requestTime` **与** 记录发生时间**不一致**时，**不读、不写** `rejected_detailed_records`，避免错误缓存。
- **按指标时间窗**：对需按时间从库中查询的指标，使用 **`metrics.json` 中 `duration`（分钟）** 定义区间 **`[T - duration, T]`**，其中 **T** 为上述请求时间（未传则用记录上的发生时间）。

### 3.3 前端

- **主页面**: [src/frontend/src/pages/FaultRecords.jsx](../src/frontend/src/pages/FaultRecords.jsx) — 筛选、表格、详情 Modal、指标服务端分页。
- **API**: [src/frontend/src/services/api.js](../src/frontend/src/services/api.js) — `rejectErrorsAPI`；详情请求可带 `requestTime`（当前实现为传入行上的 `time`，与后端「与发生时间一致则走缓存」策略一致）。

### 3.4 测试

- [src/backend/tests/test_reject_errors.py](../src/backend/tests/test_reject_errors.py) — 接口 1、2 的集成测试（**依赖 MySQL**，未起库会连接失败，属环境原因）。
- [src/backend/tests/test_metric_fetcher_window.py](../src/backend/tests/test_metric_fetcher_window.py) — `MetricFetcher` 按 `duration` 计算 `[T-duration, T]` 的单元测试（**不依赖数据库**，适合 CI 常跑）。

### 3.5 配置与规则

- [config/rules.json](../config/rules.json) — 诊断决策树（当前场景对应 COARSE_ALIGN_FAILED）。
- [config/metrics.json](../config/metrics.json) — 指标 → 数据源映射；**`duration`（分钟）** 见下文第 7 节。
- [config/connections.json](../config/connections.json) — 数据库连接（如 `local` 下 MySQL 端口）。

---

## 4. 如何运行项目

### 4.1 数据库（Docker MySQL）

```bash
docker run -d --name uix-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=datacenter \
  -p 3307:3306 \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

docker cp scripts/init_docker_db.sql uix-mysql:/tmp/init.sql
docker exec uix-mysql bash -c "mysql -u root -proot datacenter < /tmp/init.sql"
```

连接信息需与 [config/connections.json](../config/connections.json) 中 `local.mysql` 一致（示例端口 **3307**）。

### 4.2 后端

```bash
cd src/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger: http://localhost:8000/docs  
- 健康检查: http://localhost:8000/health  

### 4.3 前端（约定入口）

```bash
cd src/frontend
npm install
npm run dev
```

访问 http://localhost:3000 ；`/api` 由 Vite 代理到后端（见 [src/frontend/vite.config.js](../src/frontend/vite.config.js)）。

### 4.4 测试命令

```bash
cd src/backend
python tests/test_metric_fetcher_window.py   # 无 MySQL 也可跑
python tests/test_reject_errors.py           # 需 MySQL 与 connections.json
python tests/test_diagnosis_prd1.py
```

---

## 5. 未来仍需完成的任务（摘要）

详见 [docs/stage3/feature_todo.md](stage3/feature_todo.md) 全文，优先级摘要如下：

| 方向 | 说明 |
|------|------|
| 架构 | 查询只读缓存表；诊断与写缓存迁到 MQ 消费者（Canal / 业务发消息）；接口 3 不在请求线程内重计算。 |
| 稳定性 | 分布式锁防缓存击穿；Redis 高可用。 |
| 数据 | ClickHouse 真实查询落地（当前大量指标为本地 mock）。 |
| 契约 | OpenAPI / Swagger 与 PRD 双轨一致；空数组、`pageNo` 越界等边界已在接口 2 部分落实，持续对齐文档。 |
| 性能 | `duration` 现为统一 **1000 分钟** 的占位，生产需按指标与索引情况调优。 |

---

## 6. 文档与目录全局说明

### 6.1 文档索引

| 路径 | 作用 |
|------|------|
| [README.md](../README.md) | 仓库总览、目录树、快速启动、关键接口表。 |
| **本文档 HANDOVER.md** | 交接用：目标、需求出处、完成度、运行方式、待办、`duration`/`requestTime` 约定；**第 9 章为维护排坑（路径、缓存、并发、测试）**。 |
| [docs/data_source.md](data_source.md) | 接口字段到数据库表的溯源；接口 3 指标与时间窗策略。 |
| [docs/stage3/prd3.md](stage3/prd3.md) | Stage3 API 设计权威说明。 |
| [docs/stage3/database_schema.md](stage3/database_schema.md) | 表结构 DDL。 |
| [docs/stage3/feature_todo.md](stage3/feature_todo.md) | 演进路线与风险。 |
| [docs/stage3/frontend_backend_integration.md](stage3/frontend_backend_integration.md) | 前后端联调与页面行为对照。 |
| [scripts/README.md](../scripts/README.md) | 数据处理脚本说明。 |
| [src/backend/README.md](../src/backend/README.md) | 后端模块结构与测试说明。 |

### 6.2 代码与配置目录（精简）

| 路径 | 作用 |
|------|------|
| `src/backend/app/` | FastAPI 应用：`handler`、`service`、`engine`、`ods`、`models`、`schemas`。 |
| `src/frontend/` | **约定主前端**（Vite + React）：FaultRecords、API 层。 |
| `frontend/`（若存在） | 可能与 `src/frontend` 重复；**交接约定以 `src/frontend` 与根 README 为准**，避免两处并行修改分叉。 |
| `config/` | `rules.json`、`metrics.json`、`connections.json`、`metrics_meta.yaml`。 |
| `scripts/` | `init_docker_db.sql`、数据合并与流程脚本等。 |
| `data/` | 图谱与 case 原始/合并数据（非 Stage3 运行时必需）。 |

---

## 7. 接口 3：`requestTime` 与 `metrics.json` 的 `duration`

### 7.1 业务含义

- **T**：分析基准时间。由调用方通过 **`GET .../reject-errors/{id}/metrics?requestTime=<13位毫秒>`** 传入；**不传**则 **T = 该条故障的 `wafer_product_start_time`**（与历史行为一致）。
- **按指标历史窗口**：对需要从日志/时序表查询的指标，取 **`[T - duration, T]`** 内的数据参与后续链路推断（与 PRD/数据源文档一致）。**`duration` 单位为分钟**。
- **默认值**：当前所有需要配置的历史窗指标在 [config/metrics.json](../config/metrics.json) 中统一为 **`"1000"`**（分钟），便于联调与占位；**`db_type: intermediate`** 及无表映射的中间量、占位项不配置 `duration`。

### 7.2 缓存约定（再次强调）

- **`requestTime` 未传**，或 **传入值等于** 该记录 **`wafer_product_start_time` 的毫秒时间戳**：允许读写 **`rejected_detailed_records`**（与旧逻辑一致）。
- **`requestTime` 与发生时间不一致**：**不读、不写**该缓存表，直接按 T 与 `duration` 计算并返回，避免污染以 `failure_id` 为主键的缓存行。

### 7.3 配置片段示例

```json
"Msx": {
  "description": "台对准建模结果Msx",
  "db_type": "clickhouse",
  "table_name": "src.RPT_WAA_SA_RESULT_OFL",
  "column_name": "Msx",
  "duration": "1000"
}
```

---

## 8. 关键 API 一览

| 接口 | 方法 | 路径 |
|------|------|------|
| 1 | GET | `/api/v1/reject-errors/metadata` |
| 2 | POST | `/api/v1/reject-errors/search` |
| 3 | GET | `/api/v1/reject-errors/{id}/metrics`（可选 `requestTime`、`pageNo`、`pageSize`） |

更多字段与示例见 [docs/stage3/prd3.md](stage3/prd3.md)。

---

## 9. 维护须知与已知边界（排坑）

以下为对 Stage3 前后端与配置的走查结论，**按项知晓可避免常见误判**。

### 9.1 前后端路径是否对得上

- 前端 Axios `baseURL` 为 **`/api`**，请求路径为 **`/v1/reject-errors/...`**，拼起来即 **`/api/v1/reject-errors/...`**。
- 后端在 [src/backend/app/main.py](../src/backend/app/main.py) 中为拒片路由注册的 prefix 为 **`/api/v1/reject-errors`**，与上一致。
- 开发环境下 [src/frontend/vite.config.js](../src/frontend/vite.config.js) 将 **`/api`** 代理到 **`http://localhost:8000`**，因此不要省略代理直连 8000 又沿用 `/api` 前缀，除非另行配置 CORS 与 baseURL。

### 9.2 `requestTime` 与缓存：何时会绕过缓存

- 绕过缓存的条件是：**Query 里带了 `requestTime`，且其整数值 ≠ 本条记录 `wafer_product_start_time` 用 `datetime_to_timestamp` 算出的毫秒时间戳**。
- 当前 FaultRecords 列表行的 **`time`** 来自接口 2 的同一套 `datetime_to_timestamp(wafer_product_start_time)`，详情请求把 **`record.time`** 原样作为 `requestTime` 传回，**正常情况下与后端比较值一致，不会误绕过缓存**。
- **易踩坑场景**：第三方客户端、Postman 手写 `requestTime`、或列表数据与详情不是同一字段/同一套时间换算时，可能出现「每次都绕过缓存」或「以为走了缓存实际未走」——排查时先核对两侧毫秒值是否完全一致。

### 9.3 时间戳容差与参数校验（当前未实现，可选增强）

- 当前为 **严格整数相等** 才视为「与发生时间一致」。若未来存在多条路径生成展示时间（舍入、时区、仅秒级精度等），可能出现 **个位数毫秒级差异** 导致误判为不一致并绕过缓存；如需可改为 **±1s（或 ±1000ms）内视为相等**（需改 [reject_error_service.py](../src/backend/app/service/reject_error_service.py) 比较逻辑并补测试）。
- **`requestTime` 极端值**（过大/过小）在转 `datetime` 时可能触发底层异常，表现为 **500**；若产品希望统一返回 **400**，可在 Handler 层对合理范围做校验。

### 9.4 缓存表唯一约束与并发

- 表 **`rejected_detailed_records`** 上 **`failure_id` 唯一**。同一 `failure_id` **首次**打开详情时，若两个请求并发都未命中缓存，可能两次都尝试 `INSERT`，**其中一个会因唯一约束失败**。
- [reject_error_service.py](../src/backend/app/service/reject_error_service.py) 中 **`_save_to_cache`** 已对写入失败做 **try/except + rollback**，**不向上抛出**，因此 **用户仍能拿到正确诊断结果**，只是该瞬间可能未写入缓存；后续再请求会重新计算或依赖另一方写入成功。高并发下若需更强保证，可改为 **upsert** 或分布式锁（与 [feature_todo.md](stage3/feature_todo.md) 中长期方案一致）。

### 9.5 双前端目录（再次强调）

- **唯一约定入口**：**[src/frontend/](../src/frontend/)**。根目录若存在 **`frontend/`**，且未同步 `rejectErrorsAPI`、`FaultRecords` 等 Stage3 代码，会出现「有人改 A 目录、有人跑 B 目录」的分叉。**新需求只改 `src/frontend`，并计划淘汰或合并根目录 `frontend/`**。

### 9.6 测试与根 README

- **无 MySQL** 时：`test_reject_errors.py` 报连接拒绝是预期现象，不代表业务逻辑必坏；可先跑 **`test_metric_fetcher_window.py`** 验证时间窗逻辑。
- 仓库根目录 **README.md** 在部分环境下为 **UTF-16 编码**，个别工具可能显示异常；**运行步骤与模块说明以本文 + [src/backend/README.md](../src/backend/README.md) 为准**。

### 9.7 `metrics.json` 与性能

- 全指标 **`duration: 1000` 分钟** 会放大 MySQL/ClickHouse 扫描范围；联调占位可接受，**上线前需按指标与索引单独调优**，并关注慢查询。

---

**交接确认**：接手人建议先通读 `prd3.md` + `data_source.md`，按第 4 节拉起 Docker、后端与 `src/frontend`，用 Swagger 与 FaultRecords 页各走通接口 1→2→3；若需改指标取数逻辑，同步修改 `metrics.json` 与 `metric_fetcher.py`。修改接口 3 缓存或 `requestTime` 行为前，**务必重读本章第 9.2～9.4 节**。
