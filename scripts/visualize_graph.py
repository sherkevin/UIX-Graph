import json
import argparse
from pathlib import Path
from collections import defaultdict

try:
    from pyvis.network import Network
except ImportError:
    print("错误: 未安装pyvis库")
    print("请运行: pip install pyvis")
    exit(1)


# 为不同类型定义颜色
TYPE_COLORS = {
    "故障状态": "#FF6B6B",      # 红色
    "数据前置": "#4ECDC4",      # 青色
    "数据表征": "#45B7D1",      # 蓝色
    "虚拟分组": "#FFA07A",      # 橙色
    "算子": "#95E1D3",          # 绿色
    "默认": "#CCCCCC"           # 灰色
}


def get_node_color(node_type):
    """根据节点类型获取颜色"""
    return TYPE_COLORS.get(node_type, TYPE_COLORS["默认"])


def get_node_label(node_id, node_data):
    """
    获取节点显示的标签
    - 虚拟分组显示ID
    - 其他节点显示name
    """
    node_type = node_data.get("type", "")

    if node_type == "虚拟分组":
        return str(node_id)
    else:
        return node_data.get("name", str(node_id))


def visualize_graph(input_file, output_file, height="900px", width="100%"):
    """
    可视化图谱数据

    Args:
        input_file: 输入的graph_data.json文件路径
        output_file: 输出的HTML文件路径
        height: 画布高度
        width: 画布宽度
    """
    # 读取数据
    print(f"读取文件: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    nodes = data.get("nodes", {})
    edges = data.get("edges", [])

    print(f"节点数: {len(nodes)}, 边数: {len(edges)}")

    # 创建网络图
    net = Network(
        height=height,
        width=width,
        bgcolor="#ffffff",
        font_color="black",
        directed=True,  # 有向图
        cdn_resources='in_line'  # 使用内联资源，离线也能用
    )

    # 设置物理引擎参数，让布局更好看
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -8000,
          "centralGravity": 0.3,
          "springLength": 150,
          "springConstant": 0.04
        }
      },
      "nodes": {
        "borderWidth": 2,
        "borderWidthSelected": 3
      },
      "edges": {
        "width": 2,
        "smooth": {
          "type": "cubicBezier",
          "forceDirection": "horizontal",
          "roundness": 0.4
        },
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.5
          }
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 200
      }
    }
    """)

    # 统计节点类型
    type_counts = defaultdict(int)

    # 添加节点
    for node_id, node_data in nodes.items():
        node_type = node_data.get("type", "默认")
        type_counts[node_type] += 1

        # 获取标签
        label = get_node_label(node_id, node_data)

        # 获取颜色
        color = get_node_color(node_type)

        # 添加节点
        net.add_node(
            node_id,
            label=label,
            title=f"ID: {node_id}\n名称: {node_data.get('name', '')}\n类型: {node_type}",
            color=color,
            shape="circle",  # 圆形
            size=25,
            font={"size": 14, "color": "black"}
        )

    # 添加边
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        net.add_edge(source, target)

    # 生成HTML（手动保存以避免编码问题）
    print(f"生成可视化: {output_file}")
    html_content = net.generate_html()  # 先生成HTML内容
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # 打印统计信息
    print("\n节点类型统计:")
    for node_type, count in sorted(type_counts.items()):
        color_code = get_node_color(node_type)
        print(f"  {node_type}: {count} 个 (颜色: {color_code})")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='将graph_data.json可视化交互式图谱'
    )
    parser.add_argument(
        '-i', '--input',
        default=None,
        help='输入的graph_data.json文件路径（默认为scripts目录下的graph_data.json）'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='输出的HTML文件路径（默认为scripts目录下的graph_visualization.html）'
    )
    parser.add_argument(
        '--height',
        default="900px",
        help='画布高度（默认: 900px）'
    )
    parser.add_argument(
        '--width',
        default="100%",
        help='画布宽度（默认: 100%%）'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 确定默认路径
    scripts_dir = Path(__file__).parent

    # 输入文件
    if args.input:
        input_file = Path(args.input)
    else:
        input_file = scripts_dir / "graph_data.json"

    # 输出文件
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = scripts_dir / "graph_visualization.html"

    # 检查输入文件是否存在
    if not input_file.exists():
        print(f"错误: 输入文件不存在: {input_file}")
        print("\n提示:")
        print("1. 先运行 process_data.py 生成 graph_data.json")
        print("2. 或使用 -i 参数指定输入文件路径")
        return

    # 执行可视化
    visualize_graph(input_file, output_file, args.height, args.width)

    print(f"\n完成！请在浏览器中打开: {output_file.absolute()}")


if __name__ == "__main__":
    main()
