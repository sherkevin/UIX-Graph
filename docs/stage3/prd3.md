# 拒片故障管理模块 - 后端设计文档

文档版本: 4.0
状态: 开发中
模块: 拒片故障管理 (Reject Failure Management) - 原因反馈功能

---

## 1. 引言

### 1.1 文档目的

本文档详细描述了拒片故障管理模块中"拒片故障报错的原因反馈"功能的 API 接口设计。该功能旨在提供高性能的筛选与查询能力，支持后端基于 Chuck, Lot, Wafer 等维度快速定位及分析拒片数据。

### 1.2 接口设计原则

* 高性能查询: 针对可能的大数据量场景，查询接口采用 `POST` 请求体传参，支持复杂的过滤条件，并配合分页机制。
* 前端友好: 时间字段在 API 传输层统一使用 13 位 Unix 时间戳（毫秒），由前端根据业务需要进行格式化。
* 类型严谨: 前后端数据交互严格区分类型（如 ID 统一使用 `INT`，非字符串）。
* 一致性: 遵循系统通用的响应格式、错误码定义及 HTTP/JSON 规范。
* 胖服务端，瘦客户端: 数据处理逻辑（状态判定、异常置顶排序、分页）下沉到服务端，前端只负责渲染。

### 1.3 核心设计文档体系 (研发必读)

本模块业务逻辑较重，开发需结合以下四份文档形成闭环，请务必配套查阅：

1. **`prd3.md` (本文档)**：定义 API 交互规范、缓存策略及前后端契约。
2. **`data_source.md`**：定义底层取数溯源映射（接口字段对应底层 MySQL 哪张表）。
3. **`config/rules.json`**：COWA 拒片诊断决策树（目前仅支持 COARSE_ALIGN_FAILED）。
4. **`config/metrics.json`**：指标 → 数据源映射表（db_type/table_name/column_name）；对需按时间拉取历史数据的指标可配置 **`duration`（分钟）**，与接口 3 的基准时间 **T** 共同定义查询区间 **`[T - duration, T]`**（详见 §3.3.2）。

---

## 2. API 接口规范

### 2.1 通用规范

* 协议: HTTP
* 根路径: 默认 `/api/v1`
* 数据格式: `application/json` (遵循驼峰命名法)
* 字符编码: UTF-8
* 时间传输格式: 13 位 Unix 时间戳（毫秒），如 `1699596120000`

### 2.2 全局固定枚举定义 (机台列表)

* `equipment` (机台名称) 为系统固定资产，前后端交互及校验均基于以下白名单，无需查表：
`["SSB8000", "SSB8001", "SSB8002", "SSC8001", "SSC8002", "SSC8003", "SSC8004", "SSC8005", "SSC8006", "SSB8005"]`

### 2.3 HTTP 动词约束

| 动词 | 使用场景 | 参数传递方式 |
| --- | --- | --- |
| `GET` | 幂等的资源获取 | URL 路径参数 (Path Variable) 或 查询字符串 (Query String) |
| `POST` | 创建资源或复杂条件查询 | Request Body |

> 注意: 绝对禁止在 GET 请求中携带 Request Body。

### 2.4 请求与响应格式

全局统一的成功响应 (HTTP 2xx) 及标准分页 `meta` 结构：

```json
{
  "data": { ... },
  "meta": {
    "total": 156,
    "pageNo": 1,
    "pageSize": 20,
    "totalPages": 8
  }
}
```

### 2.5 空数组筛选条件处理规则

| 条件值 | 业务语义 | 后端处理方式 |
| --- | --- | --- |
| `null` 或 字段未传 | 不限制 / 默认全选 | 动态 SQL 忽略该条件 |
| `[]` 空数组 | 用户明确清空筛选 | Controller/Service 层直接返回 `data: []`，**不查 DB** |

### 2.6 时间字段存储与传输规约

1. **数据库底层存储**：`DATETIME(6)` 类型，保留微秒级精度。
2. **API 接口传输**：13 位 Unix 时间戳（毫秒级整型）。
3. **后端转换职责**：后端接收 13 位时间戳 → 转 datetime 查 DB → 查出后转回 13 位时间戳返回前端。

---

## 3. 接口定义

### 3.1 接口 1：获取筛选元数据

用于页面初始化时获取 Chuck、Lot、Wafer 的分层可选数据。**不同机台 + 时间下的下拉选项是动态的、实时的。**

* **请求方式**: `GET /reject-errors/metadata`
* **Query 参数**:

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| equipment | string | 是 | 机台名称，必须在枚举白名单内 |
| startTime | number | 否 | 查询起始时间（13 位时间戳），用于动态筛选 Chuck/Lot |
| endTime | number | 否 | 查询结束时间（13 位时间戳），用于动态筛选 Chuck/Lot |

* **Response (200 OK)**:

```json
{
  "data": [
    {
      "chuckId": 1,
      "chuckName": "Chuck 1",
      "availableLots": [
        {
          "lotId": 101,
          "lotName": "Lot A001",
          "availableWafers": [1, 2, 3, 4, 5]
        }
      ]
    }
  ]
}
```

### 3.2 接口 2：查询拒片故障记录

表格区数据查询接口，支持多维度筛选、分页与排序。

对于已被接口 3 诊断过的记录，会从缓存表 `rejected_detailed_records` 补充 `rootCause` 和 `system` 字段。未诊断的记录这两个字段为 `null`。

* **请求方式**: `POST /reject-errors/search`
* **Request Body**:

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| pageNo | integer | 是 | 1 | 页码 |
| pageSize | integer | 是 | 20 | 每页数量 |
| equipment | string | 是 | - | 机台名称 |
| chucks | int[] \| null | 否 | null | Chuck ID 列表 |
| lots | int[] \| null | 否 | null | Lot ID 列表 |
| wafers | int[] \| null | 否 | null | Wafer ID 列表 (1-25) |
| startTime | number \| null | 否 | null | 起始时间（13 位时间戳） |
| endTime | number \| null | 否 | null | 结束时间（13 位时间戳） |
| sortedBy | string | 否 | "time" | 排序字段 |
| orderedBy | string | 否 | "desc" | 排序方向 |

* **Response (200 OK)**:

```json
{
  "data": [
    {
      "id": 59,
      "failureId": 59,
      "chuckId": 1,
      "lotId": 101,
      "waferIndex": 7,
      "rejectReason": "COARSE_ALIGN_FAILED",
      "rejectReasonId": 6,
      "rootCause": "上片偏差异常",
      "time": 1736488500000,
      "system": "WS与WH分系统"
    }
  ],
  "meta": { "total": 22, "pageNo": 1, "pageSize": 20, "totalPages": 2 }
}
```

> **rootCause / system 的来源**：
> 用户点击某条记录的"详情"按钮后，接口 3 运行诊断引擎，结果缓存到 `rejected_detailed_records`。
> 之后接口 2 再次查询时，会从缓存表读取这两个字段。

### 3.3 接口 3：获取拒片故障详情（含指标诊断）

根据拒片故障记录 ID，获取该条故障的详细报错字段及所有关联的检测指标数据。

#### 3.3.1 诊断流程

```
用户点击"详情"按钮
     │
     ▼
GET /{id}/metrics
     │
     ├─ 查缓存表 rejected_detailed_records
     │   ├─ 命中 → 直接返回缓存数据
     │   └─ 未命中 → 继续
     │
     ├─ 查源表 lo_batch_equipment_performance
     │
     ├─ 判断 reject_reason_id 是否支持诊断
     │   ├─ reject_reason_id = 6 (COARSE_ALIGN_FAILED) → 运行诊断引擎
     │   └─ 其他 → 返回基础信息，metrics=[]
     │
     ├─ 诊断引擎执行:
     │   1. 从源记录获取 Tx, Ty, Rw (MySQL)
     │   2. 从 ClickHouse 获取 Mwx_0 等指标 (本地 mock)
     │   3. 按 rules.json 决策树遍历
     │   4. 到达叶子节点 → 读取 rootCause, system
     │   5. 汇总所有指标的 {name, value, unit, status, threshold}
     │
     ├─ 写入缓存表
     │
     └─ 返回响应
```

#### 3.3.2 指标获取时间窗口与基准时间 T

由于当前没有 ID 一一对应关系，指标查询使用 **`equipment + 基准时间 T + 按指标 duration`** 定位 LOG / 时序数据：

- **基准时间 T**：
  - 由调用方通过 Query 参数 **`requestTime`** 传入（**13 位毫秒 Unix 时间戳**，可选）。
  - **未传 `requestTime`** 时，**T = 该条故障记录的 `wafer_product_start_time`**（与历史行为一致）。
- **按指标时间窗**：对 `metrics.json` 中配置了 **`duration`** 的指标（单位：**分钟**），查询时间区间为 **`[T - duration, T]`**，用于后续链路推断所需历史数据。
  - **`duration` 未配置**时，后端使用引擎构造参数中的 **`time_window_minutes` 作为回退**（当前服务层默认 5 分钟）。
  - **`db_type: intermediate`** 等中间量一般不配置 `duration`，不参与按窗查库。
- **缓存行为**：当 **`requestTime` 未传**，或与 **`wafer_product_start_time` 对应的毫秒时间戳相同**时，允许读写 `rejected_detailed_records`；**当 `requestTime` 与发生时间不一致**时，**不读、不写**该缓存表，避免以 `failure_id` 为主键的缓存被错误覆盖。
- **后续改进**: 当有精确 ID 对应关系后，可缩小或替换时间窗口查询逻辑。

#### 3.3.3 API 定义

* **请求方式**: `GET /reject-errors/{id}/metrics`
* **路径参数**: `id` (integer) - 故障记录 ID
* **Query 参数**:

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| requestTime | number | 否 | null | 分析基准时间 **T**（13 位毫秒时间戳）。未传则 T 取该条 `wafer_product_start_time`。与发生时间不一致时不走 `rejected_detailed_records` 缓存。 |
| pageNo | integer | 否 | 1 | 指标分页页码 |
| pageSize | integer | 否 | 20 | 指标分页大小 |

* **Response (200 OK)**:

```json
{
  "data": {
    "failureId": 59,
    "equipment": "SSB8000",
    "chuckId": 1,
    "lotId": 101,
    "waferIndex": 7,
    "errorField": "Tx",
    "rejectReason": "COARSE_ALIGN_FAILED",
    "rejectReasonId": 6,
    "rootCause": "上片偏差异常",
    "system": "WS与WH分系统",
    "time": 1736488500000,
    "metrics": [
      {
        "name": "Tx",
        "value": 25.5,
        "unit": "um",
        "status": "ABNORMAL",
        "threshold": { "operator": "between", "limit": [-20, 20] }
      },
      {
        "name": "Ty",
        "value": 3.2,
        "unit": "um",
        "status": "NORMAL",
        "threshold": { "operator": "between", "limit": [-20, 20] }
      },
      {
        "name": "Rw",
        "value": 150.0,
        "unit": "urad",
        "status": "NORMAL",
        "threshold": { "operator": "between", "limit": [-300, 300] }
      }
    ]
  },
  "meta": { "total": 8, "pageNo": 1, "pageSize": 20, "totalPages": 1 }
}
```

---

## 4. 后端架构

### 4.1 模块结构

```
src/backend/app/
├── engine/                         ← 诊断引擎
│   ├── rule_loader.py              ← 加载 rules.json + metrics.json
│   ├── metric_fetcher.py           ← 根据 metrics.json 从 DB 取指标值
│   └── diagnosis_engine.py         ← 执行决策树推理
│
├── handler/                        ← HTTP 路由层
│   └── reject_errors.py
│
├── service/                        ← 业务逻辑层
│   └── reject_error_service.py
│
├── ods/                            ← 数据源访问层
│   ├── datacenter_ods.py           ← MySQL
│   └── clickhouse_ods.py           ← ClickHouse (TODO)
│
├── models/                         ← ORM 模型
│   └── reject_errors_db.py
│
├── schemas/                        ← Pydantic 模型
│   └── reject_errors.py
│
└── utils/                          ← 工具函数
    └── time_utils.py
```

### 4.2 诊断引擎数据流

```
rules.json                    metrics.json
(决策树: steps + scenes)      (指标→数据源映射)
         │                          │
         ▼                          ▼
   RuleLoader ──────────────── MetricFetcher
         │                          │
         │    metric_values         │
         ▼         ↓                ▼
   DiagnosisEngine.diagnose(source_record)
         │
         ├─ 遍历决策树 (steps)
         ├─ 评估条件分支
         ├─ 到达叶子节点
         │
         ▼
   DiagnosisResult
   ├── rootCause: "上片偏差异常"
   ├── system: "WS与WH分系统"
   ├── errorField: "Tx"
   └── metrics: [{name, value, unit, status, threshold}, ...]
```

### 4.3 当前支持的诊断场景

| reject_reason_id | reject_reason_value | 诊断支持 | 说明 |
| --- | --- | --- | --- |
| 6 | COARSE_ALIGN_FAILED | ✅ 已实现 | COWA 倍率超限诊断 |
| 5001-5010 | 其他原因 | ❌ 暂不支持 | 返回基础信息，metrics=[] |

### 4.4 COWA 倍率超限诊断决策树 (rules.json)

```
Step 1: 判断 Mwx_0 值
├─ > 1.0001 或 < 0.9999 → Step 10 (建模 88um)
├─ between (1.00002, 1.0001) → Step 11 (建模 8um)
└─ else → Step 99 (人工处理)

Step 10/11: 建模 → 输出 Tx/Ty/Rw/Mw

Step 20: 检查温模次数 n_88um
├─ ≤ 8 → Step 21 (检查建模结果)
└─ > 8 → Step 30 (计算 Tx mean)

Step 21: 检查 output_Mw
├─ between (-20, 20) → Step 22, 23, 24 (并行检查 Tx/Ty/Rw)
└─ else → 继续建模

Step 22/23/24: 检查 Tx/Ty/Rw
├─ 正常 → Step 50 (汇总)
└─ 异常 → Step 30/31/32 (计算 mean)

Step 30/31/32: 计算 mean 值
├─ mean 正常 → 叶子节点 (rootCause=上片偏差/旋转异常, system=WS与WH分系统)
└─ mean 异常 → 叶子节点 (rootCause=上片工艺适应性问题)

Step 50: 汇总 → Step 99 (人工处理)
```

---

## 5. 错误码定义

| 错误码 | HTTP 状态码 | 描述 |
| --- | --- | --- |
| 30001 | 400 | 筛选条件无效 |
| 30002 | 404 | 查询不到相关的拒片记录 |
| 30003 | 500 | 数据库查询超时 |

---

## 6. 文档契约化说明

* 本接口文档使用 OpenAPI 3.0 标准维护，出入参数据类型严格依照文档执行。
