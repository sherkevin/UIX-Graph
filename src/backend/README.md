<!--
 * @Author: shervin sherkevin@163.com
 * @Date: 2026-01-21 16:51:53
 * @Description: 
 * @FilePath: \UIX\backend\README.md
 * @LastEditTime: 2026-01-22 10:24:45
 * @LastEditors: shervin sherkevin@163.com
 * 
 * Copyright (c) 2026 by ${git_name_email}, All Rights Reserved. 
-->
# 后端 API 文档

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 初始化数据库和Mock数据

```bash
cd backend
python -m app.init_data
```

### 启动服务

```bash
uvicorn app.main:app --reload
```

服务将在 http://localhost:8000 启动

## API 端点

### 本体管理 (`/api/ontology`)

- `GET /api/ontology/phenomena` - 列出所有故障现象
- `POST /api/ontology/phenomena` - 创建故障现象
- `GET /api/ontology/subsystems` - 列出所有分系统
- `POST /api/ontology/subsystems` - 创建分系统
- `GET /api/ontology/components` - 列出所有部件
- `POST /api/ontology/components` - 创建部件
- `GET /api/ontology/parameters` - 列出所有参数
- `POST /api/ontology/parameters` - 创建参数
- `GET /api/ontology/rootcauses` - 列出所有根因
- `POST /api/ontology/rootcauses` - 创建根因

### 知识录入 (`/api/knowledge`)

- `GET /api/knowledge/records` - 列出所有故障记录
- `POST /api/knowledge/records` - 创建故障记录
- `GET /api/knowledge/records/{case_id}` - 获取单个故障记录
- `PUT /api/knowledge/records/{case_id}` - 更新故障记录
- `DELETE /api/knowledge/records/{case_id}` - 删除故障记录

### 诊断推理 (`/api/diagnosis`)

- `POST /api/diagnosis/analyze` - 分析故障记录
- `GET /api/diagnosis/analyze/{case_id}` - 根据case_id分析
- `GET /api/diagnosis/rules` - 列出所有诊断规则

### 可视化 (`/api/visualization`)

- `GET /api/visualization/graph/{case_id}` - 获取单个案例的知识图谱
- `GET /api/visualization/graph` - 获取所有案例的合并知识图谱
### 故障传播 (`/api`)

- `GET /api/propagation/{case_id}` - 获取故障传播路径
  - 参数: `start_node` (可选) - 起始节点ID
- `GET /api/entity/{entity_id}` - 获取实体详情

## 数据模型

详见 `app/schemas/ontology.py`

## 诊断规则

系统已实现以下诊断规则：

1. **旋转超限规则**
   - 条件：`rotation_mean > 300 urad` 或 `rotation_3sigma > 350`
   - 根因：上片旋转机械超限
   - 分类：机械精度

2. **真空吸附异常规则**
   - 条件：`vacuum_level == "Low"` 且 `rotation_mean > 100`
   - 根因：WS 硬件物理损坏/泄露
   - 分类：硬件损耗

3. **对准重复性异常规则**
   - 条件：`rotation_mean > 300`
   - 根因：上片旋转机械超限
   - 分类：机械精度
