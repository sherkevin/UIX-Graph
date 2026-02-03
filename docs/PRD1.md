# 拒片故障管理模块 - 后端设计文档

**文档版本**: 1.0
**状态**: 待开发
**模块**: 拒片故障管理 (Reject Failure Management) - 原因反馈功能

---

## 1. 引言

### 1.1 文档目的

本文档详细描述了拒片故障管理模块中“拒片故障报错的原因反馈”功能的API接口设计。该功能旨在提供高性能的筛选与查询能力，支持后端基于 Chunk, Lot, Wafer 等维度快速定位及分析拒片数据。

### 1.2 接口设计原则

* **高性能查询**: 针对可能的大数据量场景，查询接口采用 `POST` 请求体传参，支持复杂的过滤条件，并配合分页机制。
* **前端友好**: 时间字段统一使用 Unix 时间戳（秒），由前端根据业务需要进行格式化；列表支持分页与空状态处理。
* **一致性**: 遵循系统通用的响应格式、错误码定义及 HTTP/JSON 规范。

---

## 2. API 接口规范

### 2.1 通用规范

* **协议**: HTTP
* **根路径**: 默认 `/api/v1`
* **数据格式**: `application/json` (遵循驼峰命名法)
* **字符编码**: UTF-8
* **时间格式**: Unix 时间戳 (秒)

### 2.2 请求与响应格式

**成功响应 (HTTP 2xx):**

```json
{
  "data": { ... },       // 具体数据对象或数组
  "meta": {              // 分页及元数据信息
    "total": 100,
    "pageNo": 1,
    "pageSize": 20
  }
}

```

**失败响应 (HTTP 4xx 或 5xx):**

```json
{
  "error": {
    "code": 10001,       // 业务错误码
    "message": "...",    // 简短提示
    "details": "..."     // 详细调试信息
  }
}

```

---

## 3. 接口定义

### 3.1 获取筛选元数据 (前端 -> 后端)

用于页面初始化时获取 Chunk、Lot、Wafer 的可选列表，以填充筛选区的下拉框。

* **接口描述**: 获取当前系统中所有有效的 Chunk, Lot 及 Wafer 范围。
* **请求方式**: `GET`
* **URL**: `/reject-errors/metadata`
* **Query Params**: 无
* **Response (200 OK)**:
```json
{
  "data": {
    "availableMachines": ["C 1", "C 2"],
    "availableChunks": ["Chunk 1", "Chunk 2"],
    "availableLots": ["Lot A001", "Lot A002", "Lot B001"],
    "availableWafers": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25],
    "waferRange": {
      "min": 1,
      "max": 25
    }
  }
}

```



### 3.2 查询拒片故障记录

表格区数据查询接口，支持多维度筛选、分页与排序。

* **接口描述**: 根据 Chunk, Lot, Wafer 等条件查询拒片记录。筛选逻辑为“与 (AND)”关系。即返回同时满足所有指定条件的数据。若某筛选参数数组为空或 null，则视为忽略该条件（相当于全选）。
* **请求方式**: `POST`
* **URL**: `/reject-errors/search`
* **Request Body**:
```json
{
  "pageNo": 1,
  "pageSize": 20,
  "machine": "C1",
  "chunks": [],           // (可选) Chunk 列表，空数组或null表示不过滤
  "lots": [],             // (可选) Lot 列表
  "wafers": [],           // (可选) Wafer ID 数组，范围 1-25
  "errorCode": null,      // (可选) 精确匹配错误代码
  "startTime": null,      // (可选) 查询起始时间，Unix时间戳
  "endTime": null,        // (可选) 查询结束时间，Unix时间戳
  "sortedBy": "occurredAt", // (可选) 排序字段，默认按发生时间倒序
  "orderedBy": "desc"     // (可选) 排序方向
}

```


*参数逻辑说明：默认全选行为。为了配合前端“默认全选”的需求，当请求体中 chunks, lots, wafers 字段为空数组 [] 或 null 时，后端应返回所有相关数据，不做该维度的过滤。*
* **Response (200 OK)**:
```json
{
  "data": [
    {
      "id": 10245,
      "chunk": "Chunk 1",
      "lotId": "Lot A001",
      "waferIndex": 5,
      "errorCode": "MEASURE_FAILED",
      "errorReason": "Sensor calibration drift",
      "occurredAt": 1699596120,
      "system": "OPT"
    },
    {
      "id": 10246,
      "chunk": "Chunk 1",
      "lotId": "Lot A001",
      "waferIndex": 12,
      "errorCode": "ALIGNMENT_FAILED",
      "errorReason": "Sensor calibration drift",
      "occurredAt": 1699596000,
      "system": "WSA"
    }
  ],
  "meta": {
    "total": 156,
    "pageNo": 1,
    "pageSize": 20
  }
}

```



---

## 4. 诊断详情接口设计 (占位)

*(文档中显示该部分为标题，具体内容可能在后续开发中完善，目前主要依赖核心诊断逻辑)*

---

## 5. 错误码定义

| 错误码 (Code) | HTTP状态码 | 描述 (Description) |
| --- | --- | --- |
| **30001** | 400 | 筛选条件无效 (如 Wafer ID 超出 1-25 范围) |
| **30002** | 404 | 查询不到相关的拒片记录 |
| **30003** | 500 | 数据库查询超时 |

---

## 6. 前端交互时序图 (逻辑说明)

后端需支持以下交互流程：

1. **初始化**:
* 前端加载页面 -> 调用 `GET /reject-errors/metadata`。
* 后端返回 Chunk/Lot/Wafer 列表。


2. **默认加载**:
* 前端填充下拉框，默认触发“全选”状态。
* 前端调用 `POST /reject-errors/search`，Payload 中 chunks/lots 等为空。
* 后端识别为空，返回所有数据（全选结果）。


3. **用户筛选**:
* 用户修改筛选条件（如：取消 Chunk 1）。
* 前端调用 `POST /reject-errors/search`，Payload 中 `chunks: ["Chunk 2"]`。
* 后端执行过滤，返回筛选后数据。



---

## 7. 附录：核心诊断业务逻辑 (后端实现参考)

*(基于提供的Excel表格和复杂流程图截图，后端需实现以下故障归因逻辑)*

### 7.1 故障树与归因映射

后端需维护以下故障状态与子系统/原因的映射关系（Knowledge Graph 基础）：

* **COWA拒片 - 对准倍率超限**
* 原因分支：硅片质量问题 (翘曲/Mark问题)、WH异常 (Docking/预对准/交接)、WS异常 (控制性能/吸盘/上片偏差)。


* **COWA拒片 - 上片旋转超限**
* 原因分支：前层存在旋转、Mark质量不佳、WS硬件问题 (Docking plate/吸盘/Epin)、上片问题 (工艺适应性/标定问题)。


* **COWA拒片 - 2DC补偿/WA/WRS**
* 涉及子系统：WA (SBO异常/对准焦距)、WRS (扫描轨迹异常/振动)、WH (90度上片/跳点)。



### 7.2 诊断流程逻辑 (Decision Tree)

后端在处理“诊断”请求时，应遵循以下判断优先级：

1. **倍率检查 (Magnification)**:
* 判断 `M > 100ppm` 或 `20ppm < M < 100ppm`。
* 触发补做 COWA 建模逻辑。
* 检查温模次数与历史机台状态。


2. **偏差检查 (Deviation)**:
* 拉取 Layer 上片偏差值 vs 均值。
* 判定为“上片工艺适应性问题”或“分系统硬件异常(WS/WH)”。


3. **旋转检查 (Rotation)**:
* 拉取 Layer 上片旋转值 vs 均值。
* 判定为“工艺适应性(需旋转补偿)”或“分系统异常”。


4. **标记对准检查 (Alignment Mark)**:
* 检查 MCC 及 WQ 值。
* 若数值接近 0 -> 上片异常。
* 若数值异常非0 -> 人工处理。


5. **其他检查**:
* 建模残差、平移偏差、正交性等。

*(注：具体的诊断逻辑实现请参考配套的 `flow.json`, `node.json`, `compute.json` 文件，它们是该业务逻辑的代码化描述)*