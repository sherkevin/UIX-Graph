# 拒片故障管理模块 - 未来改进计划

**文档版本**: 1.0
**创建日期**: 2026-03-13

---

## 1. 核心架构优化：读写解耦与异步计算

**优先级**: 高
**预计工作量**: 2-3 周
**依赖**: 消息队列基础设施、Canal 或类似 Binlog 监听工具

### 1.1 当前痛点

查询接口承载了"查源数据 -> 规则计算 -> 写入缓存 -> 返回结果"的繁重同步任务，高并发下极易引发：
- 缓存击穿
- 数据库连接池耗尽
- 响应时间不稳定

### 1.2 目标架构

将系统的"读路径"与"写路径"彻底分离，将故障归因（Decision Tree）变成异步过程。

#### 1.2.1 写入链路（异步预计算）

```
┌─────────────────────────────────────────────────────────────────┐
│  数据源变更                                                      │
│  (lo_batch_equipment_performance INSERT/UPDATE)                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  消息队列 (Message Queue)                                        │
│  方式一：Canal 监听 Binlog → Kafka/RocketMQ                      │
│  方式二：业务代码发送 MQ 消息                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  消费者服务 (Consumer Service)                                   │
│  1. 监听 MQ 消息                                                  │
│  2. 加载 `reject_errors.diagnosis.json` 进行规则推导             │
│  3. 计算 rootCause、system 及指标异常状态                         │
│  4. Upsert 到 rejected_detailed_records 表                       │
└─────────────────────────────────────────────────────────────────┘
```

**实现步骤**:
1. 部署 Canal 服务，配置监听 `datacenter` 数据库的 `lo_batch_equipment_performance` 表
2. 创建 Kafka/RocketMQ Topic，如 `reject-failure-calc`
3. 开发消费者服务，实现规则计算逻辑
4. 实现幂等性处理（同一故障 ID 的重复消息只处理一次）

#### 1.2.2 查询链路（纯只读）

```
┌─────────────────────────────────────────────────────────────────┐
│  前端请求                                                         │
│  (/search, /metrics)                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  API 网关 / Controller                                            │
│  只读 SQL 查询 rejected_detailed_records 表                      │
│  查不到即返回空集，严禁在查询请求中做树形规则运算和数据库写操作     │
└─────────────────────────────────────────────────────────────────┘
```

**接口行为规范**:
- `/search` 和 `/metrics` 接口变为**纯粹的只读接口**
- 接口只负责拼接 SQL 查询 `rejected_detailed_records` 表
- 查不到即返回空集
- **严禁在查询请求中做树形规则运算和数据库写操作**

### 1.3 短期过渡方案（当前版本）

若暂无法实现异步架构，当前版本采用以下措施：

#### 1.3.1 分布式锁保护

**实现方案**:
```python
# 伪代码示例
import redis

redis_client = redis.Redis(host='localhost', port=6379)

def query_failure_data(failure_id):
    # 1. 先查缓存
    cached = db.query("SELECT * FROM rejected_detailed_records WHERE failure_id = ?", failure_id)
    if cached and cached.metrics_data:
        return cached

    # 2. 尝试获取分布式锁
    lock_key = f"lock:failure:{failure_id}"
    lock_acquired = redis_client.set(lock_key, "1", nx=True, ex=10)  # 10 秒过期

    if lock_acquired:
        try:
            # 3. 双重检查缓存（防止其他线程已写入）
            cached = db.query("SELECT * FROM rejected_detailed_records WHERE failure_id = ?", failure_id)
            if cached and cached.metrics_data:
                return cached

            # 4. 从源表查询并计算
            raw_data = query_source_data(failure_id)
            calculated = calculate_with_rules(raw_data)

            # 5. 写入缓存
            save_to_cache(calculated)

            return calculated
        finally:
            # 6. 释放锁
            redis_client.delete(lock_key)
    else:
        # 7. 等待锁释放（轮询，最多 3 秒）
        for _ in range(30):
            time.sleep(0.1)
            cached = db.query("SELECT * FROM rejected_detailed_records WHERE failure_id = ?", failure_id)
            if cached and cached.metrics_data:
                return cached

        # 8. 超时返回错误
        raise TimeoutError("获取缓存数据超时")
```

**依赖组件**:
- Redis 实例（用于分布式锁）
- 锁超时时间：10 秒
- 轮询等待时间：最多 3 秒

---

## 2. API 与 RESTful 规范优化

**优先级**: 中
**预计工作量**: 1 周

### 2.1 当前痛点

- GET 请求带 Body
- 时间格式定义矛盾
- 入参定义不清晰

### 2.2 优化目标

严格规范 HTTP 动词的使用和数据交互标准。

#### 2.2.1 HTTP 动词约束

| 动词 | 使用场景 | 参数传递方式 | 禁止行为 |
| --- | --- | --- | --- |
| `GET` | 幂等的资源获取 | URL 路径参数或查询字符串 | 禁止携带 Request Body |
| `POST` | 创建资源或复杂条件查询 | Request Body | - |

#### 2.2.2 全局时间格式统一

- **API 边界（前后端交互）**: 统一采用 **13 位 Unix 时间戳（毫秒）**，如 `1666016625123`
- **数据库存储**: `DATETIME(6)` 格式
- **转换逻辑**:
  - 前端：负责将时间戳格式化为人类可读格式
  - 后端 DAO 层：负责时间戳与 DATETIME 的双向转换

**禁止在 API 传输中使用 `datetime(6)` 字符串格式**，消除跨时区和前端解析的隐患。

### 2.3 实施建议

1. 使用 Swagger / OpenAPI 3.0 定义接口契约
2. 配置前端请求库（如 Axios）统一处理时间戳转换
3. 后端添加全局时间格式转换器

---

## 3. 前后端协作职责重塑

**优先级**: 中
**预计工作量**: 1 周

### 3.1 当前痛点

诊断详情接口将大量的指标数据（Metrics）丢给前端，要求前端自行完成：
- 异常判断
- 状态置顶排序
- 分页处理

### 3.2 优化目标

遵循"胖服务端，瘦客户端"原则，数据处理逻辑必须下沉。

#### 3.2.1 状态判定下沉

后端在处理 `reject_errors.diagnosis.json` 时，直接根据阈值算好每个 metric 的 `status`：

```python
def calculate_status(value, operator, limit):
    if operator == "<=" and value > limit:
        return "ABNORMAL"
    elif operator == ">=" and value < limit:
        return "ABNORMAL"
    elif operator == "<" and value >= limit:
        return "ABNORMAL"
    elif operator == ">" and value <= limit:
        return "ABNORMAL"
    elif operator == "==" and value != limit:
        return "ABNORMAL"
    else:
        return "NORMAL"
```

前端只根据 `status` 字段渲染红/绿色。

#### 3.2.2 排序置顶下沉

后端在组装 Metrics 数组时，利用代码逻辑将 `status == 'ABNORMAL'` 的对象优先排序到数组头部：

```python
metrics.sort(key=lambda x: (0 if x['status'] == 'ABNORMAL' else 1))
```

#### 3.2.3 分页逻辑下沉

即便详情页的指标数据不走数据库物理分页，后端也应在内存中对排序好的数组进行 `slice(offset, limit)` 切割，配合 `pageNo` 和 `pageSize` 返回当前页数据。

```python
offset = (pageNo - 1) * pageSize
paged_metrics = all_metrics[offset : offset + pageSize]
```

前端只负责傻瓜式渲染，降低浏览器内存开销。

---

## 4. 数据库动态查询与边界防范

**优先级**: 高
**预计工作量**: 3-5 天

### 4.1 当前痛点

`chucks: []` 视为空或全选的定义模糊，极易引发 MyBatis 等 ORM 框架拼出 `WHERE chuck IN ()` 的致命 SQL 错误。

### 4.2 优化目标

在持久层严格区分 `null`、缺失键值与 `[]` 的业务语义。

#### 4.2.1 `null` 或字段未传（代表不限制 / 全选）

后端拦截器或动态 SQL 层直接**忽略该条件**，不拼接 `AND chuck IN (...)` 语句。

```xml
<!-- MyBatis 动态 SQL 示例 -->
<if test="chucks != null and chucks.length > 0">
    AND chuck_id IN
    <foreach item="chuck" collection="chucks" open="(" separator="," close=")">
        #{chuck}
    </foreach>
</if>
```

#### 4.2.2 `[]` 空数组（代表用户清空了筛选 / 查无结果）

后端开发应当在 Controller 层或 Service 层直接拦截此请求，**不发起任何数据库查询，直接 return 空结果集**。

```python
# 伪代码示例
def search RejectFailures(query):
    # 显式空数组检查
    if (query.chucks is not None and len(query.chucks) == 0) or \
       (query.lots is not None and len(query.lots) == 0) or \
       (query.wafers is not None and len(query.wafers) == 0):
        return {"data": [], "meta": {"total": 0, "pageNo": 1, "pageSize": 20}}

    # 正常查询逻辑
    ...
```

#### 4.2.3 深层分页防备

针对 `/search` 接口，若前端传入的 `pageNo` 远超实际数据的最大页码，后端直接返回空数组 `[]`，不要抛出异常。

---

## 5. 文档契约化管理

**优先级**: 中
**预计工作量**: 持续进行

### 5.1 当前痛点

PRD 中的 JSON 示例存在语法错误，无法被 Mock 平台或代码生成器解析。

### 5.2 优化目标

#### 5.2.1 使用 API 管理工具

- 摒弃纯文本 JSON
- 使用 Swagger / OpenAPI 3.0 通过代码注解直接生成 API 文档
- 或使用 Apifox / YApi 等工具维护接口契约

#### 5.2.2 Schema 校验

所有出入参必须定义严格的数据类型（Type）、是否必填（Required）和默认值（Default）。

**示例**:
```json
{
  "type": "object",
  "required": ["pageNo", "pageSize", "equipment"],
  "properties": {
    "pageNo": {
      "type": "integer",
      "minimum": 1,
      "default": 1
    },
    "chucks": {
      "type": "array",
      "items": { "type": "string" },
      "nullable": true,
      "description": "Chuck 列表，空数组表示查无结果"
    }
  }
}
```

---

## 6. 实施路线图

| 阶段 | 任务 | 优先级 | 预计工作量 |
| --- | --- | --- | --- |
| **Phase 1** | 分布式锁实现（短期过渡方案） | 高 | 3-5 天 |
| **Phase 1** | 空数组筛选条件拦截 | 高 | 1-2 天 |
| **Phase 2** | 状态判定、排序、分页逻辑下沉 | 中 | 1 周 |
| **Phase 2** | API 时间格式统一（13 位时间戳） | 中 | 3-5 天 |
| **Phase 3** | Swagger/OpenAPI 接口契约化 | 中 | 1 周 |
| **Phase 3** | Canal + MQ 异步预计算架构 | 高 | 2-3 周 |

---

## 7. 风险与注意事项

1. **异步架构的数据一致性问题**:
   - 从数据源变更到缓存生成存在延迟（秒级）
   - 需评估业务是否能容忍短暂的数据不一致

2. **分布式锁的可靠性**:
   - 需确保 Redis 高可用（哨兵或集群模式）
   - 锁超时时间需大于计算逻辑的最大执行时间

3. **规则文件变更的缓存刷新**:
   - `reject_errors.diagnosis.json` 变更时，需批量刷新缓存表
   - 可考虑使用版本号机制，避免全量刷新
