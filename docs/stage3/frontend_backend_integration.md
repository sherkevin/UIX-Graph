# 前后端交互对照文档

文档版本: 3.0  
模块: 拒片故障管理 (FaultRecords 页面)  
更新时间: 2026-03-16  
状态: **✅ 三个接口全部已实现并联调**

---

## 1. 整体架构

```
前端 (Vite + React, :3000)
    │
    │  /api/* → 代理转发 (vite.config.js proxy)
    ▼
后端 (FastAPI, :8000)
    │
    ├─ handler/reject_errors.py        ← HTTP 路由层
    ├─ service/reject_error_service.py ← 业务逻辑层
    ├─ engine/                         ← 诊断引擎（接口3核心）
    │   ├─ rule_loader.py              ← 加载 structured pipeline 配置
    │   ├─ metric_fetcher.py           ← 从 DB 获取指标实际值
    │   └─ diagnosis_engine.py         ← 执行决策树推理
    ├─ ods/datacenter_ods.py           ← MySQL 查询层
    └─ MySQL Docker (localhost:3307/datacenter)
```

**时间约定（统一规范）**：
- 数据库存储：`DATETIME(6)`（微秒精度）
- 后端内部处理：Python `datetime` 对象
- 前后端传输：**13 位毫秒 Unix 时间戳**（`int`）
- 前端发送时间：`dayjs().valueOf()` → 毫秒
- 前端渲染时间：`dayjs(ms).format(...)` → 直接用毫秒构造

---

## 2. 页面布局与接口触发地图

```
┌──────────────────────────────────────────────────────────────────┐
│  SXEE-LITHO-RCA                                                  │
├──────────┬───────────────────────────────────────────────────────┤
│  故障记录 │  FaultRecords.jsx                                    │
│  (菜单)  │                                                       │
│          │  ┌──────────────────────────────────────────────────┐ │
│          │  │ 筛选区 (.filter-section)                         │ │
│          │  │                                                  │ │
│          │  │  [机台 Select]  [量产开始时间 RangePicker]       │ │  ← 触发接口1+2
│          │  │  [Chuck 多选]   [Lot/Wafer TreeSelect]          │ │  ← 触发接口2
│          │  └──────────────────────────────────────────────────┘ │
│          │                                                       │
│          │  ┌──────────────────────────────────────────────────┐ │
│          │  │ 故障记录表格 (Table)                              │ │
│          │  │  Chuck│LotId│Wafer│时间│原因│系统│根因│操作       │ │
│          │  │  ...  │ ... │ .. │... │... │...│... │[详情]      │ │  ← 触发接口3
│          │  │  分页控件 [< 1 2 3 ... >]                       │ │  ← 触发接口2
│          │  └──────────────────────────────────────────────────┘ │
│          │                                                       │
│          │  ┌──────────────────────────────────────────────────┐ │
│          │  │ Modal 弹窗（详情 - ID xxx）                      │ │
│          │  │  报错字段:...  发生时间:...                       │ │
│          │  │  故障根因:...  分系统:...   指标总数:...          │ │
│          │  │  [指标表格: 状态│指标名│指标值│阈值条件]          │ │
│          │  │  指标分页 [< 1 2 >]                              │ │  ← 服务端分页
│          │  └──────────────────────────────────────────────────┘ │
└──────────┴───────────────────────────────────────────────────────┘
```

---

## 3. 接口 1 — 获取筛选元数据

### 3.1 触发时机

| 触发场景 | 说明 |
|---------|------|
| **页面首次加载** | 用默认机台 SSB8000 调用一次 |
| **切换机台 或 时间范围变化** | `useEffect([selectedMachine, dateRange])` → 带 startTime/endTime 重新获取 |

### 3.2 请求详情

```
GET /api/v1/reject-errors/metadata?equipment=SSB8000&startTime=1736384400000&endTime=1736470800000
```

| 参数 | 说明 |
|-----|------|
| `equipment` | 机台名称 |
| `startTime` | 13位毫秒时间戳（可选） |
| `endTime` | 13位毫秒时间戳（可选） |

**关键**: 不同机台 + 时间下的 Chuck/Lot/Wafer 选项是实时动态的。

---

## 4. 接口 2 — 查询拒片故障记录

### 4.1 触发时机

| 触发场景 | 说明 |
|---------|------|
| 任意筛选条件变化 | 自动重置到第1页并查询 |
| 表格翻页 | 直接调用 fetchRecords |

### 4.2 rootCause / system 的来源

```
接口2返回 rootCause/system 的前提：
  用户先点击某条记录的"详情"→ 接口3运行诊断引擎 → 写入缓存表
  下次接口2查询时从缓存表补充 rootCause/system
  未被点击过详情的记录 → rootCause=null, system=null
```

---

## 5. 接口 3 — 获取故障详情（诊断引擎）

### 5.1 触发时机

| 触发场景 | 说明 |
|---------|------|
| 点击表格行的"详情"按钮 | `openDetail(record)` |
| Modal 指标翻页 | `handleMetricPageChange(page)` |

### 5.2 诊断引擎流程

```
GET /api/v1/reject-errors/{id}/metrics?pageNo=1&pageSize=20
    │
    ├─ 查缓存 rejected_detailed_records → 命中则直接返回（若带 requestTime 且与发生时间不一致则跳过缓存）
    │
    ├─ 未命中 → 查源表 lo_batch_equipment_performance
    │
    ├─ reject_reason_id = 6 (COARSE_ALIGN_FAILED)?
    │   ├─ YES → 运行诊断引擎:
    │   │   1. 从源记录获取 Tx, Ty, Rw
    │   │   2. 从 ClickHouse 获取 Mwx_0 等 (本地 mock)
    │   │   3. 遍历 `reject_errors.diagnosis.json` 中的决策树
    │   │   4. 叶子节点 → rootCause, system
    │   │   5. 构建 metrics 列表 (ABNORMAL 置顶)
    │   │   6. 写入缓存表
    │   │
    │   └─ NO → 返回基础信息, metrics=[]
    │
    └─ 返回响应
```

### 5.3 COARSE_ALIGN_FAILED 诊断结果示例

**Tx 超限 (>20um)**:
- rootCause: "上片偏差异常"
- system: "WS与WH分系统"
- errorField: "Tx"
- metrics: Tx=25.5 (ABNORMAL), Ty=3.2 (NORMAL), Rw=150.0 (NORMAL), ...

**Rw 超限 (>300urad)**:
- rootCause: "上片旋转异常"  
- system: "WS与WH分系统"
- errorField: "Rw"

**所有正常 → 人工处理**:
- rootCause: "需要人工处理"
- system: null

---

## 6. 完整交互时序

```
页面加载
  │
  ├─ [自动] GET metadata?equipment=SSB8000
  │         ↓ 返回 Chuck/Lot/Wafer 树 → 初始化筛选区（全选）
  │
  ├─ [自动] POST search
  │         ↓ 返回故障记录列表（rootCause/system 可能为 null）
  │
用户操作
  │
  ├─ 切换机台/时间 → GET metadata(新条件) → 更新筛选 → POST search
  │
  ├─ 修改 Chuck/Lot 筛选 → POST search
  │
  ├─ 点击"详情" → GET /{id}/metrics?requestTime=<行时间>&pageNo=&pageSize=
  │               ↓ requestTime 为可选；与列表行 `time` 一致时可走缓存
  │               ↓ 诊断引擎按 T 与 `reject_errors.diagnosis.json` 各指标 duration 取数 → 返回 rootCause + system + metrics
  │               ↓ 弹出 Modal (显示故障根因、分系统、指标列表)
  │               ↓ 满足缓存条件时诊断结果写入 rejected_detailed_records
  │
  └─ 再次搜索 → POST search
                 ↓ 已诊断的记录现在带有 rootCause 和 system
```

---

## 7. 快速启动

```bash
# 1. 确认 Docker MySQL 运行中
docker ps | grep uix-mysql

# 2. 启动后端
cd src/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 启动前端
cd src/frontend
npm run dev

# 4. 访问
http://localhost:3000

# 5. Swagger API 文档
http://localhost:8000/docs
```
