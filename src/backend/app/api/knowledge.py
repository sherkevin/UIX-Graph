"""
知识录入 API
管理故障记录的增删改查
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.models.database import get_db, FaultRecordDB
from app.schemas.ontology import FaultRecord, FaultRecordCreate
import json

router = APIRouter()


@router.get("/records")
def get_records(db: Session = Depends(get_db)):
    """获取所有故障记录"""
    records = db.query(FaultRecordDB).all()
    # 将 JSON 字符串转换为字典
    result = []
    for record in records:
        record_dict = {
            "id": record.id,
            "case_id": record.case_id,
            "phenomenon": record.phenomenon,
            "subsystem": record.subsystem,
            "component": record.component,
            "params": record.get_params_dict(),  # 转换为字典
            "logic_link": record.logic_link,
            "potential_root_cause": record.potential_root_cause,
            "is_confirmed": record.is_confirmed,
            "confidence": record.confidence
        }
        result.append(record_dict)
    return result


@router.get("/records/{case_id}")
def get_record(case_id: str, db: Session = Depends(get_db)):
    """获取单个故障记录"""
    record = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == case_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 将 JSON 字符串转换为字典
    record_dict = {
        "id": record.id,
        "case_id": record.case_id,
        "phenomenon": record.phenomenon,
        "subsystem": record.subsystem,
        "component": record.component,
        "params": record.get_params_dict(),
        "logic_link": record.logic_link,
        "potential_root_cause": record.potential_root_cause,
        "is_confirmed": record.is_confirmed,
        "confidence": record.confidence
    }
    return record_dict


@router.post("/records", response_model=FaultRecord)
def create_record(record: FaultRecordCreate, db: Session = Depends(get_db)):
    """创建故障记录"""
    # 检查 case_id 是否已存在
    existing = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == record.case_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="案例ID已存在")

    db_record = FaultRecordDB(
        case_id=record.case_id,
        phenomenon=record.phenomenon,
        subsystem=record.subsystem,
        component=record.component,
        params=json.dumps(record.params, ensure_ascii=False) if record.params else None,
        logic_link=record.logic_link,
        potential_root_cause=record.potential_root_cause,
        is_confirmed=record.is_confirmed
    )

    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    return db_record


@router.put("/records/{case_id}", response_model=FaultRecord)
def update_record(
    case_id: str,
    record: FaultRecordCreate,
    db: Session = Depends(get_db)
):
    """更新故障记录"""
    db_record = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == case_id
    ).first()

    if not db_record:
        raise HTTPException(status_code=404, detail="记录不存在")

    db_record.phenomenon = record.phenomenon
    db_record.subsystem = record.subsystem
    db_record.component = record.component
    db_record.params = json.dumps(record.params, ensure_ascii=False) if record.params else None
    db_record.logic_link = record.logic_link
    db_record.potential_root_cause = record.potential_root_cause
    db_record.is_confirmed = record.is_confirmed

    db.commit()
    db.refresh(db_record)

    return db_record


@router.delete("/records/{case_id}")
def delete_record(case_id: str, db: Session = Depends(get_db)):
    """删除故障记录"""
    db_record = db.query(FaultRecordDB).filter(
        FaultRecordDB.case_id == case_id
    ).first()

    if not db_record:
        raise HTTPException(status_code=404, detail="记录不存在")

    db.delete(db_record)
    db.commit()

    return {"message": "删除成功"}
