"""
诊断引擎 - PRD1 版本
基于 PRD1.md 中定义的诊断流程实现故障归因分析
"""
import json
from typing import Dict, List, Any, Optional
from app.services.mock_data_service import mock_data_service


class DiagnosisEnginePRD1:
    """
    PRD1 诊断引擎
    实现故障树与归因映射逻辑
    """

    # 故障状态与子系统/原因的映射关系
    FAULT_MAPPINGS = {
        "COWA拒片-对准倍率超限": {
            "causes": {
                "硅片质量问题": ["翘曲", "Mark问题"],
                "WH异常": ["Docking", "预对准", "交接"],
                "WS异常": ["控制性能", "吸盘", "上片偏差"]
            },
            "priority": 1
        },
        "COWA拒片-上片旋转超限": {
            "causes": {
                "前层存在旋转": None,
                "Mark质量不佳": None,
                "WS硬件问题": ["Docking plate", "吸盘", "Epin"],
                "上片问题": ["工艺适应性", "标定问题"]
            },
            "priority": 2
        },
        "COWA拒片-2DC补偿/WA/WRS": {
            "causes": {
                "WA异常": ["SBO异常", "对准焦距"],
                "WRS异常": ["扫描轨迹异常", "振动"],
                "WH异常": ["90度上片", "跳点"]
            },
            "priority": 3
        }
    }

    # 诊断流程判断优先级
    DIAGNOSIS_STEPS = [
        "magnification_check",  # 倍率检查
        "deviation_check",      # 偏差检查
        "rotation_check",       # 旋转检查
        "alignment_check",      # 标记对准检查
        "other_check"           # 其他检查
    ]

    @classmethod
    def analyze(cls, error_code: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        执行诊断分析

        Args:
            error_code: 错误代码
            params: 额外参数（如 wafer_id, layer, machine 等）

        Returns:
            诊断结果，包含根因和路径
        """
        # 获取图谱数据
        graph_data = mock_data_service.get_graph_data("merged")
        if not graph_data:
            return cls._fallback_diagnosis(error_code, params)

        nodes = graph_data.get('nodes', {})
        compute = graph_data.get('compute', {})

        # 查找匹配的故障节点
        fault_node_id = cls._find_fault_node(nodes, error_code)
        if not fault_node_id:
            return cls._fallback_diagnosis(error_code, params)

        # 执行诊断流程
        result = cls._execute_diagnosis_flow(
            fault_node_id,
            nodes,
            compute,
            params or {}
        )

        return result

    @classmethod
    def _find_fault_node(cls, nodes: Dict, error_code: str) -> Optional[str]:
        """在节点中查找匹配的故障节点"""
        for node_id, node_data in nodes.items():
            if node_data.get('name', '').lower() == error_code.lower():
                return node_id
        return None

    @classmethod
    def _execute_diagnosis_flow(
        cls,
        fault_node_id: str,
        nodes: Dict,
        compute: Dict,
        params: Dict
    ) -> Dict[str, Any]:
        """
        执行诊断流程

        按照优先级执行：
        1. 倍率检查
        2. 偏差检查
        3. 旋转检查
        4. 标记对准检查
        5. 其他检查
        """
        activated_paths = []
        root_causes = []

        # 获取故障节点的计算规则
        compute_rule = compute.get(fault_node_id)
        if not compute_rule:
            return cls._build_result(nodes, root_causes, activated_paths, params)

        operator_expr = compute_rule.get('operator', '')

        # 解析算子表达式，找到可能的根因
        # 例如："{3}||{4}||({5}||{6}||{7})"
        potential_causes = cls._parse_operator_expression(operator_expr)

        # 执行诊断步骤
        for step in cls.DIAGNOSIS_STEPS:
            step_result = cls._execute_diagnosis_step(
                step,
                potential_causes,
                nodes,
                params
            )

            if step_result['found']:
                root_causes.extend(step_result['causes'])
                activated_paths.extend(step_result['paths'])

                # 如果找到明确的根因，可以提前结束
                if step_result['confidence'] == 'high':
                    break

        return cls._build_result(nodes, root_causes, activated_paths, params)

    @classmethod
    def _execute_diagnosis_step(
        cls,
        step: str,
        potential_causes: List[str],
        nodes: Dict,
        params: Dict
    ) -> Dict[str, Any]:
        """
        执行单个诊断步骤
        """
        result = {
            'found': False,
            'causes': [],
            'paths': [],
            'confidence': 'low'
        }

        if step == "magnification_check":
            # 倍率检查：检查是否 M > 100ppm 或 20ppm < M < 100ppm
            m_value = params.get('magnification')
            if m_value:
                if m_value > 100 or (20 < m_value < 100):
                    result['found'] = True
                    result['confidence'] = 'high'
                    # 找到倍率相关的根因
                    for cause_id in potential_causes:
                        cause_data = nodes.get(cause_id, {})
                        if '倍率' in cause_data.get('name', ''):
                            result['causes'].append(cause_id)
                            result['paths'].append([cause_id])

        elif step == "deviation_check":
            # 偏差检查：拉取 Layer 上片偏差值 vs 均值
            deviation = params.get('deviation')
            layer_avg = params.get('layer_avg_deviation')

            if deviation and layer_avg:
                if abs(deviation - layer_avg) > 2:  # 阈值可配置
                    result['found'] = True
                    result['confidence'] = 'medium'
                    # 判定为上片工艺适应性问题或分系统硬件异常
                    for cause_id in potential_causes:
                        cause_data = nodes.get(cause_id, {})
                        name = cause_data.get('name', '')
                        if '上片' in name or 'WS' in cause_data.get('subsystem', ''):
                            result['causes'].append(cause_id)
                            result['paths'].append([cause_id])

        elif step == "rotation_check":
            # 旋转检查：拉取 Layer 上片旋转值 vs 均值
            rotation = params.get('rotation')
            layer_avg_rotation = params.get('layer_avg_rotation')

            if rotation and layer_avg_rotation:
                if abs(rotation - layer_avg_rotation) > 5:  # 阈值可配置
                    result['found'] = True
                    result['confidence'] = 'medium'
                    # 判定为工艺适应性或分系统异常
                    for cause_id in potential_causes:
                        cause_data = nodes.get(cause_id, {})
                        if '旋转' in cause_data.get('name', ''):
                            result['causes'].append(cause_id)
                            result['paths'].append([cause_id])

        elif step == "alignment_check":
            # 标记对准检查：检查 MCC 及 WQ 值
            mcc = params.get('mcc')
            wq = params.get('wq')

            if mcc is not None and wq is not None:
                if mcc == 0 or wq == 0:
                    result['found'] = True
                    result['confidence'] = 'high'
                    # 判定为上片异常
                    for cause_id in potential_causes:
                        cause_data = nodes.get(cause_id, {})
                        if '上片' in cause_data.get('name', ''):
                            result['causes'].append(cause_id)
                            result['paths'].append([cause_id])

        return result

    @classmethod
    def _parse_operator_expression(cls, expr: str) -> List[str]:
        """
        解析算子表达式，提取所有节点ID
        例如："{3}||{4}||({5}||{6}||{7})" -> ["3", "4", "5", "6", "7"]
        """
        import re
        pattern = r'\{(\d+)\}'
        matches = re.findall(pattern, expr)
        return matches

    @classmethod
    def _build_result(
        cls,
        nodes: Dict,
        root_cause_ids: List[str],
        paths: List[List[str]],
        params: Dict
    ) -> Dict[str, Any]:
        """构建诊断结果"""
        # 转换节点ID为节点信息
        root_cause_nodes = []
        for cause_id in root_cause_ids:
            if cause_id in nodes:
                node_data = nodes[cause_id]
                root_cause_nodes.append({
                    'id': cause_id,
                    'name': node_data.get('name'),
                    'type': node_data.get('type'),
                    'subsystem': node_data.get('subsystem')
                })

        return {
            'root_causes': root_cause_nodes,
            'activated_paths': paths,
            'timestamp': params.get('timestamp'),
            'input_params': params
        }

    @classmethod
    def _fallback_diagnosis(
        cls,
        error_code: str,
        params: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        降级诊断：当图谱数据不可用时使用
        返回预定义的故障映射
        """
        for fault_name, fault_info in cls.FAULT_MAPPINGS.items():
            if error_code.lower() in fault_name.lower():
                # 找到匹配的故障类型
                causes = fault_info['causes']

                root_causes = []
                paths = []

                for subsystem, sub_causes in causes.items():
                    if sub_causes:
                        for cause in sub_causes:
                            root_causes.append({
                                'id': f"fallback_{len(root_causes)}",
                                'name': cause,
                                'type': '故障状态',
                                'subsystem': subsystem if subsystem in ['WH', 'WS', 'WA', 'WRS'] else None
                            })
                            paths.append([f"fallback_{len(root_causes)-1}"])
                    else:
                        root_causes.append({
                            'id': f"fallback_{len(root_causes)}",
                            'name': subsystem,
                            'type': '故障状态'
                        })
                        paths.append([f"fallback_{len(root_causes)-1}"])

                return {
                    'root_causes': root_causes,
                    'activated_paths': paths,
                    'timestamp': params.get('timestamp') if params else None,
                    'input_params': params,
                    'fallback': True,
                    'message': '使用预定义故障映射进行诊断'
                }

        # 未找到匹配的故障
        return {
            'root_causes': [],
            'activated_paths': [],
            'timestamp': params.get('timestamp') if params else None,
            'input_params': params,
            'error': f'未知的错误代码: {error_code}'
        }
