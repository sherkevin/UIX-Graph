"""
初始化数据脚本
加载示例故障记录数据
"""
import json
from app.models.database import SessionLocal, FaultRecordDB, init_db

# Mock 数据
MOCK_DATA = [
    {
        "case_id": "CASE_001",
        "phenomenon": "对准重复性异常",
        "subsystem": "WS 硅片台",
        "component": "Chuck 2",
        "params": {
            "rotation_mean": "357 urad",
            "status": "超出阈值"
        },
        "logic_link": "对准重复性异常 -> 上片旋转超限 -> Chuck2 承载",
        "potential_root_cause": "上片旋转机械超限",
        "is_confirmed": False
    },
    {
        "case_id": "CASE_005",
        "phenomenon": "真空吸附异常",
        "subsystem": "WS 硅片台",
        "component": "Chuck 1 真空系统",
        "params": {
            "vacuum_level": "Low",
            "rotation_mean": "150 urad"
        },
        "logic_link": "真空吸附力不足 -> 硅片漂移 -> 上片旋转异常 -> 拒片",
        "potential_root_cause": "WS 硬件物理损坏/泄露",
        "is_confirmed": True
    }
]


def init_mock_data():
    """初始化Mock数据"""
    init_db()
    db = SessionLocal()
    
    try:
        # 检查是否已有数据
        existing_count = db.query(FaultRecordDB).count()
        if existing_count > 0:
            print(f"数据库中已有 {existing_count} 条记录，跳过初始化")
            return
        
        # 插入Mock数据
        for record_data in MOCK_DATA:
            db_record = FaultRecordDB(
                case_id=record_data["case_id"],
                phenomenon=record_data["phenomenon"],
                subsystem=record_data.get("subsystem"),
                component=record_data.get("component"),
                params=json.dumps(record_data["params"], ensure_ascii=False),
                logic_link=record_data.get("logic_link"),
                potential_root_cause=record_data.get("potential_root_cause"),
                is_confirmed=record_data.get("is_confirmed", False)
            )
            db.add(db_record)
        
        db.commit()
        print(f"成功初始化 {len(MOCK_DATA)} 条Mock数据")
    except Exception as e:
        db.rollback()
        print(f"初始化数据失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_mock_data()
