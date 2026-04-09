# UIX Windows 内网部署指南

**版本**: 1.0  
**更新日期**: 2026-03-25  
**适用场景**: 将 UIX 系统迁移到上海微电子（SMEE）内网 Windows 环境，
并作为独立子系统接入其总系统

---

## 1. 环境要求

| 依赖 | 版本要求 | 备注 |
|------|----------|------|
| Windows | Server 2016+ / Win10+ | 已测试 Windows 10/11 |
| Python | 3.9+ | 安装时勾选"Add to PATH" |
| Node.js | 18 LTS | 构建前端用，生产环境可只部署 dist/ |
| MySQL | 8.0+ | 由 SMEE 内网 MySQL 提供 |
| ClickHouse | 21+ | 指标数据源（可选，接通前用 mock 模式）|
| Nginx for Windows | 1.20+ | 同源反代（推荐）；或由 SMEE 网关承担 |

> **注意**：Windows 版 Python 不依赖 bash 或 Docker，可在纯 Windows 环境运行。
> 若已有其他 Web 容器（IIS/Apache），可替代 Nginx 承担静态资源和反代职责。

---

## 2. 快速开始

### 2.1 解压交付包

将完整项目目录（含 `src/backend`、`src/frontend`、`config`、`scripts`）
复制到目标机器，例如 `C:\Apps\UIX`。

### 2.2 配置数据库连接

编辑 `config\connections.json`，在 `prod` 键下填写 SMEE 内网 MySQL 连接信息：

```json
{
  "prod": {
    "mysql": {
      "host": "内网 MySQL 主机名或 IP",
      "port": 3306,
      "username": "数据库账号",
      "password": "密码（建议生产前由管理员提供）",
      "dbname": "datacenter"
    },
    "clickhouse": {
      "host": "内网 ClickHouse 主机名或 IP",
      "port": 8123,
      "username": "",
      "password": "",
      "dbname": "las"
    },
    "frontend_api_url": ""
  }
}
```

> **安全要求**：生产密码不得提交 git。建议将密码从 json 移至环境变量（见 2.4 节）。

### 2.3 切换到生产环境（PowerShell）

在项目根目录打开 PowerShell，执行：

```powershell
cd C:\Apps\UIX
python scripts\switch_env.py prod
```

脚本自动完成：
- 写入 `src\backend\.env`（APP_ENV=prod）
- 验证 MySQL 连通性
- 创建缓存表 `rejected_detailed_records`（若不存在）

### 2.4 安装 Python 依赖

```powershell
cd src\backend
pip install -r requirements.txt
```

### 2.5 启动后端

```powershell
# 在 C:\Apps\UIX 根目录
.\scripts\start_backend.ps1 production
```

或手动启动（等价）：

```powershell
cd C:\Apps\UIX\src\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证：打开浏览器访问 `http://localhost:8000/health`，返回 `{"status":"healthy"}`

### 2.6 构建前端（如需在此机器构建）

```powershell
.\scripts\start_frontend.ps1 build
# 产物在 src\frontend\dist\
```

若由 CI/CD 提供已构建的 dist 目录，可跳过此步骤。

### 2.7 配置 Nginx（Windows 版）

1. 下载 [Nginx for Windows](http://nginx.org/en/download.html) 并解压到 `C:\nginx`
2. 编辑 `deploy\nginx\uix.conf`，修改 `root` 路径为实际 dist 目录：
   ```nginx
   root C:/Apps/UIX/src/frontend/dist;
   server_name  _;  # 或填写内网 IP/域名
   ```
3. 将 `uix.conf` 复制到 `C:\nginx\conf\conf.d\uix.conf`
4. 确保 `C:\nginx\conf\nginx.conf` 包含 `include conf.d/*.conf;`
5. 启动 Nginx：
   ```cmd
   cd C:\nginx
   nginx.exe
   ```
6. 测试：`http://localhost/` 返回前端页面，`http://localhost/health` 返回健康检查

---

## 3. 环境变量说明

`src\backend\.env` 文件（由 `switch_env.py` 自动生成，也可手动维护）：

```dotenv
APP_ENV=prod

# CORS：与 SMEE 总系统集成时，填写前端访问域名/IP
# 例：CORS_ORIGINS=http://192.168.1.100,http://intranet.smee.com
CORS_ORIGINS=http://内网访问地址

# 数据源模式
# mock_allowed - 联调阶段（ClickHouse 不通时降级 mock）
# real         - 正式上线后（ClickHouse 必须可用）
METRIC_SOURCE_MODE=mock_allowed

LOG_LEVEL=INFO
```

---

## 4. 接入总系统边界说明

UIX 作为 SMEE 总系统的独立子模块，边界定义如下：

### 4.1 网络接口

| 接口 | 地址 | 说明 |
|------|------|------|
| 前端入口 | `http://<host>:<nginx_port>/` | 浏览器访问 |
| 后端 API | `http://<host>:<nginx_port>/api/v1/reject-errors/` | 由 Nginx 反代 |
| 健康检查 | `http://<host>:<nginx_port>/health` | 监控探针 |
| Swagger 文档 | `http://<host>:8000/docs` | 仅内部调试用，可通过 Nginx 屏蔽 |

### 4.2 对外暴露的 API

```
GET  /api/v1/reject-errors/metadata        接口1：元数据查询
POST /api/v1/reject-errors/search          接口2：故障记录搜索
GET  /api/v1/reject-errors/{id}/metrics   接口3：故障详情+指标
GET  /health                               健康检查
```

### 4.3 数据依赖

| 数据源 | 用途 | 当前状态 |
|--------|------|----------|
| MySQL `datacenter` | 主数据 + 缓存表 | 生产可用 |
| ClickHouse | 指标数据（Tx/Ty/Rw 等） | 内网接通前使用 mock |
| `config/diagnosis.json` | 诊断 pipeline 索引配置 | 随代码一起部署 |
| `config/reject_errors.diagnosis.json` | reject_errors 的 structured 诊断配置 | 随代码一起部署 |

### 4.4 不纳入本轮范围

- 统一认证/SSO 接入（预留位，当前无鉴权）
- 异步预计算架构（MQ/Canal）
- 读写分离数据库架构

---

## 5. Windows 特殊注意事项

1. **路径编码**：代码已使用 `pathlib.Path` 处理路径，避免硬编码 `/`；
   如遇中文路径问题，建议将项目放在 `C:\Apps\UIX`（无中文）。

2. **PowerShell 执行策略**：首次运行 `.ps1` 需先执行：
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

3. **端口防火墙**：确保 Windows 防火墙放行 8000（后端）和 80（Nginx）端口。

4. **日志编码**：后端日志已配置为 UTF-8；PowerShell 默认可能为 GBK，
   若乱码执行：
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   ```

5. **进程持久化**：生产环境建议将后端注册为 Windows 服务，使用 NSSM：
   ```cmd
   nssm install UIX-Backend "python" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
   nssm set UIX-Backend AppDirectory C:\Apps\UIX\src\backend
   nssm start UIX-Backend
   ```

---

## 6. 验收检查命令

```powershell
# 健康检查
Invoke-WebRequest http://localhost/health | Select-Object -ExpandProperty Content

# 接口1
Invoke-WebRequest "http://localhost/api/v1/reject-errors/metadata?equipment=SSB8000" | Select-Object -ExpandProperty Content

# 接口2
$body = '{"pageNo":1,"pageSize":5,"equipment":"SSB8000"}'
Invoke-WebRequest -Method POST -Uri "http://localhost/api/v1/reject-errors/search" `
  -Body $body -ContentType "application/json" | Select-Object -ExpandProperty Content
```

---

## 7. 回滚方案

若部署出现问题：

1. 停止 Nginx：`cd C:\nginx && nginx.exe -s stop`
2. 停止后端：终止 `uvicorn` 进程（任务管理器或 `taskkill /F /IM python.exe`）
3. 恢复上一版本代码目录
4. 重新启动
