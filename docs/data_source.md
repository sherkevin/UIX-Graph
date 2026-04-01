# 拒片故障管理模块 - 底层数据源映射规则 (Data Source)

文档版本: 4.0
描述: 本文档是对 `prd3.md` 中定义的 API 提供底层表结构的取数依据。

---

## 接口 1: 筛选元数据查询映射
对应 PRD 接口: `GET /reject-errors/metadata`

- **机台设备列表 (Equipment)**: 不查库，直接基于业务给定的 10 个固定枚举验证。
- **层级关联关系 (Chuck → Lot → Wafer)**:
  - 提取逻辑: 在给定 equipment 和时间范围内，查询该机台下的有效关联树。
  - `equipment(varchar)`: 前端传入的枚举值。
  - `startTime / endTime(datetime(6))`: 限定 `datacenter.lo_batch_equipment_performance.lot_start_time` / `lot_end_time` (mysql)
  - `chuckId(int)`: 对应底层 `datacenter.lo_batch_equipment_performance.chuck_id`
  - `lotId(int)`: 对应底层 `datacenter.lo_batch_equipment_performance.lot_id`
  - `waferId(int)`: 对应底层 `datacenter.lo_batch_equipment_performance.wafer_id`
  - **注意**: 不同机台 + 时间下的 Chuck/Lot/Wafer 组合是不同的（实时动态）

## 接口 2: 故障记录列表查询映射
对应 PRD 接口: `POST /reject-errors/search`

基础数据从源表 `lo_batch_equipment_performance` 查询，`rootCause` 和 `system` 从缓存表补充：

- `id(bigint)`: `datacenter.lo_batch_equipment_performance.id`
- `equipment(varchar)`: 前端固定枚举值
- `occurredAt(datetime(6))`: 底层为 `wafer_product_start_time`
- `chuckId(int)`: `chuck_id`
- `lotId(int)`: `lot_id`
- `waferIndex(int)`: `wafer_id`
- `rejectReasonId(bigint)`: `datacenter.lo_batch_equipment_performance.reject_reason`
- `rejectReason(varchar)`: 连表查询 `datacenter.reject_reason_state.reject_reason_value`
- `rootCause(varchar)`: 来源 `rejected_detailed_records.root_cause`（接口3诊断后缓存）
- `system(varchar)`: 来源 `rejected_detailed_records.system`（接口3诊断后缓存）

## 接口 3: 故障详细记录诊断提取映射
对应 PRD 接口: `GET /reject-errors/{id}/metrics`

### 3.1 基础字段

同接口 2 的源表字段。

### 3.2 诊断字段（仅 COARSE_ALIGN_FAILED, reject_reason_id=6）

- `rootCause(varchar)`: 诊断引擎遍历 `rules.json` 决策树到达叶子节点的 `result.rootCause`
- `system(varchar)`: 叶子节点的 `result.system`
- `errorField(varchar)`: 诊断路径中触发异常判断的 `metric_id` 列表，逗号分隔

### 3.3 指标数据 (metrics 数组)

指标值的获取遵循 `metrics.json` 配置：

| 指标 ID | 描述 | db_type | 数据表 | 列名 | 本地可用 |
| --- | --- | --- | --- | --- | --- |
| `Tx` | 上片偏差X | mysql | `lo_batch_equipment_performance` | `wafer_transaction_X` | ✅ 直接从源记录取 |
| `Ty` | 上片偏差Y | mysql | `lo_batch_equipment_performance` | `wafer_transaction_y` | ✅ 直接从源记录取 |
| `Rw` | 上片旋转 | mysql | `lo_batch_equipment_performance` | `wafer_rotation` | ✅ 直接从源记录取 |
| `Mwx_0` | 倍率实测值 | clickhouse | `las.LOG_EH_UNION_VIEW` | `detail` (regex) | ❌ 本地 mock |
| `ws_pos_x` | 标记对准位置X | clickhouse | `src.RPT_WAA_SET_OFL` | `ws_pos_x` | ❌ 本地 mock |
| `ws_pos_y` | 标记对准位置Y | clickhouse | `src.RPT_WAA_SET_OFL` | `ws_pos_y` | ❌ 本地 mock |
| `mark_pos_x` | 标记名义位置X | clickhouse | `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA` | `mark_pos_x` | ❌ 本地 mock |
| `mark_pos_y` | 标记名义位置Y | clickhouse | `src.RPT_WAA_LOT_MARK_INFO_OFL_KAFKA` | `mark_pos_y` | ❌ 本地 mock |
| `Msx` | 台对准建模结果 | clickhouse | `src.RPT_WAA_SA_RESULT_OFL` | `Msx` | ❌ 本地 mock |
| `Msy` | 台对准建模结果 | clickhouse | `src.RPT_WAA_SA_RESULT_OFL` | `Msy` | ❌ 本地 mock |
| `Sx` | 静态上片偏差X | mysql | `mc_config_commits_history` | `data` | ❌ 本地 mock |
| `Sy` | 静态上片偏差Y | mysql | `mc_config_commits_history` | `data` | ❌ 本地 mock |

### 3.4 时间窗口查询策略

由于目前 LOG 日志与拒片记录没有 ID 一一对应关系，使用 **`equipment + 基准时间 T + 按指标 duration`** 定位：

- **基准时间 T**：由接口 3 的 Query 参数 **`requestTime`**（13 位毫秒）传入；**未传**时 **T = `wafer_product_start_time`**。
- **按指标窗口**：`metrics.json` 中每个指标可选字段 **`duration`（分钟）**；配置了则查询 **`[T - duration, T]`** 内的数据。当前仓库对需查库的指标统一占位为 **1000 分钟**（见 `config/metrics.json`），生产可按指标调优。
- **回退**：某指标在 `metrics.json` 中**无 `duration`** 时，后端使用诊断引擎的 **`time_window_minutes`**（服务层当前默认 5）作为该指标的时间窗长度。
- **缓存**：仅当 **未传 `requestTime`** 或 **`requestTime` 等于** 该条 **`wafer_product_start_time` 的毫秒时间戳**时，读写 `rejected_detailed_records`；否则不读不写缓存。
- **后续改进**: 当有精确 ID 映射后，替换或缩小时间窗口查询

### 3.5 阈值与状态判定

阈值条件从 `rules.json` 的 steps 中提取：
- 找到 `metric_id` 匹配的 step
- 优先使用 `between` 类型条件作为正常范围
- 值在范围内 → `NORMAL`，超出 → `ABNORMAL`
- ABNORMAL 指标排序在返回数组头部
