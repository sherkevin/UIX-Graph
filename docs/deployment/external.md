# UIX 外网部署指南

**版本**: 1.0  
**更新日期**: 2026-03-25  
**适用场景**: 外网服务器首次部署，验证三接口完整功能

---

## 1. 前置条件

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.9+ | 后端运行环境 |
| Node.js | 18+ | 前端构建 |
| MySQL | 8.0+ | 主数据库 |
| Nginx | 1.20+ | 同源反代（推荐）|
| Docker（可选） | 20.10+ | 本地 MySQL 最简方式 |

---

## 2. 部署步骤（Linux/macOS）

### 2.1 获取代码

```bash
git clone <仓库地址> UIX
cd UIX
```

### 2.2 配置 MySQL 连接

编辑 `config/connections.json`，填写 `prod` 环境的真实 MySQL 连接信息：

```json
{
  "prod": {
    "mysql": {
      "host": "your-mysql-host",
      "port": 3306,
      "username": "your-user",
      "password": "your-password",
      "dbname": "datacenter"
    },
    "frontend_api_url": ""
  }
}
```

> **安全提示**：不要将真实密码提交到 git 仓库。生产环境建议使用环境变量或密钥管理服务。

### 2.3 切换到生产环境并初始化

```bash
python scripts/switch_env.py prod
```

脚本自动：
- 写入 `src/backend/.env`（APP_ENV=prod）
- 验证 MySQL 连通性
- 创建缓存表 `rejected_detailed_records`（若不存在）

若 MySQL 连通失败，检查防火墙、端口和账号权限后重试。

### 2.4 安装后端依赖并启动

```bash
cd src/backend
pip install -r requirements.txt

# 启动（生产环境去掉 --reload）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证：`curl http://localhost:8000/health` → `{"status":"healthy"}`

### 2.5 构建前端

```bash
cd src/frontend
npm ci
npm run build
# 产物在 src/frontend/dist/
```

### 2.6 配置 Nginx 同源反代

```bash
# 将前端产物部署到静态目录
sudo mkdir -p /var/www/uix
sudo cp -r src/frontend/dist/* /var/www/uix/

# 安装 Nginx 配置
sudo cp deploy/nginx/uix.conf /etc/nginx/conf.d/uix.conf
# 修改 uix.conf 中的 server_name 和 root 路径
sudo nginx -t && sudo nginx -s reload
```

---

## 3. 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `local` | 对应 `config/connections.json` 的键 |
| `CORS_ORIGINS` | `http://localhost:3000,...` | 允许的前端来源（逗号分隔）；同源部署时后端不需要跨域，填写代理域名即可 |
| `METRIC_SOURCE_MODE` | `mock_allowed` | `real` / `mock_allowed` / `mock_forbidden`；外网联调阶段用 `mock_allowed` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

## 4. 外网验收清单

逐一执行以下命令，确认全部返回预期结果后方可宣布外网验收通过：

```bash
BASE=http://your-external-domain.com

# 1. 健康检查
curl "$BASE/health"
# 期望：{"status":"healthy"}

# 2. 接口1 元数据
curl "$BASE/api/v1/reject-errors/metadata?equipment=SSB8000"
# 期望：200，data 包含 Chuck/Lot/Wafer 层级

# 3. 接口2 搜索
curl -X POST "$BASE/api/v1/reject-errors/search" \
  -H "Content-Type: application/json" \
  -d '{"pageNo":1,"pageSize":5,"equipment":"SSB8000"}'
# 期望：200，data 列表非空，meta 含 total

# 4. 接口3 详情（替换 {ID} 为实际记录 ID）
curl "$BASE/api/v1/reject-errors/{ID}/metrics?pageNo=1&pageSize=20"
# 期望：200，data 含 rootCause/metrics

# 5. 非法参数
curl "$BASE/api/v1/reject-errors/metadata?equipment=FAKE"
# 期望：400

curl "$BASE/api/v1/reject-errors/999999999/metrics"
# 期望：404
```

---

## 5. 常见问题

**Q: 接口返回 502 Bad Gateway**  
A: 检查后端是否在 `:8000` 正常运行：`curl http://localhost:8000/health`

**Q: 前端页面空白或路由刷新 404**  
A: 检查 Nginx `location /` 的 `try_files` 配置，确保回退到 `index.html`

**Q: 接口 3 指标均为模拟值**  
A: 当前 `METRIC_SOURCE_MODE=mock_allowed`，ClickHouse 指标均为 mock。
内网 ClickHouse 接通后，在 `.env` 中设置 `METRIC_SOURCE_MODE=real`

**Q: 切换机台后 Chuck/Lot 不更新**  
A: 接口 1 与接口 2 使用了不同的时间字段（详见 Swagger `/docs`），确认时间范围有数据

**Q: CORS 错误**  
A: 同源反代部署时不应出现 CORS。若出现，检查 Nginx 配置，确认前端和 `/api` 走同一域名

---

## 6. 日志位置

后端日志默认输出到 stdout，可通过 systemd 或 supervisor 管理：

```bash
# 查看运行日志（如通过 nohup 启动）
tail -f /var/log/uix-backend.log

# Nginx 访问日志
tail -f /var/log/nginx/access.log
```
