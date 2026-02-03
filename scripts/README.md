# 图谱数据处理脚本使用说明

本目录包含三个用于处理和可视化图谱数据的Python脚本。

## 目录

- [脚本概述](#脚本概述)
- [环境准备](#环境准备)
- [脚本详细说明](#脚本详细说明)
  - [1. 数据合并脚本 (merge_data.py)](#1-数据合并脚本-merge_datapy)
  - [2. 图谱处理脚本 (process_data.py)](#2-图谱处理脚本-process_datapy)
  - [3. 可视化脚本 (visualize_graph.py)](#3-可视化脚本-visualize_graphpy)
- [完整工作流程](#完整工作流程)
- [常见问题](#常见问题)

---

## 脚本概述

| 脚本名称 | 功能 | 输入 | 输出 |
|---------|------|------|------|
| `merge_data.py` | 合并多个数据集 | data/1-8目录 | node.json, compute.json, id_mapping.json |
| `process_data.py` | 解析逻辑表达式，构建图谱 | node.json, compute.json | graph_data.json, graph_mapping.json |
| `visualize_graph.py` | 生成交互式HTML图谱 | graph_data.json | graph_visualization.html |

---

## 环境准备

### 1. Python环境

需要 Python 3.6 或更高版本。

### 2. 安装依赖

```bash
pip install pyvis
```

### 3. 验证安装

```bash
python --version
python -c "import pyvis; print('pyvis安装成功')"
```

---

## 脚本详细说明

### 1. 数据合并脚本 (merge_data.py)

将多个数据集（data/1, data/2, ...）合并为一个统一的数据集，自动处理ID冲突。

#### 功能特点

- 自动扫描data目录下所有包含node.json和compute.json的子目录
- 重新分配唯一ID，保证所有节点ID全局唯一
- 自动更新compute中的ID引用
- 同名节点保持独立，不进行合并
- 保留原始节点属性（subsystem、attribute等）

#### 使用方法

```bash
# 基本用法（默认处理data目录，输出到data/merged）
python scripts/merge_data.py

# 指定数据目录
python scripts/merge_data.py -d /path/to/data

# 指定输出目录
python scripts/merge_data.py -o /path/to/output

# 组合使用
python scripts/merge_data.py -d data -o data/merged_output
```

#### 参数说明

| 参数 | 短参数 | 说明 | 默认值 |
|-----|-------|------|--------|
| `--data-dir` | `-d` | 数据集根目录 | `data` |
| `--output` | `-o` | 输出目录路径 | `data/merged` |

#### 输出文件

执行后在输出目录生成三个文件：

- **node.json**: 合并后的节点数据
  ```json
  {
    "1": {
      "name": "节点名称",
      "type": "节点类型",
      "subsystem": "WS",
      "_dataset": "2",         // 来源数据集
      "_original_id": "1"       // 原始ID
    }
  }
  ```

- **compute.json**: 合并后的计算逻辑
  ```json
  {
    "1": {
      "target": "{14}",
      "operator": "{15}||{16}",
      "_dataset": "2",
      "_original_id": "1"
    }
  }
  ```

- **id_mapping.json**: ID映射关系表
  ```json
  {
    "2": {
      "node_id_map": {
        "1": "14",      // 数据集2的ID1 → 全局ID14
        "2": "15"       // 数据集2的ID2 → 全局ID15
      }
    }
  }
  ```

---

### 2. 图谱处理脚本 (process_data.py)

解析compute.json中的逻辑表达式，构建图谱的节点和边。

#### 功能特点

- 解析复杂的逻辑表达式（括号、||、&&、+等）
- 自动创建虚拟节点和算子节点
- 保留原始节点的所有属性
- 生成标准的图谱数据格式（nodes + edges）
- 分离映射信息到独立文件

#### 使用方法

```bash
# 基本用法（输出到脚本目录）
python scripts/process_data.py -n data/2/node.json -c data/2/compute.json

# 指定输出目录
python scripts/process_data.py -n data/2/node.json -c data/2/compute.json -o data/2/output

# 处理合并后的数据
python scripts/process_data.py -n data/merged/node.json -c data/merged/compute.json -o data/merged/processed
```

#### 参数说明

| 参数 | 短参数 | 说明 | 是否必填 | 默认值 |
|-----|-------|------|---------|--------|
| `--node` | `-n` | node.json文件路径 | 必填 | - |
| `--compute` | `-c` | compute.json文件路径 | 必填 | - |
| `--output` | `-o` | 输出目录路径 | 可选 | 脚本所在目录 |

#### 输出文件

- **graph_data.json**: 主数据文件
  ```json
  {
    "nodes": {
      "1": {
        "name": "节点名",
        "type": "类型",
        "subsystem": "WS",
        "attribute": []
      }
    },
    "edges": [
      {
        "source": "1",
        "target": "2"
      }
    ]
  }
  ```

- **graph_mapping.json**: 映射信息文件
  ```json
  {
    "virtual_to_id": {
      "{12}||{13}||{14}": "10001"
    },
    "id_ranges": {
      "virtual_nodes_start": 10001,
      "operator_nodes_start": 20001
    }
  }
  ```

#### ID分配规则

| 节点类型 | ID范围 | 说明 |
|---------|--------|------|
| 原始节点 | 1 - 10000 | 来自node.json |
| 虚拟分组 | 10001 - 20000 | 括号表达式生成的虚拟节点 |
| 算子节点 | 20001+ ||, &&, +等算子 |

---

### 3. 可视化脚本 (visualize_graph.py)

将graph_data.json转换为交互式HTML图谱。

#### 功能特点

- 不同类型节点使用不同颜色
- 虚拟分组节点显示ID，其他节点显示名称
- 所有节点使用圆形
- 支持拖拽、缩放、悬停提示
- 有向箭头显示边的方向
- 物理引擎自动布局

#### 节点颜色方案

| 节点类型 | 颜色代码 | 颜色 |
|---------|---------|------|
| 故障状态 | #FF6B6B | 红色 |
| 数据前置 | #4ECDC4 | 青色 |
| 数据表征 | #45B7D1 | 蓝色 |
| 虚拟分组 | #FFA07A | 橙色 |
| 算子 | #95E1D3 | 绿色 |
| 默认 | #CCCCCC | 灰色 |

#### 使用方法

```bash
# 基本用法（使用默认路径）
python scripts/visualize_graph.py

# 指定输入文件
python scripts/visualize_graph.py -i data/2/output/graph_data.json

# 指定输出文件
python scripts/visualize_graph.py -o my_graph.html

# 调整画布大小
python scripts/visualize_graph.py --height "1200px" --width "1200px"

# 组合使用
python scripts/visualize_graph.py -i data/merged/processed/graph_data.json -o merged.html --height "1000px"
```

#### 参数说明

| 参数 | 短参数 | 说明 | 默认值 |
|-----|-------|------|--------|
| `--input` | `-i` | 输入的graph_data.json路径 | `scripts/graph_data.json` |
| `--output` | `-o` | 输出的HTML文件路径 | `scripts/graph_visualization.html` |
| `--height` | - | 画布高度 | `900px` |
| `--width` | - | 画布宽度 | `100%` |

#### 交互操作

- **拖拽节点**：点击并拖动节点调整位置
- **缩放**：鼠标滚轮缩放图谱
- **平移**：点击空白处拖动
- **查看详情**：鼠标悬停在节点上显示详细信息
- **高亮**：点击节点高亮显示其连接

---

## 完整工作流程

### 场景1：处理单个数据集

以处理 `data/2` 为例：

```bash
# 步骤1: 处理数据
python scripts/process_data.py \
  -n data/2/node.json \
  -c data/2/compute.json \
  -o data/2/processed

# 步骤2: 生成可视化
python scripts/visualize_graph.py \
  -i data/2/processed/graph_data.json \
  -o data/2/processed/graph.html

# 步骤3: 在浏览器中打开
start data/2/processed/graph.html  # Windows
# 或
open data/2/processed/graph.html   # macOS/Linux
```

### 场景2：合并所有数据集并可视化

```bash
# 步骤1: 合并所有数据集
python scripts/merge_data.py

# 步骤2: 处理合并后的数据
python scripts/process_data.py \
  -n data/merged/node.json \
  -c data/merged/compute.json \
  -o data/merged/processed

# 步骤3: 生成总图谱
python scripts/visualize_graph.py \
  -i data/merged/processed/graph_data.json \
  -o data/merged/processed/total_graph.html

# 步骤4: 打开浏览器查看
start data/merged/processed/total_graph.html
```

### 场景3：批量处理所有数据集

```bash
# 批量处理每个数据集
for dir in data/*/; do
  if [ -f "$dir/node.json" ] && [ -f "$dir/compute.json" ]; then
    echo "Processing $dir"
    python scripts/process_data.py \
      -n "$dir/node.json" \
      -c "$dir/compute.json" \
      -o "$dir/processed"

    python scripts/visualize_graph.py \
      -i "$dir/processed/graph_data.json" \
      -o "$dir/processed/graph.html"
  fi
done
```

---

## 常见问题

### Q1: 脚本报错"未安装pyvis"

**解决方案：**
```bash
pip install pyvis
```

### Q2: Windows下输出文件名乱码

这是终端编码问题，不影响文件内容。文件实际保存正常。

### Q3: 可视化图谱布局混乱

可以调整物理引擎参数，编辑 `visualize_graph.py` 中的物理配置：

```python
net.set_options("""
{
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -8000,  # 调整引力
      "springLength": 150,             # 调整弹簧长度
      "springConstant": 0.04           # 调整弹簧强度
    }
  }
}
""")
```

### Q4: 想自定义节点颜色

编辑 `visualize_graph.py` 中的 `TYPE_COLORS` 字典：

```python
TYPE_COLORS = {
    "故障状态": "#FF0000",  # 改为纯红色
    "数据前置": "#00FF00",  # 改为纯绿色
    # ...
}
```

### Q5: 如何验证ID映射是否正确？

检查 `id_mapping.json` 文件，它记录了所有ID的转换关系。

### Q6: 虚拟节点的ID为什么从10001开始？

这是为了避免与原始节点ID冲突。可以在 `process_data.py` 中修改：

```python
VIRTUAL_ID_START = 10001  # 修改为其他值
OPERATOR_ID_START = 20001  # 修改为其他值
```

---

## 数据格式说明

### node.json 格式

```json
{
  "1": {
    "name": "节点名称",
    "type": "节点类型",
    "subsystem": "WS",      // 可选
    "attribute": []         // 可选
  }
}
```

### compute.json 格式

```json
{
  "1": {
    "target": "{1}",                    // 目标节点ID
    "operator": "{2}||{3}||({4}&&{5})"  // 逻辑表达式
  }
}
```

#### 逻辑表达式语法

| 符号 | 说明 | 示例 |
|-----|------|------|
| `\{id\}` | 引用节点ID | `{1}` |
| `\|\|` | 或运算 | `{1}||{2}` |
| `&&` | 与运算 | `{1}&&{2}` |
| `+` | 加运算 | `{1}+{2}` |
| `()` | 分组/虚拟节点 | `({1}||{2})` |
| `{do}` | 动作算子 | `{do}{action}` |

---

## 文件结构示例

```
UIX/
├── data/
│   ├── 1/
│   │   ├── node.json
│   │   └── compute.json
│   ├── 2/
│   │   ├── node.json
│   │   └── compute.json
│   └── ...
├── scripts/
│   ├── merge_data.py
│   ├── process_data.py
│   ├── visualize_graph.py
│   └── README.md (本文件)
└── data/merged/
    ├── node.json
    ├── compute.json
    ├── id_mapping.json
    └── processed/
        ├── graph_data.json
        ├── graph_mapping.json
        └── total_graph.html
```

---

## 技术支持

如有问题，请检查：
1. Python版本是否 >= 3.6
2. pyvis是否正确安装
3. 输入文件路径是否正确
4. JSON文件格式是否合法

---

**最后更新：** 2026-01-29
