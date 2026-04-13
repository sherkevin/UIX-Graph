# SXEE-LITHO-RCA

光刻机拒片根因分析系统（Reject Cause Analysis）

---

## 目录结构

```
UIX/
├── src/                          # 源代码（唯一代码目录）
│   ├── frontend/                 # 前端（React + Vite）
│   │   ├── src/
│   │   │   ├── pages/            # 页面级组件
│   │   │   │   ├── FaultRecords.jsx   ★ 拒片故障管理（Stage3 主页面）
│   │   │   │   └── FaultRecords.css
│   │   │   ├── components/       # 通用 UI 组件
│   │   │   │   ├── CustomSelect.jsx   多选下拉（Chunk 筛选器）
│   │   │   │   ├── EntityMetrics.jsx
│   │   │   │   ├── EntityPopover.jsx
│   │   │   │   ├── ErrorBoundary.jsx
│   │   │   │   ├── FaultPropagationGraph.jsx
│   │   │   │   ├── FullGraphView.jsx
│   │   │   │   ├── GraphSkeleton.jsx
│   │   │   │   └── LoadingProgress.jsx
│   │   │   ├── hooks/            # 自定义 Hook
│   │   │   │   ├── useApi.jsx         通用 API 调用 Hook
│   │   │   │   └── useCache.jsx       localStorage 缓存 Hook
│   │   │   ├── services/
│   │   │   │   └── api.js        ★ 统一 API 服务层（所有接口在此定义）
│   │   │   ├── config/
│   │   │   │   └── index.js      环境变量配置（baseURL、debug 等）
│   │   │   ├── App.jsx           路由根组件
│   │   │   ├── main.jsx          入口文件
│   │   │   └── index.css         全局样式
│   │   ├── package.json
│   │   └── vite.config.js        代理配置（/api → :8000）
│   │
│   └── backend/                  # 后端（Python FastAPI）
│       ├── app/
│       │   ├── handler/          # Handler 层 — HTTP 路由 & 参数解析
│       │   │   ├── reject_errors.py   ★ 拒片故障（接口 1/2/3）
│       │   │   ├── diagnosis.py
│       │   │   ├── entity.py
│       │   │   ├── full_graph.py
│       │   │   ├── knowledge.py
│       │   │   ├── ontology.py
│       │   │   ├── propagation.py
│       │   │   └── visualization.py
│       │   ├── service/          # Service 层 — 业务逻辑
│       │   │   └── reject_error_service.py  ★
│       │   ├── ods/              # ODS 层 — 数据源封装
│       │   │   ├── datacenter_ods.py   MySQL datacenter 查询
│       │   │   └── clickhouse_ods.py
│       │   ├── models/           # Model 层 — ORM 表定义
│       │   │   ├── reject_errors_db.py  ★
│       │   │   └── database.py
│       │   ├── schemas/          # Schema 层 — Pydantic 请求/响应模型
│       │   │   ├── reject_errors.py  ★
│       │   │   ├── diagnosis.py
│       │   │   └── ontology.py
│       │   ├── core/             # Core 层 — 诊断引擎 & 图算法
│       │   │   ├── diagnosis_engine.py
│       │   │   ├── diagnosis_engine_prd1.py
│       │   │   ├── full_graph_builder.py
│       │   │   ├── graph_builder.py
│       │   │   ├── operators.py
│       │   │   ├── path_finder.py
│       │   │   └── test_data.py
│       │   ├── utils/            # Utils 层 — 工具函数
│       │   │   └── time_utils.py
│       │   └── main.py           # FastAPI 应用入口 & 路由注册
│       ├── tests/
│       │   ├── test_reject_errors.py   ★ 接口 1 & 2 完整测试套件
│       │   └── test_diagnosis_prd1.py
│       ├── requirements.txt
│       └── README.md
│
├── config/                       # 全局配置（前后端共享）
│   ├── connections.json          数据库连接配置（local/test 环境）
│   ├── diagnosis.json            诊断 pipeline 索引（指向各 *.diagnosis.json）
│   ├── reject_errors.diagnosis.json  拒片诊断规则与指标（Stage3 主配置）
│   ├── ontology_api.diagnosis.json   通用诊断入口配置
│   └── CONFIG_GUIDE.md           配置编写与维护指南
│
├── data/                         # 原始数据 & 处理后数据
│   ├── 1/ ~ 8/                   各 case 原始节点/计算数据
│   ├── merged/                   合并后的图谱数据
│   └── 拒片流程.json              业务流程定义
│
├── docs/                         # 设计文档
│   ├── data_source.md            数据溯源映射
│   └── stage3/
│       ├── prd3.md               Stage3 接口设计文档
│       ├── database_schema.md    数据库 DDL 规范
│       ├── feature_todo.md       功能待办清单
│       └── frontend_backend_integration.md  ★ 前后端交互对照文档
│
└── scripts/                      # 数据处理脚本
    ├── init_docker_db.sql        ★ Docker MySQL 初始化（建表 + Mock 数据）
    ├── flow2data.py              流程 JSON → 图谱数据转换
    ├── merge_data.py             多 case 数据合并
    ├── process_data.py           数据预处理
    └── README.md
```

> ★ 标注为当前 Stage3 开发重点文件。

---

## 快速启动

### 1. 启动数据库（Docker MySQL）

```bash
# 首次启动
docker run -d --name uix-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=datacenter \
  -p 3307:3306 \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

# 初始化表结构与 Mock 数据
docker cp scripts/init_docker_db.sql uix-mysql:/tmp/init.sql
docker exec uix-mysql bash -c "mysql -u root -proot datacenter < /tmp/init.sql"

# 后续重启
docker start uix-mysql
```

数据库连接配置见 `config/connections.json`（本地开发使用 `local` 配置，端口 3307）。

### 2. 启动后端

```bash
cd src/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 3. 启动前端

```bash
cd src/frontend
npm install
npm run dev
```

- 访问：http://localhost:3000
- 前端所有 `/api/*` 请求通过 Vite 代理转发到 `:8000`

---

## 运行测试

```bash
# 拒片故障管理接口 1 & 2 测试（需数据库已启动）
cd src/backend
python tests/test_reject_errors.py

# 诊断引擎测试
python tests/test_diagnosis_prd1.py
```

---

## 关键接口

| 接口 | 方法 | 路径 | 描述 |
|-----|------|------|------|
| 接口 1 | `GET` | `/api/v1/reject-errors/metadata` | 获取 Chunk/Lot/Wafer 筛选元数据 |
| 接口 2 | `POST` | `/api/v1/reject-errors/search` | 查询拒片故障记录（分页+筛选） |
| 接口 3 | `GET` | `/api/v1/reject-errors/{id}/metrics` | 获取故障详情及指标数据 |

详细的前后端交互说明见 `docs/stage3/frontend_backend_integration.md`。  
交接说明见 `docs/HANDOVER.md`。

## 诊断规则与文档

拒片决策树配置见 `config/reject_errors.diagnosis.json`，`config/diagnosis.json` 负责登记 pipeline，`config/CONFIG_GUIDE.md` 负责说明字段语义、写法与维护流程。**执行契约与校验规则**以 `docs/stage3/rules_execution_spec.md`（**v1.2**）为准：`next` 分支仅使用 **`condition` 表达式**；布尔连接词 **大小写不敏感**；服务启动时校验 **`{变量}` 可达性**（Phase A）。
