# 文档中心

本目录收录 **SXEE-LITHO-RCA（UIX-Graph）** 的设计说明、交接材料与部署指南。阅读顺序建议按角色选择。

## 1. 五分钟上手

| 文档 | 用途 |
|------|------|
| [../README.md](../README.md) | 仓库总览、一键启动、关键 API 表 |
| [STRUCTURE.md](STRUCTURE.md) | **目录约定** +「我要做 X 改哪儿」对照表 |
| [HANDOVER.md](HANDOVER.md) | 交接：主线能力、运行方式、排坑（§9） |

## 2. 配置驱动（诊断规则）

| 文档 | 用途 |
|------|------|
| [../config/CONFIG_GUIDE.md](../config/CONFIG_GUIDE.md) | 配置文件字段权威说明 |
| [CONFIG_DRIVEN_STATUS.md](CONFIG_DRIVEN_STATUS.md) | 「只改配置」达成度与根本限制 |
| [CONFIG_REVIEW_CHECKLIST.md](CONFIG_REVIEW_CHECKLIST.md) | 改配置时的评审清单（8 节） |
| [stage3/rules_execution_spec.md](stage3/rules_execution_spec.md) | `reject_errors.diagnosis.json` 执行契约（与引擎/校验器对齐） |

**本地自检**：仓库根目录执行 `python scripts/check_config.py`（可选 `--strict` 将 warning 视为失败）。

## 3. Stage3 产品 / 联调

| 文档 | 用途 |
|------|------|
| [stage3/prd3.md](stage3/prd3.md) | 拒片模块 API 设计 |
| [stage3/frontend_backend_integration.md](stage3/frontend_backend_integration.md) | 前后端联调 |
| [data_source.md](data_source.md) | 字段到表的溯源 |

## 4. 部署与内网

| 文档 | 用途 |
|------|------|
| [deployment/docker_local_e2e.md](deployment/docker_local_e2e.md) | 本地 Docker MySQL + ClickHouse |
| [deployment/windows_intranet.md](deployment/windows_intranet.md) | Windows 内网部署 |
| [intranet/databases/](intranet/databases/) | 内网库表 schema 参考（外网 mock 依据） |

**打包交付**：`scripts/package_intranet.ps1`（排除 `node_modules`、`.git`、归档与 IDE 目录；产物通常远小于 50MB）。

## 5. 工程结构约定（摘要）

- **主线后端**：`src/backend/app/engine/`（配置驱动诊断）、`handler/reject_errors.py`、`service/reject_error_service.py`
- **主线前端**：`src/frontend/`（唯一约定前端）
- **运行时配置**：`config/diagnosis.json` 索引 + `config/reject_errors.diagnosis.json` 等
- **老图谱路由**：**2026-04-20 起已物理删除**，后端仅保留 `/api/v1/reject-errors`；历史演进与归档入口见 [archive/README.md](../archive/README.md)

## 6. 启动器与排障

- **GUI**：`start_UIX.bat` / `start_UIX.command` → `scripts/start.py`
- **无 GUI**：`python scripts/start.py --console --env local`（日志同步写入 `logs/launcher-*.log`）
- **依赖安装**：以后端 `src/backend/requirements.txt` 为准；启动器会按需 `pip install -r`

---

维护约定：新增或移动文档时，请同步更新本页索引与 [STRUCTURE.md](STRUCTURE.md) 中相关条目。
