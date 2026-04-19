# scripts/

本目录存放 UIX-Graph 项目的所有命令行工具。**本目录不做物理子目录划分**,
原因:[`start_UIX.bat`](../start_UIX.bat) 与 [`start_UIX.command`](../start_UIX.command)
直接 `python scripts/start.py`,而 `start.py` 又用相对路径调
[`scripts/serve_frontend.py`](./serve_frontend.py) 与 [`scripts/switch_env.py`](./switch_env.py),
物理移动会断引用。本文件用**5 类分组**做软标注。

> 想了解每个脚本对应主线/历史的整体定位,见 [`docs/STRUCTURE.md`](../docs/STRUCTURE.md) §6。

---

## 1. 主入口(用户日常用)

仅这两项是面向最终用户的入口,**改其他文件前先确认不影响这两条链路**。

| 脚本 | 用途 | 谁在调它 | 备注 |
|------|------|---------|------|
| [`start.py`](./start.py) | **唯一推荐启动方式**:Tkinter GUI,环境切换 + 后端 + 前端 + 浏览器 | [`start_UIX.bat`](../start_UIX.bat)、[`start_UIX.command`](../start_UIX.command) | 主流程,不要随便改函数签名 |
| [`serve_frontend.py`](./serve_frontend.py) | 前端静态服务 + `/api/*` 反代到后端 :8000 | `start.py` 子进程拉起 | **路径固定,不能改名/移位** |

启动方式:

```bash
# Windows: 双击 start_UIX.bat
# macOS:   双击 start_UIX.command
# Linux/CLI: python scripts/start.py
```

---

## 2. 环境管理

| 脚本 | 用途 | 谁在调它 |
|------|------|---------|
| [`switch_env.py`](./switch_env.py) | 切换 `APP_ENV`(local/test/prod),生成 `src/backend/.env`、`src/frontend/.env` | `start.py` 自动调,也可独立用 `python scripts/switch_env.py local` |

环境配置源头:[`config/connections.json`](../config/connections.json)。

---

## 3. 数据库初始化(本地 docker)

外网开发用 docker 起 MySQL + ClickHouse 时执行,内网部署不用。

| 脚本 | 用途 | 关键说明 |
|------|------|---------|
| [`init_docker_db.sql`](./init_docker_db.sql) | MySQL `datacenter` 库:建表 + 注入 COARSE 锚点样例 | 详细 schema 见 [`docs/intranet/databases/mysql_datacenter.md`](../docs/intranet/databases/mysql_datacenter.md) |
| [`init_clickhouse_local.sql`](./init_clickhouse_local.sql) | ClickHouse `las` + `src` 库:建表 + 1 行最小 mock | 详细 schema 见 [`docs/intranet/databases/clickhouse_las.md`](../docs/intranet/databases/clickhouse_las.md) 与 [`clickhouse_src.md`](../docs/intranet/databases/clickhouse_src.md) |
| [`create_indexes.sql`](./create_indexes.sql) | MySQL 补充索引(可选) | 仅当性能不达标时再补 |

执行步骤见 [`docs/deployment/docker_local_e2e.md`](../docs/deployment/docker_local_e2e.md)。

---

## 4. 打包 / 部署 / 烟测

| 脚本 | 平台 | 用途 |
|------|------|------|
| [`package_intranet.ps1`](./package_intranet.ps1) | Windows | 把外网开发产物打包成 `UIX-Graph-intranet-package*.zip`,供内网迁移 |
| [`verify_docker_e2e.ps1`](./verify_docker_e2e.ps1) | Windows | docker MySQL/CH 起来后跑端到端烟测 |

打包产物 `*.zip` 已在 [`.gitignore`](../.gitignore) 中拦截,不会入仓。

---

## 5. 调试工具(开发期)

| 脚本 | 用途 |
|------|------|
| [`debug_engine.py`](./debug_engine.py) | 单步调试诊断引擎(命令行,不依赖 HTTP) |
| [`debug_rules.py`](./debug_rules.py) | 校验 `config/reject_errors.diagnosis.json` 规则文件 |

---

## 6. 历史(legacy,prefer alternatives below)

这一类**仍在仓库**但**不推荐再用**;留着是因为可能被遗留的 muscle memory 调用,删掉风险大于收益。

| 脚本 | 替代方案 | 备注 |
|------|---------|------|
| [`start_backend.ps1`](./start_backend.ps1)、[`start_backend.sh`](./start_backend.sh) | 改用 [`start.py`](./start.py) | 仅启动后端,无环境切换/前端构建/端口检测;`start.py` 把这些都做了 |
| [`start_frontend.ps1`](./start_frontend.ps1)、[`start_frontend.sh`](./start_frontend.sh) | 改用 [`start.py`](./start.py) | 同上,仅启动前端 |
| [`flow2data.py`](./flow2data.py) | (无活跃替代) | 老:流程 JSON → 图谱数据;**stage3 主线已不依赖** |
| [`merge_data.py`](./merge_data.py) | (无活跃替代) | 老:多 case 数据合并;**stage3 主线已不依赖** |
| [`process_data.py`](./process_data.py) | (无活跃替代) | 老:数据预处理;**stage3 主线已不依赖** |
| [`api_response.json`](./api_response.json) | (无替代) | 老:某次接口响应的快照;**已无引用方,可在下一轮清理删除** |

**未来清理建议**(独立 PR):

- 4 个 `start_{backend,frontend}.{sh,ps1}` 在 [`docs/STRUCTURE.md`](../docs/STRUCTURE.md) 公示「6 个月不维护后下线」
- `flow2data.py` / `merge_data.py` / `process_data.py` / `api_response.json` 4 项,如确认 stage3/stage4 不用,可一起 `git rm`

---

## 命名约定

- 跨平台脚本:同名 `.ps1`(Windows PowerShell)+ `.sh`(*nix Bash)
- Python 脚本:`*.py`,UTF-8,首行 `# -*- coding: utf-8 -*-`(已隐式)
- SQL 脚本:`init_*.sql`(初始化)、`create_*.sql`(增量)、`migration_*.sql`(迁移,目前无)

## 增加新脚本时

1. 归入上述 5 类之一,在本 README 对应表格里加一行
2. 如果是新主入口,**禁止**直接改 `start.py` 的入口签名(会断 `start_UIX.{bat,command}`)
3. 如果脚本被另一个脚本调用,在「谁在调它」列写明
4. 新增依赖写到 [`src/backend/requirements.txt`](../src/backend/requirements.txt) 而不是这里
