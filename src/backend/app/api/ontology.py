"""
本体管理 API
管理知识图谱中的类和关系
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.models.database import get_db, OntologyClassDB, OntologyRelationDB
from app.schemas.ontology import (
    OntologyClass, OntologyClassCreate,
    OntologyRelation, OntologyRelationCreate
)

router = APIRouter()


# ========== 本体类管理 ==========
@router.get("/phenomena", response_model=List[OntologyClass])
def get_phenomena(db: Session = Depends(get_db)):
    """获取所有故障现象"""
    return db.query(OntologyClassDB).filter(
        OntologyClassDB.category == "现象"
    ).all()


@router.post("/phenomena", response_model=OntologyClass)
def create_phenomenon(
    phenomenon: OntologyClassCreate,
    db: Session = Depends(get_db)
):
    """创建故障现象"""
    db_obj = OntologyClassDB(
        name=phenomenon.name,
        category="现象",
        description=phenomenon.description,
        properties=phenomenon.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.get("/subsystems", response_model=List[OntologyClass])
def get_subsystems(db: Session = Depends(get_db)):
    """获取所有分系统"""
    return db.query(OntologyClassDB).filter(
        OntologyClassDB.category == "分系统"
    ).all()


@router.post("/subsystems", response_model=OntologyClass)
def create_subsystem(
    subsystem: OntologyClassCreate,
    db: Session = Depends(get_db)
):
    """创建分系统"""
    db_obj = OntologyClassDB(
        name=subsystem.name,
        category="分系统",
        description=subsystem.description,
        properties=subsystem.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.get("/components", response_model=List[OntologyClass])
def get_components(db: Session = Depends(get_db)):
    """获取所有部件"""
    return db.query(OntologyClassDB).filter(
        OntologyClassDB.category == "部件"
    ).all()


@router.post("/components", response_model=OntologyClass)
def create_component(
    component: OntologyClassCreate,
    db: Session = Depends(get_db)
):
    """创建部件"""
    db_obj = OntologyClassDB(
        name=component.name,
        category="部件",
        description=component.description,
        properties=component.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.get("/parameters", response_model=List[OntologyClass])
def get_parameters(db: Session = Depends(get_db)):
    """获取所有参数"""
    return db.query(OntologyClassDB).filter(
        OntologyClassDB.category == "参数"
    ).all()


@router.post("/parameters", response_model=OntologyClass)
def create_parameter(
    parameter: OntologyClassCreate,
    db: Session = Depends(get_db)
):
    """创建参数"""
    db_obj = OntologyClassDB(
        name=parameter.name,
        category="参数",
        description=parameter.description,
        properties=parameter.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.get("/rootcauses", response_model=List[OntologyClass])
def get_root_causes(db: Session = Depends(get_db)):
    """获取所有根因"""
    return db.query(OntologyClassDB).filter(
        OntologyClassDB.category == "根因"
    ).all()


@router.post("/rootcauses", response_model=OntologyClass)
def create_root_cause(
    rootcause: OntologyClassCreate,
    db: Session = Depends(get_db)
):
    """创建根因"""
    db_obj = OntologyClassDB(
        name=rootcause.name,
        category="根因",
        description=rootcause.description,
        properties=rootcause.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


# ========== 关系管理 ==========
@router.get("/relationships", response_model=List[OntologyRelation])
def get_relationships(db: Session = Depends(get_db)):
    """获取所有关系"""
    return db.query(OntologyRelationDB).all()


@router.post("/relationships", response_model=OntologyRelation)
def create_relationship(
    relation: OntologyRelationCreate,
    db: Session = Depends(get_db)
):
    """创建关系"""
    db_obj = OntologyRelationDB(
        source_id=relation.source_id,
        target_id=relation.target_id,
        relation_type=relation.relation_type,
        properties=relation.properties
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
