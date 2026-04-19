# UIX-Graph 项目目录约定

> 本文件回答两个问题:**「这个项目的目录长什么样?」**、**「我要做 X 件事,该改哪儿?」**
> 任何时候发现某个目录不在本文档里,请补进来,而不是把它当成「未知」绕过去。
>
> 维护人:任何 PR 修改的目录如果在本文档里没记录,审核时要求一并更新。

---

## 1. 顶层目录(30 秒导航)

| 目录 / 文件 | 用途 | 归属 | 是否在迭代 |
|-------------|------|------|-----------|
| `src/backend/` | FastAPI 后端,所有业务逻辑 | **主线 stage3/stage4** | ✅ 是 |
| `src/frontend/` | React + Vite 前端,**约定唯一前端** | **主线 stage3/stage4** | ✅ 是 |
| `config/` | 运行时配置(诊断规则、连接信息) | 主线 | ✅ 是 |
| `scripts/` | 启动器、打包、初始化 SQL、辅助脚本 | 主线 + 工具 | ✅ 是 |
| `docs/` | 设计文档、交接文档、内网 schema | 主线 + 历史 | 部分 |
| `deploy/` | 内网部署辅助(nginx 配置等) | 部署 | 偶尔改 |
| `docker/` | 容器化(`docker-compose.yml` 配套) | 部署 | 偶尔改 |
| `Dockerfile`、`docker-compose.yml` | 本地 docker 一键起 MySQL+ClickHouse | 部署 | 偶尔改 |
| `start_UIX.bat`、`start_UIX.command` | 跨平台一键启动入口(包装 `scripts/start.py`) | 部署 | 偶尔改 |
| `README.md` | 仓库门面 + 快速启动 | 必读 | ✅ 是 |
| `.cursor/`、`.vscode/` | IDE 配置(rules/mcp.json 等团队共享) | 工具 | 偶尔改 |
| `.gitignore`、`.uvrc`、`.dockerignore` | 仓库级配置 | 工具 | 偶尔改 |

---

## 2. 后端 `src/backend/`

```
src/backend/
├── app/
│   ├── main.py                      # FastAPI 入口 + 路由注册 + 全局异常处理
│   ├── handler/                     # API 层(Controller),只做 HTTP 解析+响应封装
│   │   ├── reject_errors.py         # ★ Stage3 主接口(拒片故障管理 1/2/3)
│   │   ├── ontology.py              # 老路由(本体)— 待评估是否保留
│   │   ├── knowledge.py             # 老路由(知识)— 待评估
│   │   ├── diagnosis.py             # 老路由(通用诊断)— 用 app/core/
│   │   ├── visualization.py         # 老路由(可视化)
│   │   ├── propagation.py           # 老路由(传播)
│   │   ├── full_graph.py            # 老路由(全图)
│   │   └── entity.py                # 老路由(实体)
│   │
│   ├── service/                     # 业务逻辑层(本应是主要业务沉淀地)
│   │   └── reject_error_service.py  # ★ Stage3 业务主线
│   │
│   ├── engine/                      # ★ 当前主诊断引擎(配置驱动 stage3/stage4)
│   │   ├── diagnosis_engine.py      # 决策树遍历器
│   │   ├── metric_fetcher.py        # 指标取数(MySQL/ClickHouse/intermediate/failure_record_field)
│   │   ├── condition_evaluator.py   # 条件表达式 DSL
│   │   ├── rule_loader.py           # 规则加载
│   │   ├── rule_validator.py        # 规则静态校验
│   │   └── actions/                 # 内置 action 函数(@register 装饰器)
│   │       ├── __init__.py          # 注册器 + 自动加载
│   │       └── builtin.py           # COWA 建模、Tx/Ty/Rw 均值计算等
│   │
│   ├── diagnosis/                   # 诊断配置层(单例 store)
│   │   ├── config_store.py          # 加载 config/diagnosis.json + 各 pipeline 文件
│   │   └── service.py               # 引擎工厂
│   │
│   ├── core/                        # ⚠️ 老引擎(图谱/本体/传播)— 跟 engine/ 平行存在
│   │   ├── diagnosis_engine.py      #   被 handler/diagnosis.py 用
│   │   ├── diagnosis_engine_prd1.py #   PRD1 老版本(可能可删)
│   │   ├── graph_builder.py
│   │   ├── full_graph_builder.py
│   │   ├── path_finder.py
│   │   ├── operators.py
│   │   └── test_data.py
│   │
│   ├── ods/                         # 数据访问层(MySQL / ClickHouse 直连)
│   │   ├── datacenter_ods.py        # MySQL datacenter
│   │   └── clickhouse_ods.py        # ClickHouse las/src
│   │
│   ├── models/                      # SQLAlchemy ORM
│   │   ├── reject_errors_db.py      # ★ 拒片相关 ORM
│   │   └── database.py              # 引擎/会话(老路由用)
│   │
│   ├── schemas/                     # Pydantic Schema(API 请求/响应)
│   │   ├── reject_errors.py         # ★
│   │   ├── diagnosis.py             # 老路由
│   │   └── ontology.py              # 老路由
│   │
│   └── utils/
│       ├── time_utils.py            # 时间戳互转
│       └── detail_trace.py          # 接口 3 排障日志(`[详情排障]` 前缀)
│
├── tests/                           # 13 个测试文件,见 §2.1
├── requirements.txt
└── README.md
```

### 2.1 后端测试现状

| 测试文件 | 是否依赖 DB | 跟主线关系 |
|---------|-------------|-----------|
| `test_metric_fetcher_window.py` | ❌ | 主线 |
| `test_rules_validator.py` | ❌ | 主线 |
| `test_rules_engine_conditions.py` | ❌ | 主线 |
| `test_rules_actions_implementation.py` | ❌ | 主线 |
| `test_rules_actions_binding.py` | ❌ | 主线 |
| `test_diagnosis_config_store.py` | ❌ | 主线 |
| `test_reject_error_detail.py` | 部分 | 主线 |
| `test_reject_errors.py` | ✅ MySQL | 主线集成 |
| `test_reject_errors_api.py` | ✅ MySQL | 主线集成 |
| `test_docker_seed_alignment.py` | ✅ MySQL+CH | 主线集成 |
| `test_docker_e2e_extend.py` | ✅ MySQL+CH | 主线集成 |
| `test_diagnosis_prd1.py` | ❌ | **老 PRD1 引擎**,跟 `app/core/diagnosis_engine_prd1.py` 一起待评估 |
| `test_core_diagnosis_adapter.py` | ❌ | **老 core 引擎适配测试**,同上待评估 |

**CI 推荐跑**:不带 ✅ 的 9 个文件。带 ✅ 的需要本地起 docker-compose 后才能跑(`docs/deployment/docker_local_e2e.md`)。

---

## 3. 前端 `src/frontend/`

```
src/frontend/
├── src/
│   ├── pages/
│   │   ├── FaultRecords.jsx       # ★ 唯一业务页面(故障记录管理)
│   │   └── FaultRecords.css
│   ├── components/                # 9 个通用组件(其中 ErrorBoundary/CustomSelect 实际在用)
│   ├── hooks/                     # useApi / useCache(部分组件已不再使用)
│   ├── services/api.js            # ★ 统一 API 层
│   ├── config/index.js            # 环境变量配置
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── vite.config.js                 # /api → :8000 代理
└── package.json
```

> ⚠️ **历史遗留:仓库根目录的 `frontend/` 是「老的多页面 UI」**(知识录入/本体/全图谱等 6 个老页面),与 `src/frontend/` **不是同一份代码**。后续清理需用户决策是否物理删除,见 [`docs/HANDOVER.md`](./HANDOVER.md) §9.5。

---

## 4. 配置 `config/`

```
config/
├── diagnosis.json                       # pipeline 索引(version=3.0.0)
├── reject_errors.diagnosis.json         # ★ Stage3 主诊断规则(28KB)
├── ontology_api.diagnosis.json          # 老 pipeline(配 handler/ontology)
├── connections.json                     # MySQL/ClickHouse 连接(local/test/prod 三档)
├── metrics_meta.yaml                    # 指标元数据(config_store 启动时合并进 metrics)
└── CONFIG_GUIDE.md                      # ★ 诊断规则编写权威说明
```

**改诊断规则的标准流程**:`metrics_meta.yaml` → `reject_errors.diagnosis.json` → `pytest tests/test_rules_validator.py tests/test_diagnosis_config_store.py`

---

## 5. 文档 `docs/`

```
docs/
├── STRUCTURE.md                         # ★ 本文件
├── HANDOVER.md                          # 交接说明 + 已知边界排坑
├── data_source.md                       # API 字段 → DB 字段映射
├── plans/
│   └── 2026-04-13-cowa-metric-source-fixes.md   # ★ 迭代中的实施计划
├── stage3/                              # Stage3(已基本完成,部分待办)
│   ├── prd3.md
│   ├── database_schema.md
│   ├── rules_execution_spec.md          # 诊断 DSL 执行契约 v1.2
│   ├── frontend_backend_integration.md
│   └── feature_todo.md
├── stage4/                              # ★ 当前迭代(指标源头梳理 + 台账方法论)
│   ├── prd.md
│   ├── reject_errors_config_mapping.md  # diagnosis.json 字段说明
│   └── diagnosis-path-template.md       # 专家访谈台账模板
├── intranet/                            # 内网/外网协作
│   ├── databases/                       # ★★ 内网数据库 schema 权威(供外网 mock)
│   │   ├── README.md
│   │   ├── mysql_datacenter.md
│   │   ├── clickhouse_las.md
│   │   └── clickhouse_src.md
│   ├── schema_reference.md              # 老版「内网字段标准」,已被 databases/ 取代
│   └── linking_tbd.md                   # 待业务确认的关联键清单
└── deployment/
    ├── docker_local_e2e.md              # 本地 docker 起 MySQL/CH 端到端
    ├── windows_intranet.md              # Windows 内网部署
    └── external.md                      # 外网部署
```

---

## 6. 脚本 `scripts/`

```
scripts/
├── start.py                  # ★ Tkinter GUI 一键启动器(主入口)
├── switch_env.py             # 切换 APP_ENV(local/test/prod)
├── serve_frontend.py         # 静态前端服务(start.py 调它)
├── package_intranet.ps1      # ★ 内网迁移打包(产出根目录 zip,zip 自动 .gitignore)
├── verify_docker_e2e.ps1     # docker e2e 烟测
│
├── init_docker_db.sql        # ★ MySQL docker 初始化(建表 + COARSE mock 数据)
├── init_clickhouse_local.sql # ★ ClickHouse docker 初始化
├── create_indexes.sql        # 索引补全(可选)
│
├── start_backend.ps1         # 仅后端启动(不走 start.py)
├── start_frontend.ps1
├── start_backend.sh          # *nix 版
├── start_frontend.sh
│
├── debug_engine.py           # 单步调试诊断引擎(命令行)
├── debug_rules.py            # 校验规则文件(命令行)
│
├── flow2data.py              # 老:流程 JSON → 图谱数据
├── merge_data.py             # 老:多 case 数据合并
├── process_data.py           # 老:数据预处理
├── api_response.json         # 老:接口响应快照
└── README.md
```

> 当前**用户操作主入口**:`scripts/start.py`(GUI)。其他 .sh / .ps1 是历史保留,后续清理时建议合并到 `scripts/dev/` 子目录。

---

## 7. 「我想做 X 件事,该改哪儿」对照表

| 想做的事 | 改哪些文件 | 备注 |
|---------|-----------|------|
| 改诊断规则(加个分支/调阈值) | `config/reject_errors.diagnosis.json` | 改完跑 `pytest tests/test_rules_validator.py` |
| 加一个新的诊断指标(已有表的列) | `config/reject_errors.diagnosis.json` 加 `metrics.<id>` | 如指标依赖前序值,要在 metric_id 列表上保持顺序 |
| 加一个新的 DB 表作指标源 | 1. `docs/intranet/databases/<db>.md` 加表小节<br>2. `scripts/init_docker_db.sql` 或 `init_clickhouse_local.sql` 建表+mock<br>3. `config/reject_errors.diagnosis.json` 加 metric | **顺序重要**:文档先于代码 |
| 加一个新的 action 函数 | `src/backend/app/engine/actions/<新文件>.py`(用 `@register("name")` 装饰) | 自动加载,不用改 `__init__.py` |
| 加一个新接口 | `src/backend/app/handler/<新文件>.py` + `service/` + `schemas/` + `main.py` 注册 | 参考 `handler/reject_errors.py` |
| 改前端筛选 / 表格 | `src/frontend/src/pages/FaultRecords.jsx` | 主页面单文件 |
| 加一个前端页面 | `src/frontend/src/pages/<新文件>.jsx` + `App.jsx` 加路由 | 注意根目录 `frontend/` 不是这里 |
| 改后端启动逻辑 | `scripts/start.py`(主)/ `src/backend/app/main.py`(应用层) | start.py 是 GUI 启动器,不要把业务逻辑塞这里 |
| 改打包流程 | `scripts/package_intranet.ps1` | 产物 zip 自动忽略,不要 commit |
| 改本地 docker 数据 | `scripts/init_docker_db.sql` / `init_clickhouse_local.sql` | 按 §9 锚点对齐 |

---

## 8. 命名 / 编码 / 路径约定

| 项 | 约定 |
|---|------|
| 文件名 | **全部 ASCII**;中文名一律不入仓(已有 .gitignore 拦截) |
| Python 模块 | `snake_case` |
| React 组件 | `PascalCase.jsx` |
| metric_id | `snake_case`(`Mwx_0`、`mark_pos_x`、`trigger_log_mwx_cgg6_range`) |
| diagnosis step id | 整数或数字字符串(全局唯一) |
| 时间戳 | API 层一律 13 位毫秒(int);DB 层 DATETIME(6) |
| 字符集 | UTF-8(后端 main.py 已在启动时 `reconfigure(encoding="utf-8")`) |

---

## 9. Mock 锚点(贯穿所有文件)

为了让外网开发任何时候都能跑通**端到端 COWA 诊断样例**,所有 mock 与测试都围绕这一锚点对齐:

| 字段 | 锚点值 |
|------|--------|
| `equipment` | `SSB8000` |
| `chuck_id` | `1` |
| `lot_id` | `101` |
| `wafer_index` / `wafer_id` | `7` |
| `wafer_product_start_time` (T) | `2026-01-10 08:45:00` |
| `reject_reason` | `6` (COARSE_ALIGN_FAILED) |
| `recipe_id` | `RCP-DOCKER-001` |
| ClickHouse `file_time` | `[T - 7 天, T]`,推荐 `08:44:30 ~ 08:44:58` |

详见 [`docs/intranet/databases/README.md`](./intranet/databases/README.md) §2.3。
