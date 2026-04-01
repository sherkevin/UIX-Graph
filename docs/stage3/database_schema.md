# 拒片故障管理模块 - 数据库表结构设计

**文档版本**: 1.0
**创建日期**: 2026-03-13

---

## 1. 表结构概述

### 1.1 源数据表

| 表名 | 用途 |
| --- | --- |
| `lo_batch_equipment_performance` | 存储 Lot-Batch-Chuck 设备性能原始数据 |
| `reject_reason_state` | 存储拒片原因枚举值映射 |

### 1.2 缓存表

| 表名 | 用途 |
| --- | --- |
| `rejected_detailed_records` | 存储接口 2 和接口 3 的查询结果，避免重复计算，提高查询性能 |

---

## 2. 源数据表设计

### 2.1 表名：`lo_batch_equipment_performance`

存储机台生产过程中的批次、性能、拒片等原始数据。

| 字段名 | 数据类型 | 约束 | 说明 | 用途 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | 故障记录 ID | 接口 2 和接口 3 的主键关联 |
| `equipment` | VARCHAR(50) | NOT NULL | 机台名称 | 枚举值：SSB8000~SSB8005, SSC8001~SSC8006 |
| `chuck_id` | INT | NOT NULL | Chuck ID | 筛选条件 |
| `lot_id` | INT | NOT NULL | Lot ID | 筛选条件 |
| `wafer_id` | INT | NOT NULL | Wafer ID (1-25) | 筛选条件 |
| `lot_start_time` | DATETIME(6) | DEFAULT NULL | Lot 开始时间 | 接口 1 时间范围筛选 |
| `lot_end_time` | DATETIME(6) | DEFAULT NULL | Lot 结束时间 | 接口 1 时间范围筛选 |
| `wafer_product_start_time` | DATETIME(6) | NOT NULL | Wafer 生产开始时间 | 接口 2 的 occurredAt 来源 |
| `reject_reason` | BIGINT | NOT NULL | 拒片原因 ID | 外键，关联 reject_reason_state.reject_reason_id |

> **注意**: 数据库中时间字段使用 `DATETIME(6)` 存储，但 API 接口返回时转换为 13 位 Unix 时间戳（毫秒）。

### 2.2 表名：`reject_reason_state`

存储拒片原因的枚举值定义。

| 字段名 | 数据类型 | 约束 | 说明 | 用途 |
| --- | --- | --- | --- | --- |
| `reject_reason_id` | BIGINT | PRIMARY KEY | 拒片原因 ID | 主键，关联 lo_batch_equipment_performance.reject_reason |
| `reject_reason_value` | VARCHAR(50) | NOT NULL | 拒片原因值 | 如 "MEASURE_FAILED", "ALIGNMENT_FAILED" 等 |

---

## 3. 缓存表设计

### 3.1 表名：`rejected_detailed_records`

存储拒片故障记录及其详细指标数据。

| 字段名 | 数据类型 | 约束 | 说明 | 来源映射 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | 主键 ID | 自增主键 |
| `failure_id` | BIGINT | UNIQUE, NOT NULL | 故障记录 ID | `datacenter.lo_batch_equipment_performance.id` |
| `equipment` | VARCHAR(50) | NOT NULL | 机台名称 | `datacenter.lo_batch_equipment_performance.equipment` |
| `chuck_id` | INT | NOT NULL | Chuck ID | `datacenter.lo_batch_equipment_performance.chuck_id` |
| `lot_id` | INT | NOT NULL | Lot ID | `datacenter.lo_batch_equipment_performance.lot_id` |
| `wafer_id` | INT | NOT NULL | Wafer ID | `datacenter.lo_batch_equipment_performance.wafer_id` |
| `occurred_at` | DATETIME(6) | NOT NULL | 故障发生时间 | `datacenter.lo_batch_equipment_performance.wafer_product_start_time` |
| `reject_reason` | VARCHAR(50) | NOT NULL | 拒片原因 | `datacenter.reject_reason_state.reject_reason_value` |
| `reject_reason_id` | BIGINT | NOT NULL | 拒片原因 ID | `datacenter.lo_batch_equipment_performance.reject_reason` |
| `root_cause` | VARCHAR(255) | DEFAULT NULL | 根本原因 | `rules.json.steps.results.root_cause` |
| `system` | VARCHAR(50) | DEFAULT NULL | 所属分系统 | `rules.json.steps.results.system` |
| `error_field` | VARCHAR(255) | DEFAULT NULL | 报错字段 | `rules.json.steps.results.metric_id` 组合 |
| `metrics_data` | JSON | DEFAULT NULL | 指标数据 | 存储完整的指标数组，每个指标含 status 字段 |
| `created_at` | DATETIME(6) | DEFAULT CURRENT_TIMESTAMP(6) | 创建时间 | 系统自动生成 |
| `updated_at` | DATETIME(6) | DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) | 更新时间 | 系统自动生成 |

> **注意**: 数据库中 `occurred_at` 使用 `DATETIME(6)` 存储，但 API 接口返回时转换为 13 位 Unix 时间戳（毫秒）。

---

## 4. 索引设计

### 4.1 `lo_batch_equipment_performance` 表索引

| 索引名 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `PRIMARY` | `id` | PRIMARY KEY | 主键索引 |
| `IDX_equipment` | `equipment` | NORMAL | 机台查询优化 |
| `IDX_chuck_lot_wafer` | `chuck_id`, `lot_id`, `wafer_id` | COMPOSITE | 联合索引，用于多维度筛选 |
| `IDX_wafer_product_start_time` | `wafer_product_start_time` | NORMAL | 时间范围查询优化 |
| `IDX_lot_start_end_time` | `lot_start_time`, `lot_end_time` | COMPOSITE | 用于接口 1 的时间范围筛选 |
| `IDX_reject_reason` | `reject_reason` | NORMAL | 拒片原因 ID 查询优化 |

### 4.2 `reject_reason_state` 表索引

| 索引名 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `PRIMARY` | `reject_reason_id` | PRIMARY KEY | 主键索引 |

### 4.3 `rejected_detailed_records` 表索引

| 索引名 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `PRIMARY` | `id` | PRIMARY KEY | 主键索引 |
| `UK_failure_id` | `failure_id` | UNIQUE | 故障 ID 唯一索引，确保每条故障记录唯一 |
| `IDX_equipment` | `equipment` | NORMAL | 机台查询优化 |
| `IDX_occurred_at` | `occurred_at` | NORMAL | 时间范围查询优化 |
| `IDX_chuck_lot_wafer` | `chuck_id`, `lot_id`, `wafer_id` | COMPOSITE | 联合索引，用于多维度筛选 |
| `IDX_reject_reason` | `reject_reason` | NORMAL | 拒片原因查询优化 |

---

## 5. 字段设计说明

### 5.1 `metrics_data` 字段 (JSON 类型)

`metrics_data` 使用 JSON 类型存储变长指标数组，结构如下：

```json
[
  {
    "name": "Overlay_X",
    "value": 1.245,
    "unit": "nm",
    "status": "ABNORMAL",
    "threshold": {
      "operator": "<=",
      "limit": 0.80
    }
  },
  {
    "name": "Overlay_Y",
    "value": 0.550,
    "unit": "nm",
    "status": "NORMAL",
    "threshold": {
      "operator": "<=",
      "limit": 0.80
    }
  }
]
```

**设计理由**:
1. **变长数组**：每条故障记录关联的检测指标数量不固定（可能几条到几十条），JSON 数组可以灵活存储
2. **嵌套结构**：每个指标包含 name、value、unit、threshold、status 等属性，JSON 可以完整保留层级关系
3. **MySQL 支持**：MySQL 5.7+ 对 JSON 类型有良好支持，可以进行高效的查询和提取
4. **扩展性**：未来若需添加新的指标属性，无需修改表结构

**status 字段说明**:
- `NORMAL`: 指标值在阈值范围内
- `ABNORMAL`: 指标值超出阈值范围（后端根据 threshold.operator 和 threshold.limit 计算得出）

### 5.2 接口 3 返回字段覆盖检查

| 接口 3 返回字段 | 表字段 | 覆盖情况 |
| --- | --- | --- |
| `failureId` | `failure_id` | 完全覆盖 |
| `equipment` | `equipment` | 完全覆盖 |
| `chuck` | `chuck_id` | 完全覆盖 |
| `lotId` | `lot_id` | 完全覆盖 |
| `waferIndex` | `wafer_id` | 完全覆盖 |
| `errorField` | `error_field` | 完全覆盖 |
| `rejectReason` | `reject_reason` | 完全覆盖 |
| `rejectReasonId` | `reject_reason_id` | 完全覆盖 |
| `rootCause` | `root_cause` | 完全覆盖 |
| `system` | `system` | 完全覆盖 |
| `time` | `occurred_at` | 完全覆盖 |
| `metrics` | `metrics_data` | 完全覆盖 |
| `totalMetrics` | (计算字段) | 可通过 `JSON_LENGTH(metrics_data)` 计算得出 |

---

## 6. 缓存逻辑说明

### 6.1 缓存写入时机

1. **接口 2 查询时**：
   - 当用户通过筛选条件查询拒片故障记录时
   - 从原始数据源 (`datacenter.lo_batch_equipment_performance` 和 `datacenter.reject_reason_state`) 查询数据
   - 同时写入 `rejected_detailed_records` 表，`root_cause` 和 `system` 字段可能为空，需要后续计算

2. **接口 3 查询时**：
   - 当用户点击某条记录查看详情时
   - 从原始数据源和规则文件计算详细信息
   - 更新 `rejected_detailed_records` 表中对应 `failure_id` 的记录，填充 `error_field` 和 `metrics_data` 字段

### 6.2 缓存读取逻辑

```
查询流程：
1. 接收查询请求（按 failure_id 或其他筛选条件）
2. 先查询 rejected_detailed_records 表
3. IF 缓存中存在记录 THEN
     - 返回缓存数据
   ELSE
     - 从原始数据源查询
     - 计算所需字段（如 root_cause, system, metrics_data）
     - 写入 rejected_detailed_records 表
     - 返回查询结果
   END IF
```

### 6.3 缓存更新策略

| 场景 | 策略 |
| --- | --- |
| 数据源更新 | 当原始数据表 (`lo_batch_equipment_performance`, `reject_reason_state`) 更新时，同步或异步更新缓存表 |
| 规则文件更新 | 当 `rules.json` 更新时，批量刷新缓存表中的 `root_cause`, `system`, `metrics_data` 字段 |
| 缓存失效 | 可设置 TTL（如 24 小时），定期清理过期数据 |

---

## 7. SQL 建表语句

### 7.1 `lo_batch_equipment_performance` 表

```sql
CREATE TABLE IF NOT EXISTS `lo_batch_equipment_performance` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '故障记录 ID',
  `equipment` VARCHAR(50) NOT NULL COMMENT '机台名称',
  `chuck_id` INT NOT NULL COMMENT 'Chuck ID',
  `lot_id` INT NOT NULL COMMENT 'Lot ID',
  `wafer_id` INT NOT NULL COMMENT 'Wafer ID (1-25)',
  `lot_start_time` DATETIME(6) DEFAULT NULL COMMENT 'Lot 开始时间',
  `lot_end_time` DATETIME(6) DEFAULT NULL COMMENT 'Lot 结束时间',
  `wafer_product_start_time` DATETIME(6) NOT NULL COMMENT 'Wafer 生产开始时间',
  `reject_reason` BIGINT NOT NULL COMMENT '拒片原因 ID（外键）',

  INDEX `IDX_equipment` (`equipment`),
  INDEX `IDX_chuck_lot_wafer` (`chuck_id`, `lot_id`, `wafer_id`),
  INDEX `IDX_wafer_product_start_time` (`wafer_product_start_time`),
  INDEX `IDX_lot_start_end_time` (`lot_start_time`, `lot_end_time`),
  INDEX `IDX_reject_reason` (`reject_reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='机台生产过程中的批次、性能、拒片等原始数据表';
```

### 7.2 `reject_reason_state` 表

```sql
CREATE TABLE IF NOT EXISTS `reject_reason_state` (
  `reject_reason_id` BIGINT PRIMARY KEY COMMENT '拒片原因 ID',
  `reject_reason_value` VARCHAR(50) NOT NULL COMMENT '拒片原因值（如 MEASURE_FAILED）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='拒片原因枚举值定义表';
```

### 7.3 `rejected_detailed_records` 表

```sql
CREATE TABLE IF NOT EXISTS `rejected_detailed_records` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
  `failure_id` BIGINT NOT NULL COMMENT '故障记录 ID（关联源表 ID）',
  `equipment` VARCHAR(50) NOT NULL COMMENT '机台名称',
  `chuck_id` INT NOT NULL COMMENT 'Chuck ID',
  `lot_id` INT NOT NULL COMMENT 'Lot ID',
  `wafer_id` INT NOT NULL COMMENT 'Wafer ID',
  `occurred_at` DATETIME(6) NOT NULL COMMENT '故障发生时间',
  `reject_reason` VARCHAR(50) NOT NULL COMMENT '拒片原因值',
  `reject_reason_id` BIGINT NOT NULL COMMENT '拒片原因 ID',
  `root_cause` VARCHAR(255) DEFAULT NULL COMMENT '根本原因',
  `system` VARCHAR(50) DEFAULT NULL COMMENT '所属分系统',
  `error_field` VARCHAR(255) DEFAULT NULL COMMENT '报错字段',
  `metrics_data` JSON DEFAULT NULL COMMENT '指标数据（含 status）',
  `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',

  UNIQUE KEY `UK_failure_id` (`failure_id`),
  INDEX `IDX_equipment` (`equipment`),
  INDEX `IDX_occurred_at` (`occurred_at`),
  INDEX `IDX_chuck_lot_wafer` (`chuck_id`, `lot_id`, `wafer_id`),
  INDEX `IDX_reject_reason` (`reject_reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='拒片详细记录表 - 存储接口 2 和接口 3 的查询结果';
```

---

## 8. 示例数据

### 8.1 完整记录示例

```json
{
  "id": 1,
  "failure_id": 10245,
  "equipment": "C1",
  "chuck_id": 1,
  "lot_id": 101,
  "wafer_id": 5,
  "occurred_at": "2025-11-10 14:22:00.123456",
  "reject_reason": "MEASURE_FAILED",
  "reject_reason_id": 5001,
  "root_cause": "Sensor calibration drift",
  "system": "OPT",
  "error_field": "Overlay_X, Overlay_Y, Alignment_X_Dev",
  "metrics_data": [
    {
      "name": "Overlay_X",
      "value": 1.245,
      "unit": "nm",
      "threshold": {
        "operator": "<=",
        "limit": 0.80
      }
    },
    {
      "name": "Overlay_Y",
      "value": 0.550,
      "unit": "nm",
      "threshold": {
        "operator": "<=",
        "limit": 0.80
      }
    },
    {
      "name": "Alignment_X_Dev",
      "value": 15.000,
      "unit": "nm",
      "threshold": {
        "operator": ">=",
        "limit": 10.00
      }
    }
  ],
  "created_at": "2025-11-10 14:25:00.000000",
  "updated_at": "2025-11-10 14:25:00.000000"
}
```

### 8.2 接口 2 部分数据示例（仅基础字段）

```json
{
  "failure_id": 10245,
  "equipment": "C1",
  "chuck_id": 1,
  "lot_id": 101,
  "wafer_id": 5,
  "occurred_at": "2025-11-10 14:22:00.123456",
  "reject_reason": "MEASURE_FAILED",
  "reject_reason_id": 5001,
  "root_cause": "Sensor calibration drift",
  "system": "OPT"
}
```

### 8.3 接口 3 完整数据示例（包含 metrics_data）

```json
{
  "failure_id": 10245,
  "equipment": "C1",
  "chuck_id": 1,
  "lot_id": 101,
  "wafer_id": 5,
  "occurred_at": "2025-11-10 14:22:00.123456",
  "reject_reason": "MEASURE_FAILED",
  "reject_reason_id": 5001,
  "root_cause": "Sensor calibration drift",
  "system": "OPT",
  "error_field": "Overlay_X, Overlay_Y, Alignment_X_Dev",
  "metrics_data": [
    {
      "name": "Overlay_X",
      "value": 1.245,
      "unit": "nm",
      "threshold": {
        "operator": "<=",
        "limit": 0.80
      }
    },
    {
      "name": "Overlay_Y",
      "value": 0.550,
      "unit": "nm",
      "threshold": {
        "operator": "<=",
        "limit": 0.80
      }
    },
    {
      "name": "Alignment_X_Dev",
      "value": 15.000,
      "unit": "nm",
      "threshold": {
        "operator": ">=",
        "limit": 10.00
      }
    }
  ]
}
```

---

## 9. 接口与字段映射关系

### 9.1 接口 2 返回字段映射

| 接口 2 返回字段 | 缓存表字段 | 原始数据源 |
| --- | --- | --- |
| `id` | `failure_id` | `datacenter.lo_batch_equipment_performance.id` |
| `chuck` | `chuck_id` | `datacenter.lo_batch_equipment_performance.chuck_id` |
| `lotId` | `lot_id` | `datacenter.lo_batch_equipment_performance.lot_id` |
| `waferIndex` | `wafer_id` | `datacenter.lo_batch_equipment_performance.wafer_id` |
| `rejectReason` | `reject_reason` | `datacenter.reject_reason_state.reject_reason_value` |
| `rejectReasonId` | `reject_reason_id` | `datacenter.lo_batch_equipment_performance.reject_reason` |
| `rootCause` | `root_cause` | `rules.json` (计算得出) |
| `time` | `occurred_at` | `datacenter.lo_batch_equipment_performance.wafer_product_start_time` |
| `system` | `system` | `rules.json` (计算得出) |

### 9.2 接口 3 返回字段映射

| 接口 3 返回字段 | 缓存表字段 | 原始数据源 |
| --- | --- | --- |
| `failureId` | `failure_id` | 请求参数 |
| `equipment` | `equipment` | `datacenter.lo_batch_equipment_performance.equipment` |
| `chuck` | `chuck_id` | `datacenter.lo_batch_equipment_performance.chuck_id` |
| `lotId` | `lot_id` | `datacenter.lo_batch_equipment_performance.lot_id` |
| `waferIndex` | `wafer_id` | `datacenter.lo_batch_equipment_performance.wafer_id` |
| `errorField` | `error_field` | `rules.json` (计算得出) |
| `rejectReason` | `reject_reason` | `datacenter.reject_reason_state.reject_reason_value` |
| `rejectReasonId` | `reject_reason_id` | `datacenter.lo_batch_equipment_performance.reject_reason` |
| `rootCause` | `root_cause` | `rules.json` (计算得出) |
| `system` | `system` | `rules.json` (计算得出) |
| `time` | `occurred_at` | `datacenter.lo_batch_equipment_performance.wafer_product_start_time` |
| `metrics` | `metrics_data` | `rules.json` + 其他数据源 (计算得出) |
| `totalMetrics` | (计算字段) | `JSON_LENGTH(metrics_data)` |
