import json
import re
import argparse
import os
from pathlib import Path

# === 全局配置 ===
VIRTUAL_ID_START = 10001
OPERATOR_ID_START = 20001

# 存储所有的节点定义（实体 + 虚拟 + 算子）
# 结构: { "id": {"name": "...", "type": "...", ...其他属性} }
all_nodes = {}

# 存储纯粹的边
# 结构: {"source": "id", "target": "id"}
edges = []

# 映射表，防止重复创建同类算子或虚拟节点
virtual_map = {}   # Key: "{1}||{2}" -> Value: ID
operator_map = {}  # 你的需求里算子也是节点，但每次计算通常是独立的实例
                   # 注：如果是逻辑树，同一个"||"算子处理不同的输入，通常应该视为不同的算子实例（节点）。
                   # 这里我每次遇到算子都会新建一个ID，保证逻辑结构的独立性。

def register_node(id_str, name, node_type, **kwargs):
    """
    注册节点到全局表
    id_str: 节点ID
    name: 节点名称
    node_type: 节点类型
    **kwargs: 其他属性（如subsystem, attribute等）
    """
    if id_str not in all_nodes:
        node_data = {
            "name": name,
            "type": node_type
        }
        # 添加其他属性
        node_data.update(kwargs)
        all_nodes[id_str] = node_data

def get_virtual_id(content):
    """获取虚拟节点ID"""
    global VIRTUAL_ID_START
    content = content.strip()
    if content in virtual_map:
        return virtual_map[content]
    
    vid = str(VIRTUAL_ID_START)
    virtual_map[content] = vid
    VIRTUAL_ID_START += 1
    
    # 注册虚拟节点
    register_node(vid, content, "虚拟分组")
    return vid

def get_operator_id(op_symbol):
    """获取新的算子节点ID"""
    global OPERATOR_ID_START
    op_id = str(OPERATOR_ID_START)
    OPERATOR_ID_START += 1
    
    # 注册算子节点
    register_node(op_id, op_symbol, "算子")
    return op_id

def clean_id(id_str):
    return id_str.replace("{", "").replace("}", "").strip()

def parse_logic(target_id, logic_str):
    """
    解析逻辑，构建图。
    方向说明：逻辑是 Input -> Operator -> Target
    """
    
    # 1. 递归处理括号 (生成虚拟节点)
    while "(" in logic_str:
        pattern = re.compile(r'\(([^()]+)\)')
        match = pattern.search(logic_str)
        if match:
            content = match.group(1)
            full_match = match.group(0)
            
            # 获取虚拟节点ID
            v_id = get_virtual_id(content)
            
            # 递归：构建虚拟节点内部的连接 (Input -> v_id)
            parse_logic(v_id, content)
            
            # 替换字符串，继续处理上层
            logic_str = logic_str.replace(full_match, "{" + v_id + "}")
        else:
            break

    # 2. 识别算子
    # 优先级：你需要根据实际情况扩展算子
    operator_symbol = None
    split_char = None
    
    if "||" in logic_str:
        operator_symbol = "||"
        split_char = "||"
    elif "&&" in logic_str:
        operator_symbol = "&&"
        split_char = "&&"
    elif "+" in logic_str:
        operator_symbol = "+"
        split_char = "+"
    elif "{do}" in logic_str:
        operator_symbol = "do" # 动作也可以看作一种算子
        logic_str = logic_str.replace("{do}", "")
        child_nodes = [logic_str]
    else:
        # 无算子，直接传递
        child_nodes = [logic_str]

    if split_char:
        child_nodes = logic_str.split(split_char)
    elif operator_symbol is None: # 兜底
        child_nodes = [logic_str]

    # 3. 构建连接 (Source -> Target)
    
    if operator_symbol:
        # 情况 A: 有算子
        # 结构: Input1 -> OpNode, Input2 -> OpNode, OpNode -> Target
        
        # 3.1 创建算子节点
        op_id = get_operator_id(operator_symbol)
        
        # 3.2 边: inputs -> op
        for child in child_nodes:
            if child.strip():
                c_id = clean_id(child)
                edges.append({"source": c_id, "target": op_id})
        
        # 3.3 边: op -> target
        edges.append({"source": op_id, "target": target_id})
        
    else:
        # 情况 B: 直接连接 (赋值/传递)
        # 结构: Input -> Target
        child_id = clean_id(child_nodes[0])
        if child_id:
            edges.append({"source": child_id, "target": target_id})

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='处理图谱数据，生成节点、边和映射文件'
    )
    parser.add_argument(
        '-n', '--node',
        required=True,
        help='node.json文件路径'
    )
    parser.add_argument(
        '-c', '--compute',
        required=True,
        help='compute.json文件路径'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='输出目录路径（默认为脚本所在目录）'
    )
    return parser.parse_args()

def main():
    # 解析命令行参数
    args = parse_args()

    # 确定输出目录
    if args.output:
        output_dir = Path(args.output)
    else:
        # 默认为脚本所在目录
        output_dir = Path(__file__).parent

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录: {output_dir}")

    # 读取输入文件
    try:
        with open(args.node, 'r', encoding='utf-8') as f:
            raw_nodes = json.load(f)
        with open(args.compute, 'r', encoding='utf-8') as f:
            compute_data = json.load(f)
    except FileNotFoundError as e:
        print(f"文件未找到: {e}")
        return
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        return

    # 1. 预加载实体节点（保留所有原有属性）
    for nid, info in raw_nodes.items():
        # 提取基本属性
        name = info.get("name", "")
        node_type = info.get("type", "")

        # 提取其他属性（如subsystem, attribute等）
        extra_attrs = {k: v for k, v in info.items() if k not in ["name", "type"]}

        register_node(nid, name, node_type, **extra_attrs)

    # 2. 解析计算逻辑
    for key, item in compute_data.items():
        # 注意：compute.json 里的 target 是结果，operator 是来源
        # 我们的流向是 来源 -> 结果
        final_target = clean_id(item["target"])
        logic_expr = item["operator"]
        parse_logic(final_target, logic_expr)

    # 3. 准备输出数据
    # 主文件：只包含nodes和edges
    main_output = {
        "nodes": all_nodes,
        "edges": edges
    }

    # 映射文件：包含虚拟节点和算子的映射信息
    mapping_output = {
        "virtual_to_id": virtual_map,
        "operator_instances": {
            "note": "算子节点根据逻辑表达式动态生成，每次解析可能生成不同的ID"
        },
        "id_ranges": {
            "virtual_nodes_start": 10001,
            "operator_nodes_start": 20001
        }
    }

    # 4. 写入文件
    main_file = output_dir / "graph_data.json"
    mapping_file = output_dir / "graph_mapping.json"

    with open(main_file, 'w', encoding='utf-8') as f:
        json.dump(main_output, f, indent=4, ensure_ascii=False)

    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping_output, f, indent=4, ensure_ascii=False)

    print(f"\n处理完成！")
    print(f"- 主数据文件: {main_file}")
    print(f"- 映射文件: {mapping_file}")
    print(f"\n统计:")
    print(f"- 节点总数: {len(all_nodes)}")
    print(f"- 边总数: {len(edges)}")
    print(f"- 虚拟节点数: {len(virtual_map)}")

if __name__ == "__main__":
    main()