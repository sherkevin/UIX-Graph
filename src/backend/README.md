<!--
 * @Author: shervin sherkevin@163.com
 * @Date: 2026-01-21 16:51:53
 * @Description: 后端 API 文档
-->

# 后端 API 文档

## 目录结构

```
src/backend/
├── app/
│   ├── handler/          # Handler 层（原 api/）- HTTP 路由 & 参数解析
│   │   ├── reject_errors.py   ★ 拒片故障管理（接口 1/2/3）
│   │   ├── diagnosis.py       诊断推理
│   │   ├── entity.py          实体详情
│   │   ├── full_graph.py      全图谱
│   │   ├── knowledge.py       知识录入
│   │   ├── ontology.py        本体管理
│   │   ├── propagation.py     故障传播
│   │   └── visualization.py   可视化
│   │
│   ├── service/          # Service 层 - 业务逻辑
│   │   └── reject_error_service.py  ★ 拒片故障业务逻辑
│   │
│   ├── engine/           # 拒片 pipeline 规则引擎（Stage3）
│   │   ├── diagnosis_engine.py   ★ 决策树执行、分支 outcome 日志
│   │   ├── condition_evaluator.py   条件表达式解析/求值（布尔 and/or 大小写不敏感）
│   │   ├── rule_validator.py     启动期校验（含 next 变量 Phase A）
│   │   ├── rule_loader.py
│   │   ├── metric_fetcher.py
│   │   └── actions/              内置 action 注册
│   │
│   ├── diagnosis/        # 配置加载（合并 pipeline + 调用 rule_validator）
│   │   └── config_store.py
│   │
│   ├── ods/              # ODS 层 - 数据源封装
│   │   ├── datacenter_ods.py  ★ MySQL datacenter 数据源
│   │   └── clickhouse_ods.py  ClickHouse 数据源
│   │
│   ├── models/           # Model 层 - ORM 表定义
│   │   ├── reject_errors_db.py  ★ 拒片相关表（源表 + 缓存表）
│   │   └── database.py          SQLite 旧版表（历史遗留）
│   │
│   ├── schemas/          # Schema 层 - Pydantic 请求/响应模型
│   │   ├── reject_errors.py  ★ 拒片接口 Schema
│   │   ├── diagnosis.py      诊断 Schema
│   │   └── ontology.py       本体 Schema
│   │
│   ├── core/             # Core 层 - 诊断引擎 & 图谱算法
│   │   ├── diagnosis_engine.py
│   │   ├── diagnosis_engine_prd1.py
│   │   ├── full_graph_builder.py
│   │   ├── graph_builder.py
│   │   ├── operators.py
│   │   ├── path_finder.py
│   │   └── test_data.py
│   │
│   ├── utils/            # Utils 层 - 工具函数
│   │   └── time_utils.py   时间戳 ↔ datetime 转换
│   │
│   └── main.py           # FastAPI 应用入口 & 路由注册
│
├── tests/                # 测试目录
│   ├── test_reject_errors.py  ★ 接口 1 & 2 完整测试套件
│   ├── test_rules_validator.py / test_rules_engine_conditions.py  规则校验与条件求值（无 DB）
│   ├── test_diagnosis_config_store.py
│   └── test_diagnosis_prd1.py   诊断引擎测试
│
├── requirements.txt      # 依赖清单
└── README.md             # 本文档
```

> ★ 标注为拒片故障管理模块（Stage 3）的核心文件。

### 拒片诊断配置契约（研发必读）

- 执行语义与校验清单：[docs/stage3/rules_execution_spec.md](../../docs/stage3/rules_execution_spec.md)（**v1.2**）。
- 要点：`steps[].next` **只写 `condition`**（勿用 JSON `operator`/`limit`）；布尔组合推荐 ` AND ` / ` OR ` 且 **大小写不敏感**；加载时对 `next` 中 **`{变量}`** 做 Phase A 可达性校验（与 `metrics`、step/scene `metric_id`、`set`、`details.results` 对齐）。
- 无法解析的原子条件在运行期会打 **warning** 日志（`condition_evaluator`），多分支冲突且无 `else` 时 **error** 日志（`diagnosis_engine`）。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Docker MySQL（本地开发）

> 本机 3306 端口若已被占用，使用 3307：

```bash
docker run -d --name uix-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=datacenter \
  -p 3307:3306 \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
```

初始化表结构与 Mock 数据：

```bash
docker cp scripts/init_docker_db.sql uix-mysql:/tmp/init_docker_db.sql
docker exec uix-mysql bash -c "mysql -u root -proot datacenter < /tmp/init_docker_db.sql"
```

### 3. 配置数据库连接

编辑 `config/connections.json`，确认 `local.mysql` 配置与你的 Docker 端口一致：

```json
{
  "local": {
    "mysql": {
      "host": "localhost",
      "port": 3307,
      "username": "root",
      "password": "root",
      "dbname": "datacenter"
    }
  }
}
```

### 4. 启动服务

```bash
cd src/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服务将在 http://localhost:8000 启动，Swagger 文档：http://localhost:8000/docs

---

## 运行测试

### 拒片故障管理 - 接口 1 & 2 测试

```bash
cd src/backend
python tests/test_reject_errors.py
```

测试覆盖场景：

| 测试函数 | 接口 | 场景 |
|---------|------|------|
| `test_metadata_basic` | 接口 1 | 基础查询，校验 Chuck/Lot/Wafer 层级结构 |
| `test_metadata_multiple_equipment` | 接口 1 | 多机台查询（SSB8001/SSC8001/SSB8005）|
| `test_metadata_invalid_equipment` | 接口 1 | 非法机台名称应抛出 ValueError |
| `test_metadata_time_filter` | 接口 1 | 时间范围筛选后数据量 ≤ 全量 |
| `test_search_basic` | 接口 2 | 基础全量查询，校验字段完整性 |
| `test_search_filter_chuck` | 接口 2 | 按 Chuck ID 筛选 |
| `test_search_filter_lot` | 接口 2 | 按 Lot ID 筛选 |
| `test_search_filter_wafer` | 接口 2 | 按 Wafer ID 筛选 |
| `test_search_filter_combined` | 接口 2 | Chuck + Lot 组合筛选 |
| `test_search_empty_array_intercept` | 接口 2 | `chucks/lots/wafers=[]` 直接返回空，不查 DB |
| `test_search_pagination` | 接口 2 | 分页正确，两页无重叠 |
| `test_search_deep_page_guard` | 接口 2 | pageNo 超出最大页数返回空数组 |
| `test_search_sort_desc` | 接口 2 | time desc 排序正确 |
| `test_search_sort_asc` | 接口 2 | time asc 排序正确 |
| `test_search_invalid_equipment` | 接口 2 | 非法机台抛出 ValueError |
| `test_search_invalid_wafer_range` | 接口 2 | wafer_id 超出 1-25 范围抛出 ValueError |
| `test_search_null_filters_means_all` | 接口 2 | null 筛选条件等价于全选 |

### 诊断引擎测试

```bash
cd src/backend
python tests/test_diagnosis_prd1.py
```

### 拒片规则与条件表达式（无数据库）

```bash
cd src/backend
python tests/test_rules_validator.py
python tests/test_rules_engine_conditions.py
# 或
pytest tests/test_rules_validator.py tests/test_rules_engine_conditions.py -q
```

---

## API 端点

### 拒片故障管理 (`/api/v1/reject-errors`)

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/v1/reject-errors/metadata` | 接口 1：获取 Chuck/Lot/Wafer 筛选元数据 |
| `POST` | `/api/v1/reject-errors/search` | 接口 2：查询拒片故障记录（分页 + 筛选） |
| `GET` | `/api/v1/reject-errors/{id}/metrics` | 接口 3：获取故障详情及指标数据 |

### 本体管理 (`/api/ontology`)

- `GET/POST /api/ontology/phenomena` - 故障现象
- `GET/POST /api/ontology/subsystems` - 分系统
- `GET/POST /api/ontology/components` - 部件
- `GET/POST /api/ontology/parameters` - 参数
- `GET/POST /api/ontology/rootcauses` - 根因

### 其他模块

- `GET/POST /api/knowledge/records` - 知识录入
- `POST /api/diagnosis/analyze` - 诊断推理
- `GET /api/visualization/graph` - 知识图谱
- `GET /api/propagation/{case_id}` - 故障传播路径
- `GET /api/entity/{entity_id}` - 实体详情
- `GET /api/graph/full-graph` - 全量图谱
