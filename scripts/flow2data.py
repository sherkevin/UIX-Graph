import json
import argparse
import re
from pathlib import Path


def load_json(path):
    """加载JSON文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    """保存JSON文件"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def format_condition_logic(source_id, condition_text):
    """
    将文本条件转化为逻辑表达式字符串。
    V5修正：计算单元（带逻辑的表达式）必须用 () 包裹，以便后续解析为虚拟节点。
    """
    # 1. 如果没有条件，直接返回ID（这只是数据流，不是计算单元，不需要括号）
    if not condition_text:
        return f"{{{source_id}}}"

    clean_text = condition_text.strip()

    # 2. 处理数学比较符号 (>, <, =, >=, <=)
    # 示例: "M > 100ppm" -> "({10} check 'M > 100ppm')"
    if any(op in clean_text for op in ['>', '<', '=', '≥', '≤']):
        return f"({{{source_id}}} check '{clean_text}')"

    # 3. 处理状态描述 (正常, 异常)
    # 示例: "正常" -> "({10} == 'Normal')"
    if clean_text in ['正常', 'Normal', 'OK', '是', 'Yes']:
        return f"({{{source_id}}} == 'Normal')"

    if clean_text in ['异常', 'Abnormal', 'NG', '否', 'No']:
        return f"({{{source_id}}} == 'Abnormal')"

    # 4. 默认情况，保留文本作为匹配条件
    # 示例: "MCC与WQ几乎为0" -> "({40} match 'MCC与WQ几乎为0')"
    return f"({{{source_id}}} match '{clean_text}')"


def process_flow(input_file, output_dir=None):
    """
    处理flow.json文件，生成node.json和compute.json

    Args:
        input_file: 输入的flow.json文件路径
        output_dir: 输出目录路径，默认为input_file所在目录
    """
    input_file = Path(input_file)

    # 确定输出目录
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = input_file.parent

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"处理文件: {input_file}")
    print(f"输出目录: {output_dir}")

    # 加载数据
    flow_data = load_json(input_file)

    # 1. 生成 node.json
    final_nodes = {}

    for item in flow_data:
        node_entry = {
            "name": item['text'],
            "type": item['type']
        }
        if 'subsystem' in item:
            node_entry['subsystem'] = item['subsystem']

        final_nodes[item['id']] = node_entry

    # 2. 生成 compute.json
    target_logic_map = {}

    for item in flow_data:
        source_id = item['id']
        if 'next' in item and item['next']:
            for transition in item['next']:
                target_id = transition['target']
                condition = transition.get('condition', '').strip()

                # 生成逻辑表达式 (带括号的计算单元)
                logic_expr = format_condition_logic(source_id, condition)

                if target_id not in target_logic_map:
                    target_logic_map[target_id] = []
                target_logic_map[target_id].append(logic_expr)

    final_compute = {}
    for target_id, logic_parts in target_logic_map.items():
        # 如果有多个来源，用 || 连接
        # 结果示例: "({21} == 'Abnormal') || ({22} check '>10')"
        full_operator = " || ".join(logic_parts)

        final_compute[target_id] = {
            "target": f"{{{target_id}}}",
            "operator": full_operator
        }

    # 3. 输出
    output_node_file = output_dir / "node.json"
    output_compute_file = output_dir / "compute.json"

    save_json(final_nodes, output_node_file)
    save_json(final_compute, output_compute_file)

    print(f"\n转换完成 (V5 计算单元封装版)!")
    print(f"- Node数量: {len(final_nodes)}")
    print(f"- Compute规则数: {len(final_compute)}")
    print(f"- 计算单元已正确使用 () 包裹")
    print(f"- 节点文件: {output_node_file}")
    print(f"- 规则文件: {output_compute_file}")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='将流程图flow.json转换为node.json和compute.json (V5计算单元封装版)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理拒片流程，输出到同目录
  python flow2data.py -i data/拒片流程/flow.json

  # 指定输出目录
  python flow2data.py -i data/拒片流程/flow.json -o output_dir

  # 处理当前目录的flow.json
  python flow2data.py -i flow.json

特性:
  - 不生成额外的虚拟节点ID
  - 将条件直接编码到逻辑表达式中
  - 计算单元用 () 包裹，便于后续解析为虚拟节点
  - 严格保持原始节点ID不变
        """
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='输入的flow.json文件路径'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='输出目录路径（默认为flow.json所在目录）'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 检查输入文件是否存在
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}")
        return

    # 执行转换
    process_flow(input_file, args.output)


if __name__ == "__main__":
    main()
