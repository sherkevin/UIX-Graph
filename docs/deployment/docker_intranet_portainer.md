# UIX-Graph 内网 Docker 部署评审文档

**适用环境**：SMEE 内网 `172.16.70.160`  
**部署方式**：前后端分别制作镜像，使用 Portainer Stack 部署  
**评审目标**：确认镜像构建、配置注入、端口暴露、健康检查、更新与回滚流程合规后，再执行正式部署。

---

## 1. 部署边界

本方案仅容器化部署 UIX-Graph 应用本身：

- `backend-api`：FastAPI 后端，容器内端口 `8000`
- `frontend-webapp`：Nginx 托管 React/Vite 静态文件，并通过 Docker 内部网络反代 `/api` 到 `backend-api:8000`

数据库不在本 Stack 内启动。MySQL、ClickHouse 仍使用内网真实数据源，连接信息由 `config/connections.json` 提供。

---

## 2. 前置条件

部署前请确认：

1. 已具备 `172.16.70.160` 服务器访问权限。
2. 已具备 Portainer 管理平台账号。
3. 服务器已安装 Docker，并能在 Portainer 中管理对应 Docker Endpoint。
4. 项目仓库已上传到服务器，例如：

   ```bash
   cd ~
   # 上传或解压后形成 ~/UIX-Graph
   cd ~/UIX-Graph
   ```

5. `config/connections.json` 已按目标环境配置，并通过评审确认不把新增敏感信息提交到 git。
6. 目标环境 MySQL、ClickHouse 与 `172.16.70.160` 网络互通。
7. 如需推送 Harbor/Nexus，已完成 Docker Registry 登录与 Portainer Registry 配置。

---

## 3. 本次新增部署资产

| 文件 | 用途 |
| --- | --- |
| `docker/intranet/backend.Dockerfile` | 构建后端镜像 |
| `docker/intranet/frontend.Dockerfile` | 构建前端镜像 |
| `docker/intranet/nginx.conf` | 前端容器 Nginx 配置，内部反代后端 |
| `docker-compose.intranet.yml` | Portainer Stack 模板 |
| `docker/intranet/stack.env.example` | Stack 环境变量示例 |
| `scripts/build_intranet_images.sh` | 在 `172.16.70.160` 构建前后端镜像 |

说明：仓库根目录原有 `docker-compose.yml` 仍用于外网/本地数据库替身联调，不作为本次内网应用部署 Stack。

---

## 4. 镜像构建

在 `172.16.70.160` 的项目根目录执行：

```bash
cd ~/UIX-Graph
chmod +x scripts/build_intranet_images.sh

export UIX_IMAGE_NAMESPACE=uix-graph
export UIX_IMAGE_TAG=v1.0.0-review
./scripts/build_intranet_images.sh
```

如需推送到 Harbor/Nexus：

```bash
export UIX_IMAGE_NAMESPACE=<YOUR_REGISTRY>/<YOUR_NAMESPACE>
export UIX_IMAGE_TAG=v1.0.0-review
export PUSH=1
docker login <YOUR_REGISTRY>
./scripts/build_intranet_images.sh
```

合规要求：

- 镜像必须使用明确 Tag，例如 `v1.0.0-review`、`v1.0.0-prod-20260429`。
- 禁止在 Portainer Stack 中使用 `latest`。
- 每次评审记录需要包含后端镜像名、前端镜像名、Tag、构建时间与构建人。
- 正式部署前必须在 `172.16.70.160` 上完成一次 `./scripts/build_intranet_images.sh`，并确认前后端镜像均构建成功。

---

## 5. Stack 环境变量

以 `docker/intranet/stack.env.example` 为模板，在 Portainer Stack 的 Environment variables 中配置：

```env
UIX_IMAGE_NAMESPACE=uix-graph
UIX_IMAGE_TAG=v1.0.0-review
UIX_PROJECT_DIR=/home/uix/UIX-Graph

APP_ENV=prod
METRIC_SOURCE_MODE=real
REJECTED_DETAILED_CACHE=0
UIX_DETAIL_TRACE=0
LOG_LEVEL=INFO
CORS_ORIGINS=http://172.16.70.160

FRONTEND_EXTERNAL_PORT=80
BACKEND_EXTERNAL_PORT=8000
```

关键说明：

- `UIX_PROJECT_DIR` 必须是服务器上的项目绝对路径。Stack 会将 `${UIX_PROJECT_DIR}/config` 只读挂载到后端容器 `/app/config`，避免为修改数据库连接而重建镜像。
- `APP_ENV` 必须与 `config/connections.json` 中的环境键一致。
- 前端容器不使用宿主机 IP 调后端，`/api` 通过 Nginx 转发到 Docker 内部服务名 `backend-api:8000`。
- 同源部署下浏览器访问前端地址即可，前端请求 `/api`，不需要额外配置 `VITE_API_BASE_URL`。

---

## 6. Portainer 部署流程

1. 访问 Portainer：

   ```text
   http://172.16.70.160:9000
   ```

2. 登录后进入左侧菜单 `Stacks` → `Add Stack`。
3. Stack 命名建议：

   ```text
   uix-graph-review
   ```

   正式环境可使用：

   ```text
   uix-graph-prod
   ```

4. 选择 `Web editor`，粘贴 `docker-compose.intranet.yml` 内容。
5. 在 Environment variables 中填写第 5 节变量。
6. 点击 `Deploy the stack`。
7. 等待两个服务均为 `running`，并确认 healthcheck 通过。

---

## 7. 应用验证

### 7.1 前端验证

浏览器访问：

```text
http://172.16.70.160/
```

预期：

- 页面正常打开。
- 浏览器 Console 无前端资源加载错误。
- Network 中接口请求走同源 `/api/...`。

### 7.2 后端健康检查

服务器上执行：

```bash
curl http://localhost:8000/health
curl http://localhost/health
```

预期返回包含：

```json
{
  "status": "healthy",
  "appEnv": "prod"
}
```

### 7.3 业务接口验证

建议至少验证：

```bash
curl "http://localhost/api/v1/reject-errors/metadata?equipment=SSB8000"
```

若目标接口要求时间参数或其他筛选条件，请按评审用例补充完整请求。验证通过后，再由业务页面执行一次列表查询和详情查询。

---

## 8. 更新与回滚

### 8.1 更新

1. 构建新镜像 Tag：

   ```bash
   export UIX_IMAGE_TAG=v1.0.1-review
   ./scripts/build_intranet_images.sh
   ```

2. 进入 Portainer Stack → `Editor`。
3. 修改环境变量 `UIX_IMAGE_TAG`。
4. 点击 `Update the stack`。
5. 勾选 `Re-pull image and re-create`（使用 Harbor/Nexus 等 Registry 时必须勾选；只使用本机镜像时可不勾选）。

### 8.2 回滚

1. 将 `UIX_IMAGE_TAG` 改回上一个已验证 Tag。
2. 点击 `Update the stack`。
3. 验证 `/health`、前端页面和核心接口。

回滚前不要清理旧镜像；至少保留上一个稳定版本。

---

## 9. 清理与维护

清理悬空镜像：

```bash
docker images --filter "dangling=true" -q | xargs -r docker rmi
```

谨慎清理未使用资源：

```bash
docker system prune
```

仅在确认不需要历史回滚镜像后，才允许执行：

```bash
docker system prune -a
```

---

## 10. 常见问题

### 10.1 页面打不开或接口 502

检查前端容器日志：

```bash
docker logs <frontend-container>
```

重点确认 Nginx 是否能解析内部服务名 `backend-api`。Portainer Stack 中前后端必须在同一个网络 `uix-graph` 下。

### 10.2 后端健康检查失败

检查后端日志：

```bash
docker logs <backend-container>
```

重点确认：

- `APP_ENV` 是否存在于 `config/connections.json`
- `${UIX_PROJECT_DIR}/config` 是否正确挂载
- MySQL、ClickHouse 网络是否可达

### 10.3 拉取镜像失败

如果使用 Harbor/Nexus：

- 确认 `UIX_IMAGE_NAMESPACE` 与镜像实际路径一致。
- 在 Portainer `Registries` 中配置认证信息。
- 确认镜像 Tag 已推送成功。

### 10.4 端口冲突

若 80 或 8000 被占用，可修改：

```env
FRONTEND_EXTERNAL_PORT=8080
BACKEND_EXTERNAL_PORT=18000
```

然后重新部署 Stack，访问 `http://172.16.70.160:8080/`。

---

## 11. 评审检查清单

部署前必须确认：

- [ ] 前后端镜像已分别构建，Tag 明确且非 `latest`。
- [ ] `docker-compose.intranet.yml` 中前端通过 `backend-api:8000` 访问后端，不使用宿主机外部 IP。
- [ ] `config` 使用只读挂载，路径 `${UIX_PROJECT_DIR}/config` 正确。
- [ ] `APP_ENV` 与 `config/connections.json` 匹配。
- [ ] 未在新增脚本、Compose、Dockerfile 中写入真实密码。
- [ ] Portainer Stack 名称符合 `<项目名-功能-环境>` 或 `<个人名-应用名>` 规范。
- [ ] 前端端口、后端端口未与服务器现有服务冲突。
- [ ] `/health`、前端首页、核心业务接口均验证通过。
- [ ] 已记录回滚 Tag，旧镜像未被清理。
