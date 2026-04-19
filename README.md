# SXEE-LITHO-RCA(UIX-Graph)

光刻机拒片根因分析系统(Reject Cause Analysis)。

> **30 秒导航**:[`docs/STRUCTURE.md`](docs/STRUCTURE.md) — 项目目录与「我想做 X 件事改哪儿」对照表
> **新人交接**:[`docs/HANDOVER.md`](docs/HANDOVER.md) — 当前主线 + 已知边界排坑
> **内网数据库 schema**:[`docs/intranet/databases/`](docs/intranet/databases/) — 外网开发 mock 的权威参考(每个 db 一个文件)

---

## 仓库速览

| 顶层目录 | 用途 | 维护状态 |
|----------|------|----------|
| [`src/backend/`](src/backend/) | FastAPI 后端 | 主线 |
| [`src/frontend/`](src/frontend/) | React + Vite 前端(单页:拒片故障管理) | 主线 |
| [`config/`](config/) | 诊断规则 + 数据库连接 | 主线 |
| [`scripts/`](scripts/) | 启动器 / 打包 / DB 初始化(见 [`scripts/README.md`](scripts/README.md)) | 主线 |
| [`docs/`](docs/) | 设计文档 / 内网 schema / 部署文档 | 主线 |
| [`docker/`](docker/) [`Dockerfile`](Dockerfile) [`docker-compose.yml`](docker-compose.yml) | 本地 docker 一键起 MySQL+ClickHouse | 部署 |
| [`deploy/`](deploy/) | 内网部署辅助(nginx 配置等) | 部署 |
| [`archive/`](archive/) | **冻结的历史代码**(老 multi-page UI 等);**不在任何运行路径上** | 归档 |
| [`start_UIX.bat`](start_UIX.bat) [`start_UIX.command`](start_UIX.command) | 跨平台一键启动入口(包装 [`scripts/start.py`](scripts/start.py)) | 部署 |

详细布局见 [`docs/STRUCTURE.md`](docs/STRUCTURE.md)。

---

## 快速启动(本地外网开发)

### 方式 A:GUI 一键启动(推荐)

- Windows:双击 [`start_UIX.bat`](start_UIX.bat)
- macOS:双击 [`start_UIX.command`](start_UIX.command)
- 任意 OS:`python scripts/start.py`

GUI 会处理:依赖安装 → 切环境(local/test/prod)→ 起后端(:8000)→ 起前端代理(:3000)→ 打开浏览器。

### 方式 B:手工三步

```bash
# 1. 起本地数据库(docker-compose 自动起 MySQL + ClickHouse + 灌 mock)
docker-compose up -d
# 详细步骤与验证见 docs/deployment/docker_local_e2e.md

# 2. 起后端
cd src/backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Swagger: http://localhost:8000/docs

# 3. 起前端
cd src/frontend
npm install
npm run dev
# 访问: http://localhost:3000
```

数据库连接配置见 [`config/connections.json`](config/connections.json)。

---

## 关键接口

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 1 | `GET` | `/api/v1/reject-errors/metadata` | 筛选元数据(Chuck/Lot/Wafer 树) |
| 2 | `POST` | `/api/v1/reject-errors/search` | 拒片记录列表(分页 + 筛选) |
| 3 | `GET` | `/api/v1/reject-errors/{id}/metrics` | 故障详情 + 诊断指标(支持 `requestTime` 缓存绕过) |

> 老路由 `/api/{ontology,knowledge,diagnosis,visualization,propagation,entity,graph}` 默认仍注册,可通过环境变量 `LEGACY_ROUTES_ENABLED=false` 关闭。详见 [`docs/STRUCTURE.md`](docs/STRUCTURE.md) §2。

详细字段见 [`docs/stage3/prd3.md`](docs/stage3/prd3.md);前后端联调见 [`docs/stage3/frontend_backend_integration.md`](docs/stage3/frontend_backend_integration.md)。

---

## 诊断规则

- **配置入口**:[`config/diagnosis.json`](config/diagnosis.json)(pipeline 索引)
- **拒片主规则**:[`config/reject_errors.diagnosis.json`](config/reject_errors.diagnosis.json)
- **字段权威说明**:[`config/CONFIG_GUIDE.md`](config/CONFIG_GUIDE.md)
- **执行契约 v1.2**:[`docs/stage3/rules_execution_spec.md`](docs/stage3/rules_execution_spec.md) — `next` 仅 `condition` 表达式;布尔词大小写不敏感;启动时校验 `{变量}` 可达性(Phase A)

---

## 测试

```bash
cd src/backend

# 不依赖 DB(CI 常跑,推荐先跑这些)
python -m pytest tests/test_metric_fetcher_window.py tests/test_rules_validator.py tests/test_rules_engine_conditions.py tests/test_diagnosis_config_store.py tests/test_rules_actions_implementation.py tests/test_rules_actions_binding.py -v

# 依赖 docker MySQL + ClickHouse
python -m pytest tests/test_reject_errors.py tests/test_reject_errors_api.py tests/test_docker_seed_alignment.py tests/test_docker_e2e_extend.py -v
```

各测试详细分类见 [`docs/STRUCTURE.md`](docs/STRUCTURE.md) §2.1。

---

## 内网迁移 / 外网协作

外网开发完成后打包到内网部署,见:

- 打包:[`scripts/package_intranet.ps1`](scripts/package_intranet.ps1)
- 内网部署:[`docs/deployment/windows_intranet.md`](docs/deployment/windows_intranet.md)
- 内网数据库 schema(供外网 mock):[`docs/intranet/databases/`](docs/intranet/databases/)

---

## 项目历史与归档

- 原仓库根目录 `frontend/`(老的多页面 UI)已归档至 [`archive/frontend-legacy/`](archive/frontend-legacy/),不再在主线维护
- `app/core/` 老图谱/本体引擎仍存在,被 7 组老路由依赖;计划在 `LEGACY_ROUTES_ENABLED=false` 观察 30 天无 404 后清除
- 详见 [`archive/README.md`](archive/README.md) 与 [`docs/STRUCTURE.md`](docs/STRUCTURE.md)
