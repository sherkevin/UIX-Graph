"""
诊断引擎 (Diagnosis Engine) - PRD1 规范实现
实现从传感器数据到故障根因的自动化推导
基于节点-边图谱结构，支持动态算子绑定
"""
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from app.schemas.diagnosis import Node, Edge, DiagnosisResult, NodeCategory
from app.core.operators import get_data_source_function, get_s2t_function


class DiagnosisEnginePRD1:
    """诊断引擎 - 执行故障诊断推理 (PRD1 规范)"""

    def __init__(self, graph_data: Dict[str, Any]):
        """
        初始化诊断引擎

        Args:
            graph_data: 包含 nodes 和 edges 的图谱数据
        """
        self.nodes: Dict[str, Node] = {}
        for node_data in graph_data.get("nodes", []):
            # 将字典转换为 Node 对象
            if isinstance(node_data, dict):
                self.nodes[node_data["id"]] = Node(**node_data)
            else:
                self.nodes[node_data.id] = node_data

        self.edges: List[Edge] = []
        for edge_data in graph_data.get("edges", []):
            # 将字典转换为 Edge 对象
            if isinstance(edge_data, dict):
                self.edges.append(Edge(**edge_data))
            else:
                self.edges.append(edge_data)

        # 构建邻接表：source_id -> [(edge, target_node)]
        self.adj_list: Dict[str, List[tuple[Edge, Node]]] = {}
        for edge in self.edges:
            if edge.source not in self.adj_list:
                self.adj_list[edge.source] = []
            target_node = self.nodes.get(edge.target)
            if target_node:
                self.adj_list[edge.source].append((edge, target_node))

        # 反向邻接表：target_id -> [source_node] (用于 RULE_LOGIC 节点)
        self.reverse_adj_list: Dict[str, List[Node]] = {}
        for edge in self.edges:
            if edge.target not in self.reverse_adj_list:
                self.reverse_adj_list[edge.target] = []
            source_node = self.nodes.get(edge.source)
            if source_node:
                self.reverse_adj_list[edge.target].append(source_node)

        # 传感器数据缓存
        self.sensor_data: Dict[str, Any] = {}

    def diagnose(self) -> DiagnosisResult:
        """
        执行诊断

        Returns:
            DiagnosisResult: 诊断结果
        """
        print("\n" + "="*60)
        print("开始故障诊断...")
        print("="*60)

        # 1. 读取所有 INDICATOR 节点的实时数据
        self._read_indicator_data()

        # 2. 执行推理，激活根因节点
        activated_root_causes, activated_paths = self._run_inference()

        # 3. 输出诊断结果
        self._print_results(activated_root_causes, activated_paths)

        # 4. 构建诊断结果
        return DiagnosisResult(
            root_causes=activated_root_causes,
            activated_paths=activated_paths,
            timestamp=datetime.now().isoformat(),
            sensor_data=self.sensor_data
        )

    def _read_indicator_data(self):
        """读取所有 INDICATOR 节点的数据"""
        print("\n[步骤 1] 读取传感器数据...")

        indicator_nodes = [
            node for node in self.nodes.values()
            if node.category == NodeCategory.INDICATOR
        ]

        for node in indicator_nodes:
            if node.operator and node.operator.data_source:
                try:
                    func = get_data_source_function(node.operator.data_source)
                    value = func()
                    self.sensor_data[node.id] = value
                    unit = node.attributes.unit or ""
                    print(f"  ✓ {node.label} ({node.id}): {value} {unit}")
                except Exception as e:
                    print(f"  ✗ {node.label} ({node.id}): 读取失败 - {e}")
                    self.sensor_data[node.id] = None

    def _run_inference(self) -> tuple[List[Node], List[List[str]]]:
        """
        执行推理逻辑

        Returns:
            (activated_root_causes, activated_paths)
        """
        print("\n[步骤 2] 执行推理...")

        activated_root_causes: List[Node] = []
        activated_paths: List[List[str]] = []
        visited: Set[str] = set()

        # 从每个 INDICATOR 节点开始推理
        indicator_nodes = [
            node for node in self.nodes.values()
            if node.category == NodeCategory.INDICATOR
        ]

        for start_node in indicator_nodes:
            current_value = self.sensor_data.get(start_node.id)
            if current_value is None:
                continue

            # DFS 遍历，激活路径
            path = [start_node.id]
            self._dfs_inference(start_node, current_value, path, visited, activated_root_causes, activated_paths)

        return activated_root_causes, activated_paths

    def _dfs_inference(
        self,
        current_node: Node,
        input_value: Any,
        current_path: List[str],
        visited: Set[str],
        activated_root_causes: List[Node],
        activated_paths: List[List[str]]
    ):
        """
        深度优先搜索推理

        Args:
            current_node: 当前节点
            input_value: 输入值
            current_path: 当前路径
            visited: 已访问节点集合
            activated_root_causes: 激活的根因列表（引用传递）
            activated_paths: 激活的路径列表（引用传递）
        """
        node_id = current_node.id

        # 如果是 ROOT_CAUSE 节点，添加到激活列表
        if current_node.category == NodeCategory.ROOT_CAUSE:
            if current_node not in activated_root_causes:
                activated_root_causes.append(current_node)
                activated_paths.append(current_path.copy())
                classification = current_node.attributes.classification or "未分类"
                print(f"  ✓ 激活根因: {current_node.label} ({classification})")
                print(f"    路径: {' → '.join(current_path)}")
            return

        # 避免循环
        if node_id in visited:
            return

        visited.add(node_id)

        # 遍历出边
        for edge, target_node in self.adj_list.get(node_id, []):
            try:
                # 执行边的 s2t 推理
                should_activate = self._evaluate_edge(edge, input_value)

                if should_activate:
                    # 根据目标节点类型处理
                    if target_node.category == NodeCategory.RULE_LOGIC:
                        # 规则逻辑节点：需要聚合所有输入
                        self._handle_rule_logic_node(
                            target_node,
                            current_path + [target_node.id],
                            visited,
                            activated_root_causes,
                            activated_paths
                        )
                    else:
                        # 其他节点：继续 DFS
                        self._dfs_inference(
                            target_node,
                            input_value,
                            current_path + [target_node.id],
                            visited,
                            activated_root_causes,
                            activated_paths
                        )
            except Exception as e:
                print(f"  ✗ 评估边 {edge.source}→{edge.target} 失败: {e}")

    def _handle_rule_logic_node(
        self,
        rule_node: Node,
        path_from_source: List[str],
        visited: Set[str],
        activated_root_causes: List[Node],
        activated_paths: List[List[str]]
    ):
        """
        处理规则逻辑节点（聚合所有输入）

        Args:
            rule_node: 规则逻辑节点
            path_from_source: 从源节点到当前节点的路径
            visited: 已访问节点集合
            activated_root_causes: 激活的根因列表
            activated_paths: 激活的路径列表
        """
        # 收集所有输入到规则节点的值
        input_values = {}

        # 找到所有指向规则节点的边
        incoming_edges = [
            edge for edge in self.edges
            if edge.target == rule_node.id
        ]

        print(f"  → 聚合规则节点: {rule_node.label}")

        for edge in incoming_edges:
            source_node = self.nodes.get(edge.source)
            if not source_node:
                continue

            # 获取源节点的值
            if source_node.category == NodeCategory.INDICATOR:
                value = self.sensor_data.get(source_node.id)
            else:
                # 对于其他类型节点，使用节点 ID 作为值
                value = source_node.id

            # 使用边的 operator 获取传递后的值
            if edge.operator and edge.operator.s2t:
                try:
                    func = get_s2t_function(edge.operator.s2t)
                    transformed_value = func(value)
                    input_values[edge.source] = transformed_value
                    print(f"    - {source_node.label} → {transformed_value}")
                except Exception as e:
                    print(f"    - {source_node.label} → 传递失败: {e}")
                    input_values[edge.source] = value
            else:
                input_values[edge.source] = value

        # 执行规则节点的输出边推理
        for edge, target_node in self.adj_list.get(rule_node.id, []):
            try:
                # 执行 s2t 推理
                should_activate = self._evaluate_edge(edge, input_values)

                if should_activate:
                    self._dfs_inference(
                        target_node,
                        input_values,
                        path_from_source + [target_node.id],
                        visited,
                        activated_root_causes,
                        activated_paths
                    )
            except Exception as e:
                print(f"    ✗ 规则输出推理失败: {e}")

    def _evaluate_edge(self, edge: Edge, input_value: Any) -> bool:
        """
        评估边的推理条件

        Args:
            edge: 边
            input_value: 输入值（可能是单个值或字典）

        Returns:
            bool: 是否激活目标节点
        """
        if not edge.operator or not edge.operator.s2t:
            # 没有 operator 的边默认不激活
            return False

        try:
            func = get_s2t_function(edge.operator.s2t)
            result = func(input_value)
            return bool(result)
        except Exception as e:
            print(f"    ✗ S2T 函数 {edge.operator.s2t} 执行失败: {e}")
            return False

    def _print_results(self, root_causes: List[Node], paths: List[List[str]]):
        """打印诊断结果摘要"""
        print("\n" + "="*60)
        print("诊断结果")
        print("="*60)

        if root_causes:
            print(f"\n激活的根因节点 ({len(root_causes)}):")
            for rc in root_causes:
                classification = rc.attributes.classification or "未分类"
                print(f"  • {rc.label} ({classification})")

            print(f"\n激活的路径 ({len(paths)}):")
            for i, path in enumerate(paths, 1):
                path_str = " → ".join([self.nodes.get(nid, nid).label for nid in path])
                print(f"  {i}. {path_str}")
        else:
            print("\n未检测到明确的根因")

        print(f"\n传感器数据读取: {len(self.sensor_data)} 个指标")
        print("="*60 + "\n")


def diagnose_from_json(graph_json: Dict[str, Any]) -> DiagnosisResult:
    """
    从 JSON 数据执行诊断 (PRD1 规范)

    Args:
        graph_json: 图谱 JSON 数据

    Returns:
        DiagnosisResult: 诊断结果
    """
    engine = DiagnosisEnginePRD1(graph_json)
    return engine.diagnose()
