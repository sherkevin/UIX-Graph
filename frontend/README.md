# 前端应用

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

应用将在 http://localhost:3000 启动

### 构建生产版本

```bash
npm run build
```

## 功能模块

1. **故障记录** (`/records`) - 查看和管理所有故障记录，支持诊断分析
2. **知识录入** (`/entry`) - 仿Excel表单录入故障记录
3. **本体管理** (`/ontology`) - 管理故障现象、分系统、部件、参数、根因等本体
4. **本体展示** (`/ontology-view`) - 可视化展示本体结构
5. **知识图谱** (`/graph`) - 交互式知识图谱可视化，支持单案例视图和全局视图

## 技术栈

- React 18
- Ant Design Pro Components
- Ant Design 5
- G6 (知识图谱可视化)
- Vite (构建工具)
- Axios (HTTP客户端)
- React Router (路由管理)

## 知识图谱操作

1. **切换视图**：使用"单案例视图"或"全局视图"按钮
2. **选择案例**：在单案例视图中，从下拉菜单选择案例ID
3. **交互操作**：
   - 拖拽画布：移动视图
   - 滚轮缩放：放大/缩小
   - 拖拽节点：调整节点位置
   - 点击节点：查看节点信息
   - 悬停节点：高亮显示

## 常见问题排查

### 页面空白或错误

1. **打开浏览器开发者工具**:
   - Windows: 按 `F12` 或 `Ctrl + Shift + I` 或 `Ctrl + Shift + J`（直接打开Console）
   - Mac: 按 `Cmd + Option + I` 或 `Cmd + Shift + C`（打开检查元素模式）
   - 或者：右键点击页面 → 选择"检查"（Inspect）

2. **查看Console标签**: 检查是否有JavaScript错误（红色错误信息）

3. **查看Network标签**: 
   - 刷新页面（`F5` 或 `Cmd + R`）
   - 查看是否有失败的请求（红色）
   - 特别关注 `/api/` 开头的请求

### 常见问题

#### 问题1: CORS错误
如果看到 "CORS policy" 错误：
- 检查后端是否运行在 8000 端口
- 检查 `backend/app/main.py` 中的 CORS 配置

#### 问题2: API请求失败
如果看到 404 或 500 错误：
- 检查后端服务：访问 http://localhost:8000/health
- 检查API：访问 http://localhost:8000/api/knowledge/records

#### 问题3: 组件加载失败
如果看到 "Cannot find module" 错误：
- 运行 `npm install`
- 检查 `node_modules` 是否存在

### 重新安装依赖

如果问题持续：
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run dev
```

## 开发者工具使用

### 开发者工具界面说明

打开后，你会看到浏览器底部或右侧出现一个面板，包含以下标签：

1. **Console（控制台）** - 显示所有的日志和错误信息
2. **Network（网络）** - 显示所有的网络请求
3. **Elements（元素）** - 显示HTML结构
4. **Sources（源代码）** - 显示源代码文件

### 查看知识图谱问题的步骤

1. 打开开发者工具（按上面的快捷键）
2. 点击 **Console** 标签
3. 刷新页面（`F5` 或 `Cmd + R`）
4. 查看是否有红色的错误信息
5. 查看是否有日志输出（如 "G6 Graph loaded successfully"）

### 常见问题

- **如果看不到Console标签**：点击开发者工具顶部的标签栏，找到"Console"
- **如果开发者工具在底部**：可以拖拽到右侧，或者点击右上角的三个点选择位置
- **如果快捷键不工作**：尝试右键点击页面，选择"检查"或"Inspect"