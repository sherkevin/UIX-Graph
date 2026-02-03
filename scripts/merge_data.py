import json
import re
import argparse
from pathlib import Path
from collections import defaultdict


def find_data_dirs(data_root):
    """
    查找data目录下所有包含node.json和compute.json的子目录
    返回按数字排序的目录列表
    """
    data_root = Path(data_root)
    data_dirs = []

    for item in data_root.iterdir():
        if item.is_dir():
            node_file = item / "node.json"
            compute_file = item / "compute.json"
            if node_file.exists() and compute_file.exists():
                data_dirs.append(item)

    # 按目录名中的数字排序
    data_dirs.sort(key=lambda x: int(x.name) if x.name.isdigit() else float('inf'))

    return data_dirs


def load_data_from_dir(data_dir):
    """从目录加载node.json和compute.json"""
    node_file = data_dir / "node.json"
    compute_file = data_dir / "compute.json"

    with open(node_file, 'r', encoding='utf-8') as f:
        nodes = json.load(f)

    with open(compute_file, 'r', encoding='utf-8') as f:
        compute = json.load(f)

    return nodes, compute


def merge_all_data(data_root, output_dir=None):
    """
    合并所有数据目录中的node.json和compute.json

    Args:
        data_root: data目录路径
        output_dir: 输出目录路径（默认为data_root/merged）
    """
    data_root = Path(data_root)

    # 查找所有数据目录
    data_dirs = find_data_dirs(data_root)

    if not data_dirs:
        print(f"错误: 在 {data_root} 中未找到包含node.json和compute.json的子目录")
        return

    print(f"找到 {len(data_dirs)} 个数据目录:")
    for d in data_dirs:
        print(f"  - {d.name}")

    # 确定输出目录
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = data_root / "merged"

    output_dir.mkdir(parents=True, exist_ok=True)

    # 存储合并后的数据
    merged_nodes = {}
    merged_compute = {}

    # ID映射表：记录每个数据集的旧ID到新ID的映射
    # 格式: {数据集名: {旧ID: 新ID}}
    id_mappings = {}

    # 新ID计数器
    current_node_id = 1
    current_compute_id = 1

    # 遍历每个数据目录
    for data_dir in data_dirs:
        dataset_name = data_dir.name
        print(f"\n处理数据集: {dataset_name}")

        # 加载数据
        nodes, compute = load_data_from_dir(data_dir)

        # 创建此数据集的ID映射表
        node_id_map = {}
        compute_id_map = {}

        # 处理节点：重新编号
        for old_id, node_data in nodes.items():
            # 记录映射关系
            node_id_map[old_id] = str(current_node_id)

            # 创建新节点（添加数据集来源信息）
            new_node = node_data.copy()
            new_node["_dataset"] = dataset_name  # 记录来源数据集
            new_node["_original_id"] = old_id    # 记录原始ID

            merged_nodes[str(current_node_id)] = new_node
            current_node_id += 1

        # 处理compute：重新编号并更新引用
        for old_id, compute_data in compute.items():
            # 记录映射关系
            compute_id_map[old_id] = str(current_compute_id)

            # 更新target和operator中的ID引用
            old_target = compute_data["target"]
            new_target = replace_id_references(old_target, node_id_map)

            old_operator = compute_data["operator"]
            new_operator = replace_id_references(old_operator, node_id_map)

            # 创建新的compute条目
            merged_compute[str(current_compute_id)] = {
                "target": new_target,
                "operator": new_operator,
                "_dataset": dataset_name,
                "_original_id": old_id
            }

            current_compute_id += 1

        # 保存此数据集的映射关系
        id_mappings[dataset_name] = {
            "node_id_map": node_id_map,
            "compute_id_map": compute_id_map
        }

        print(f"  节点数: {len(nodes)}, compute数: {len(compute)}")

    # 保存合并后的数据
    output_node_file = output_dir / "node.json"
    output_compute_file = output_dir / "compute.json"
    output_mapping_file = output_dir / "id_mapping.json"

    with open(output_node_file, 'w', encoding='utf-8') as f:
        json.dump(merged_nodes, f, indent=4, ensure_ascii=False)

    with open(output_compute_file, 'w', encoding='utf-8') as f:
        json.dump(merged_compute, f, indent=4, ensure_ascii=False)

    with open(output_mapping_file, 'w', encoding='utf-8') as f:
        json.dump(id_mappings, f, indent=4, ensure_ascii=False)

    # 打印统计信息
    print(f"\n合并完成！")
    print(f"输出目录: {output_dir}")
    print(f"\n统计:")
    print(f"  总节点数: {len(merged_nodes)}")
    print(f"  总compute数: {len(merged_compute)}")
    print(f"  数据集数量: {len(data_dirs)}")
    print(f"\n生成的文件:")
    print(f"  - {output_node_file}")
    print(f"  - {output_compute_file}")
    print(f"  - {output_mapping_file} (ID映射关系)")


def replace_id_references(text, id_map):
    """
    替换文本中的ID引用 {id} 为新的ID

    Args:
        text: 包含ID引用的文本，如 "{1}||{2}"
        id_map: ID映射表 {旧ID: 新ID}

    Returns:
        替换后的文本
    """
    # 匹配 {数字} 格式的ID引用
    pattern = r'\{(\d+)\}'

    def replace_match(match):
        old_id = match.group(1)  # 提取数字
        new_id = id_map.get(old_id, old_id)  # 查找新ID，找不到则保持原样
        return "{" + new_id + "}"

    return re.sub(pattern, replace_match, text)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='合并多个数据集的node.json和compute.json'
    )
    parser.add_argument(
        '-d', '--data-dir',
        default="data",
        help='data目录路径（默认: data）'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='输出目录路径（默认: data/merged）'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 检查data目录是否存在
    data_root = Path(args.data_dir)
    if not data_root.exists():
        print(f"错误: data目录不存在: {data_root}")
        return

    # 执行合并
    merge_all_data(data_root, args.output)


if __name__ == "__main__":
    main()
