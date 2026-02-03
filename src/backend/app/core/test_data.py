"""
PRD1 诊断图谱示例数据
基于 PRD1.md 第 4 节的核心数据
"""
DIAGNOSIS_GRAPH_EXAMPLE = {
    "graph_info": {
        "title": "COWA Fault Diagnosis Graph",
        "version": "1.0"
    },
    "nodes": [
        {
            "id": "IND_ROT_MEAN",
            "label": "Rotation Mean",
            "category": "INDICATOR",
            "attributes": {
                "unit": "urad",
                "description": "晶圆旋转平均误差"
            },
            "operator": {
                "data_source": "get_wafer_rotation_mean"
            }
        },
        {
            "id": "IND_ROT_3SIGMA",
            "label": "Rotation 3Sigma",
            "category": "INDICATOR",
            "attributes": {
                "unit": "urad",
                "description": "晶圆旋转3倍标准差"
            },
            "operator": {
                "data_source": "get_wafer_rotation_sigma"
            }
        },
        {
            "id": "IND_VAC_LEVEL",
            "label": "Vacuum Level",
            "category": "INDICATOR",
            "attributes": {
                "unit": "State",
                "description": "真空吸附状态"
            },
            "operator": {
                "data_source": "get_vacuum_sensor_state"
            }
        },
        {
            "id": "RULE_NODE_COMBINED",
            "label": "真空&旋转联合判定",
            "category": "RULE_LOGIC",
            "attributes": {
                "logic": "AND"
            },
            "operator": {
                "data_source": "aggregate_inputs"
            }
        },
        {
            "id": "RC_MECH_LIMIT",
            "label": "上片旋转机械超限",
            "category": "ROOT_CAUSE",
            "attributes": {
                "classification": "机械精度"
            },
            "operator": {
                "data_source": "N/A"
            }
        },
        {
            "id": "RC_HW_LEAK",
            "label": "WS硬件物理损坏/泄露",
            "category": "ROOT_CAUSE",
            "attributes": {
                "classification": "硬件损耗"
            },
            "operator": {
                "data_source": "N/A"
            }
        },
        {
            "id": "COMP_WS",
            "label": "Wafer Stage",
            "category": "COMPONENT",
            "attributes": {},
            "operator": {}
        }
    ],
    "edges": [
        {
            "source": "IND_ROT_MEAN",
            "target": "RC_MECH_LIMIT",
            "relation": "DIAGNOSES",
            "operator": {
                "s2t": "op_gt_300"
            }
        },
        {
            "source": "IND_ROT_3SIGMA",
            "target": "RC_MECH_LIMIT",
            "relation": "DIAGNOSES",
            "operator": {
                "s2t": "op_gt_350"
            }
        },
        {
            "source": "IND_VAC_LEVEL",
            "target": "RULE_NODE_COMBINED",
            "relation": "INPUT_TO",
            "operator": {
                "s2t": "op_pass_value"
            }
        },
        {
            "source": "IND_ROT_MEAN",
            "target": "RULE_NODE_COMBINED",
            "relation": "INPUT_TO",
            "operator": {
                "s2t": "op_pass_value"
            }
        },
        {
            "source": "RULE_NODE_COMBINED",
            "target": "RC_HW_LEAK",
            "relation": "INFERS",
            "operator": {
                "s2t": "op_rule_vac_low_and_rot_gt_100"
            }
        },
        {
            "source": "COMP_WS",
            "target": "RC_MECH_LIMIT",
            "relation": "HAS_ISSUE"
        },
        {
            "source": "COMP_WS",
            "target": "RC_HW_LEAK",
            "relation": "HAS_ISSUE"
        }
    ]
}


# 测试用例：不同的传感器数据组合
TEST_CASES = [
    {
        "name": "测试用例 1: 旋转超限 (rotation_mean > 300)",
        "description": "应激活根因：上片旋转机械超限",
        "expected_root_cause": "RC_MECH_LIMIT",
        "mock_sensor_values": {
            "IND_ROT_MEAN": 350,
            "IND_ROT_3SIGMA": 360,
            "IND_VAC_LEVEL": "High"
        }
    },
    {
        "name": "测试用例 2: 真空吸附异常 (vacuum_level == Low AND rotation_mean > 100)",
        "description": "应激活根因：WS硬件物理损坏/泄露",
        "expected_root_cause": "RC_HW_LEAK",
        "mock_sensor_values": {
            "IND_ROT_MEAN": 150,
            "IND_ROT_3SIGMA": 200,
            "IND_VAC_LEVEL": "Low"
        }
    },
    {
        "name": "测试用例 3: 正常状态 (所有指标正常)",
        "description": "不应激活任何根因",
        "expected_root_cause": None,
        "mock_sensor_values": {
            "IND_ROT_MEAN": 50,
            "IND_ROT_3SIGMA": 80,
            "IND_VAC_LEVEL": "High"
        }
    },
    {
        "name": "测试用例 4: 同时满足多个规则 (rotation_mean > 300, vacuum_level == Low)",
        "description": "应激活两个根因：上片旋转机械超限 和 WS硬件物理损坏/泄露",
        "expected_root_cause": ["RC_MECH_LIMIT", "RC_HW_LEAK"],
        "mock_sensor_values": {
            "IND_ROT_MEAN": 350,
            "IND_ROT_3SIGMA": 400,
            "IND_VAC_LEVEL": "Low"
        }
    },
    {
        "name": "测试用例 5: 旋转 3-sigma 超限 (rotation_3sigma > 350)",
        "description": "应激活根因：上片旋转机械超限",
        "expected_root_cause": "RC_MECH_LIMIT",
        "mock_sensor_values": {
            "IND_ROT_MEAN": 250,
            "IND_ROT_3SIGMA": 400,
            "IND_VAC_LEVEL": "High"
        }
    }
]
