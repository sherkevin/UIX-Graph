"""
生成大量Mock数据（100+条）
包含本体数据和故障记录
"""
import json
import random
from datetime import datetime, timedelta
from app.models.database import (
    SessionLocal, init_db,
    FaultPhenomenonDB, SubsystemDB, ComponentDB, ParameterDB, RootCauseDB,
    FaultRecordDB, RelationshipDB
)

# 本体数据定义
PHENOMENA = [
    {"name": "对准重复性异常", "severity": "高"},
    {"name": "上片旋转超限", "severity": "高"},
    {"name": "真空吸附异常", "severity": "中"},
    {"name": "硅片漂移", "severity": "中"},
    {"name": "对准精度不足", "severity": "高"},
    {"name": "曝光剂量异常", "severity": "高"},
    {"name": "聚焦偏差", "severity": "中"},
    {"name": "扫描速度异常", "severity": "低"},
    {"name": "温度波动", "severity": "中"},
    {"name": "振动异常", "severity": "高"},
]

SUBSYSTEMS = [
    {"name": "WS 硅片台"},
    {"name": "Wafer Loader 预对准"},
    {"name": "Measurement 测量系统"},
    {"name": "Illumination 照明系统"},
    {"name": "Projection 投影系统"},
    {"name": "Stage 工作台"},
    {"name": "Environmental 环境控制"},
]

COMPONENTS = [
    {"name": "Chuck 1", "subsystem": "WS 硅片台"},
    {"name": "Chuck 2", "subsystem": "WS 硅片台"},
    {"name": "Chuck 1 真空系统", "subsystem": "WS 硅片台"},
    {"name": "Chuck 2 真空系统", "subsystem": "WS 硅片台"},
    {"name": "预对准传感器", "subsystem": "Wafer Loader 预对准"},
    {"name": "预对准电机", "subsystem": "Wafer Loader 预对准"},
    {"name": "CCD 相机", "subsystem": "Measurement 测量系统"},
    {"name": "激光干涉仪", "subsystem": "Measurement 测量系统"},
    {"name": "对准标记", "subsystem": "Measurement 测量系统"},
    {"name": "照明光源", "subsystem": "Illumination 照明系统"},
    {"name": "投影镜头", "subsystem": "Projection 投影系统"},
    {"name": "掩膜台", "subsystem": "Projection 投影系统"},
    {"name": "温度传感器", "subsystem": "Environmental 环境控制"},
    {"name": "振动传感器", "subsystem": "Environmental 环境控制"},
]

PARAMETERS = [
    {"name": "rotation_mean", "unit": "urad", "threshold": 300, "component": "Chuck 1"},
    {"name": "rotation_3sigma", "unit": "urad", "threshold": 350, "component": "Chuck 2"},
    {"name": "vacuum_level", "unit": "kpa", "threshold": 50, "component": "Chuck 1 真空系统"},
    {"name": "vacuum_kpa", "unit": "kpa", "threshold": 50, "component": "Chuck 2 真空系统"},
    {"name": "alignment_accuracy", "unit": "nm", "threshold": 10, "component": "CCD 相机"},
    {"name": "exposure_dose", "unit": "mJ/cm²", "threshold": 30, "component": "照明光源"},
    {"name": "focus_offset", "unit": "nm", "threshold": 100, "component": "投影镜头"},
    {"name": "scan_speed", "unit": "mm/s", "threshold": 500, "component": "Stage 工作台"},
    {"name": "temperature", "unit": "°C", "threshold": 0.1, "component": "温度传感器"},
    {"name": "vibration_level", "unit": "nm", "threshold": 5, "component": "振动传感器"},
]

ROOT_CAUSES = [
    {"name": "上片旋转机械超限", "category": "机械精度"},
    {"name": "WS 硬件物理损坏/泄露", "category": "硬件损耗"},
    {"name": "硅片前层形变", "category": "材料问题"},
    {"name": "算法阈值过紧", "category": "算法问题"},
    {"name": "环境干扰", "category": "环境因素"},
    {"name": "光学传感器老化", "category": "硬件损耗"},
    {"name": "真空泵故障", "category": "硬件损耗"},
    {"name": "温度控制失效", "category": "硬件损耗"},
    {"name": "振动源干扰", "category": "环境因素"},
    {"name": "校准参数偏差", "category": "算法问题"},
]

# 生成故障记录的模板
CASE_TEMPLATES = [
    {
        "phenomenon": "对准重复性异常",
        "subsystem": "WS 硅片台",
        "component": "Chuck 2",
        "params_template": {"rotation_mean": (300, 400), "rotation_3sigma": (350, 450)},
        "root_cause": "上片旋转机械超限",
    },
    {
        "phenomenon": "真空吸附异常",
        "subsystem": "WS 硅片台",
        "component": "Chuck 1 真空系统",
        "params_template": {"vacuum_level": (20, 45), "rotation_mean": (100, 200)},
        "root_cause": "WS 硬件物理损坏/泄露",
    },
    {
        "phenomenon": "对准精度不足",
        "subsystem": "Measurement 测量系统",
        "component": "CCD 相机",
        "params_template": {"alignment_accuracy": (10, 20)},
        "root_cause": "光学传感器老化",
    },
    {
        "phenomenon": "曝光剂量异常",
        "subsystem": "Illumination 照明系统",
        "component": "照明光源",
        "params_template": {"exposure_dose": (25, 35)},
        "root_cause": "算法阈值过紧",
    },
    {
        "phenomenon": "聚焦偏差",
        "subsystem": "Projection 投影系统",
        "component": "投影镜头",
        "params_template": {"focus_offset": (100, 200)},
        "root_cause": "校准参数偏差",
    },
    {
        "phenomenon": "温度波动",
        "subsystem": "Environmental 环境控制",
        "component": "温度传感器",
        "params_template": {"temperature": (0.1, 0.5)},
        "root_cause": "温度控制失效",
    },
    {
        "phenomenon": "振动异常",
        "subsystem": "Environmental 环境控制",
        "component": "振动传感器",
        "params_template": {"vibration_level": (5, 15)},
        "root_cause": "振动源干扰",
    },
    {
        "phenomenon": "硅片漂移",
        "subsystem": "WS 硅片台",
        "component": "Chuck 1",
        "params_template": {"rotation_mean": (200, 300), "vacuum_level": (30, 50)},
        "root_cause": "硅片前层形变",
    },
]


def init_ontology(db):
    """初始化本体数据"""
    print("正在初始化本体数据...")
    
    # 1. 创建分系统
    subsystem_map = {}
    for sub_data in SUBSYSTEMS:
        existing = db.query(SubsystemDB).filter(SubsystemDB.name == sub_data["name"]).first()
        if not existing:
            subsystem = SubsystemDB(name=sub_data["name"])
            db.add(subsystem)
            db.flush()
            subsystem_map[sub_data["name"]] = subsystem.id
        else:
            subsystem_map[sub_data["name"]] = existing.id
    
    # 2. 创建部件
    component_map = {}
    for comp_data in COMPONENTS:
        existing = db.query(ComponentDB).filter(ComponentDB.name == comp_data["name"]).first()
        if not existing:
            subsystem_id = subsystem_map.get(comp_data.get("subsystem"))
            component = ComponentDB(
                name=comp_data["name"],
                subsystem_id=subsystem_id
            )
            db.add(component)
            db.flush()
            component_map[comp_data["name"]] = component.id
        else:
            component_map[comp_data["name"]] = existing.id
    
    # 3. 创建参数
    parameter_map = {}
    for param_data in PARAMETERS:
        existing = db.query(ParameterDB).filter(ParameterDB.name == param_data["name"]).first()
        if not existing:
            component_id = component_map.get(param_data.get("component"))
            parameter = ParameterDB(
                name=param_data["name"],
                unit=param_data.get("unit"),
                threshold=param_data.get("threshold"),
                component_id=component_id
            )
            db.add(parameter)
            db.flush()
            parameter_map[param_data["name"]] = parameter.id
        else:
            parameter_map[param_data["name"]] = existing.id
    
    # 4. 创建故障现象
    phenomenon_map = {}
    for phen_data in PHENOMENA:
        existing = db.query(FaultPhenomenonDB).filter(FaultPhenomenonDB.name == phen_data["name"]).first()
        if not existing:
            phenomenon = FaultPhenomenonDB(
                name=phen_data["name"],
                severity=phen_data.get("severity")
            )
            db.add(phenomenon)
            db.flush()
            phenomenon_map[phen_data["name"]] = phenomenon.id
        else:
            phenomenon_map[phen_data["name"]] = existing.id
    
    # 5. 创建根因
    rootcause_map = {}
    for rc_data in ROOT_CAUSES:
        existing = db.query(RootCauseDB).filter(RootCauseDB.name == rc_data["name"]).first()
        if not existing:
            rootcause = RootCauseDB(
                name=rc_data["name"],
                category=rc_data.get("category")
            )
            db.add(rootcause)
            db.flush()
            rootcause_map[rc_data["name"]] = rootcause.id
        else:
            rootcause_map[rc_data["name"]] = existing.id
    
    db.commit()
    print(f"✅ 本体数据初始化完成:")
    print(f"   - 故障现象: {len(phenomenon_map)}")
    print(f"   - 分系统: {len(subsystem_map)}")
    print(f"   - 部件: {len(component_map)}")
    print(f"   - 参数: {len(parameter_map)}")
    print(f"   - 根因: {len(rootcause_map)}")
    
    return {
        "phenomena": phenomenon_map,
        "subsystems": subsystem_map,
        "components": component_map,
        "parameters": parameter_map,
        "rootcauses": rootcause_map,
    }


def generate_fault_record(case_num, template):
    """生成单条故障记录"""
    case_id = f"CASE_{case_num:03d}"
    
    # 生成参数值
    params = {}
    for param_name, (min_val, max_val) in template["params_template"].items():
        if param_name in ["vacuum_level"]:
            params[param_name] = random.choice(["Low", "Normal", "High"])
        else:
            value = random.uniform(min_val, max_val)
            # 获取单位
            param_info = next((p for p in PARAMETERS if p["name"] == param_name), {})
            unit = param_info.get("unit", "")
            params[param_name] = f"{value:.2f} {unit}" if unit else f"{value:.2f}"
    
    # 生成逻辑链路
    logic_links = [
        f"{template['phenomenon']} -> {template['component']}异常",
        f"{template['phenomenon']} -> 参数超限 -> {template['root_cause']}",
        f"{template['phenomenon']} -> {template['subsystem']}故障 -> {template['root_cause']}",
    ]
    logic_link = random.choice(logic_links)
    
    # 随机确认状态
    is_confirmed = random.random() > 0.3  # 70%概率已确认
    
    # 随机时间（最近3个月）
    days_ago = random.randint(0, 90)
    created_at = datetime.now() - timedelta(days=days_ago)
    
    return {
        "case_id": case_id,
        "phenomenon": template["phenomenon"],
        "subsystem": template["subsystem"],
        "component": template["component"],
        "params": params,
        "logic_link": logic_link,
        "potential_root_cause": template["root_cause"],
        "is_confirmed": is_confirmed,
        "created_at": created_at,
    }


def generate_fault_records(db, count=120):
    """生成故障记录"""
    print(f"正在生成 {count} 条故障记录...")
    
    records = []
    for i in range(1, count + 1):
        template = random.choice(CASE_TEMPLATES)
        record_data = generate_fault_record(i, template)
        records.append(record_data)
    
    # 批量插入
    for record_data in records:
        existing = db.query(FaultRecordDB).filter(FaultRecordDB.case_id == record_data["case_id"]).first()
        if not existing:
            db_record = FaultRecordDB(
                case_id=record_data["case_id"],
                phenomenon=record_data["phenomenon"],
                subsystem=record_data["subsystem"],
                component=record_data["component"],
                params=json.dumps(record_data["params"], ensure_ascii=False),
                logic_link=record_data["logic_link"],
                potential_root_cause=record_data["potential_root_cause"],
                is_confirmed=record_data["is_confirmed"],
                created_at=record_data["created_at"]
            )
            db.add(db_record)
    
    db.commit()
    print(f"✅ 成功生成 {len(records)} 条故障记录")


def init_all_data():
    """初始化所有数据"""
    init_db()
    db = SessionLocal()
    
    try:
        # 检查是否已有大量数据
        existing_count = db.query(FaultRecordDB).count()
        if existing_count >= 100:
            print(f"数据库中已有 {existing_count} 条记录，跳过初始化")
            return
        
        # 初始化本体
        ontology_map = init_ontology(db)
        
        # 生成故障记录
        generate_fault_records(db, count=120)
        
        print("\n✅ 数据初始化完成！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 初始化数据失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    init_all_data()
