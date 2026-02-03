"""
PRD1 诊断引擎测试脚本
验证诊断引擎在不同场景下的正确性
"""
import sys
import os
from pathlib import Path

# 设置UTF-8编码输出（Windows兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.test_data import DIAGNOSIS_GRAPH_EXAMPLE, TEST_CASES
from app.core.diagnosis_engine_prd1 import DiagnosisEnginePRD1
from app.core.operators import DATA_SOURCE_FUNCTIONS, S2T_FUNCTIONS
from typing import Dict, Any, List
import json


def inject_mock_sensor_values(mock_values: Dict[str, Any]):
    """
    注入模拟传感器数据到算子库

    Args:
        mock_values: {指标ID: 模拟值}
    """
    # 创建闭包来返回固定值
    for indicator_id, value in mock_values.items():
        if indicator_id == "IND_ROT_MEAN":
            DATA_SOURCE_FUNCTIONS["get_wafer_rotation_mean"] = lambda v=value: v
        elif indicator_id == "IND_ROT_3SIGMA":
            DATA_SOURCE_FUNCTIONS["get_wafer_rotation_sigma"] = lambda v=value: v
        elif indicator_id == "IND_VAC_LEVEL":
            DATA_SOURCE_FUNCTIONS["get_vacuum_sensor_state"] = lambda v=value: v


def reset_data_sources():
    """重置数据源函数为原始的随机函数"""
    import random

    def get_wafer_rotation_mean() -> float:
        return round(random.uniform(200, 400), 2)

    def get_wafer_rotation_sigma() -> float:
        return round(random.uniform(250, 450), 2)

    def get_vacuum_sensor_state() -> str:
        return random.choice(["High", "Low"])

    DATA_SOURCE_FUNCTIONS["get_wafer_rotation_mean"] = get_wafer_rotation_mean
    DATA_SOURCE_FUNCTIONS["get_wafer_rotation_sigma"] = get_wafer_rotation_sigma
    DATA_SOURCE_FUNCTIONS["get_vacuum_sensor_state"] = get_vacuum_sensor_state


def run_single_test_case(test_case: Dict[str, Any], engine: DiagnosisEnginePRD1) -> bool:
    """
    运行单个测试用例

    Args:
        test_case: 测试用例定义
        engine: 诊断引擎实例

    Returns:
        bool: 测试是否通过
    """
    print(f"\n{'='*70}")
    print(f"测试用例: {test_case['name']}")
    print(f"描述: {test_case['description']}")
    print(f"{'='*70}")

    # 注入模拟数据
    mock_values = test_case['mock_sensor_values']
    print(f"\n📊 注入传感器数据:")
    for indicator_id, value in mock_values.items():
        # 获取节点标签
        node = engine.nodes.get(indicator_id)
        label = node.label if node else indicator_id
        unit = node.attributes.unit if node and node.attributes else ""
        print(f"  • {label} ({indicator_id}): {value} {unit}")

    inject_mock_sensor_values(mock_values)

    # 执行诊断
    result = engine.diagnose()

    # 验证结果
    expected_root_cause = test_case['expected_root_cause']
    actual_root_causes = [rc.id for rc in result.root_causes]

    print(f"\n🎯 预期根因: {expected_root_cause}")
    print(f"🔍 实际激活: {actual_root_causes if actual_root_causes else '无'}")

    # 判断测试是否通过
    passed = False
    if expected_root_cause is None:
        passed = len(actual_root_causes) == 0
    elif isinstance(expected_root_cause, list):
        # 多个根因
        passed = set(actual_root_causes) == set(expected_root_cause)
    else:
        # 单个根因
        passed = len(actual_root_causes) == 1 and actual_root_causes[0] == expected_root_cause

    # 打印激活路径
    if result.activated_paths:
        print(f"\n📍 激活的传播路径 ({len(result.activated_paths)}):")
        for i, path in enumerate(result.activated_paths, 1):
            path_labels = []
            for node_id in path:
                node = engine.nodes.get(node_id)
                label = node.label if node else node_id
                path_labels.append(label)
            print(f"  {i}. {' → '.join(path_labels)}")

    # 打印测试结果
    if passed:
        print(f"\n✅ 测试通过")
    else:
        print(f"\n❌ 测试失败")
        if expected_root_cause != actual_root_causes:
            print(f"   期望: {expected_root_cause}")
            print(f"   实际: {actual_root_causes}")

    return passed


def print_graph_summary(graph_data: Dict[str, Any]):
    """打印图谱摘要信息"""
    print("\n" + "="*70)
    print("诊断图谱结构")
    print("="*70)

    nodes = graph_data['nodes']
    edges = graph_data['edges']

    # 按类型统计节点
    node_types = {}
    for node in nodes:
        category = node['category']
        node_types[category] = node_types.get(category, 0) + 1

    print(f"\n📈 节点统计 (共 {len(nodes)} 个):")
    for category, count in sorted(node_types.items()):
        print(f"  • {category}: {count} 个")

    print(f"\n🔗 边统计 (共 {len(edges)} 个):")
    relation_types = {}
    for edge in edges:
        relation = edge['relation']
        relation_types[relation] = relation_types.get(relation, 0) + 1

    for relation, count in sorted(relation_types.items()):
        print(f"  • {relation}: {count} 条")

    # 打印节点详情
    print(f"\n📋 节点详情:")
    for node in nodes:
        operator_info = ""
        if node.get('operator') and node['operator'].get('data_source'):
            operator_info = f" [数据源: {node['operator']['data_source']}]"

        print(f"  • {node['id']} ({node['label']}) - {node['category']}{operator_info}")

    # 打印边详情
    print(f"\n🔗 边详情:")
    for edge in edges:
        s2t_info = ""
        if edge.get('operator') and edge['operator'].get('s2t'):
            s2t_info = f" [推理: {edge['operator']['s2t']}]"

        print(f"  • {edge['source']} → {edge['target']} ({edge['relation']}){s2t_info}")


def main():
    """主测试函数"""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + " "*15 + "PRD1 诊断引擎测试套件" + " "*30 + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    # 1. 显示图谱结构
    print_graph_summary(DIAGNOSIS_GRAPH_EXAMPLE)

    # 2. 创建诊断引擎
    engine = DiagnosisEnginePRD1(DIAGNOSIS_GRAPH_EXAMPLE)

    # 3. 运行所有测试用例
    total_tests = len(TEST_CASES)
    passed_tests = 0

    print("\n" + "█"*70)
    print("█" + " "*25 + "开始运行测试" + " "*31 + "█")
    print("█"*70)

    for i, test_case in enumerate(TEST_CASES, 1):
        passed = run_single_test_case(test_case, engine)
        if passed:
            passed_tests += 1

        # 重置数据源
        reset_data_sources()

        # 清空传感器数据缓存
        engine.sensor_data = {}

    # 4. 打印测试摘要
    print("\n" + "█"*70)
    print("█" + " "*25 + "测试摘要" + " "*33 + "█")
    print("█"*70)
    print(f"\n总测试数: {total_tests}")
    print(f"通过: {passed_tests} ✅")
    print(f"失败: {total_tests - passed_tests} ❌")
    print(f"通过率: {passed_tests/total_tests*100:.1f}%")

    if passed_tests == total_tests:
        print("\n🎉 所有测试通过！诊断引擎工作正常。")
    else:
        print(f"\n⚠️  有 {total_tests - passed_tests} 个测试失败，请检查诊断引擎逻辑。")

    print("\n" + "█"*70 + "\n")

    return passed_tests == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
