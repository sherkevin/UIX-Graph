from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import (
    ontology, knowledge, diagnosis, visualization,
    propagation, full_graph, entity, reject_errors, diagnosis_prd1
)

app = FastAPI(
    title="UIX-Graph API",
    description="光刻机拒片根因分析系统 - 基于 PRD1 规范",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 版本前缀
API_V1_PREFIX = "/api/v1"

# 注册路由 - PRD1 规范
app.include_router(
    reject_errors.router,
    prefix=API_V1_PREFIX + "/reject-errors",
    tags=["拒片故障管理 (PRD1)"]
)

app.include_router(
    diagnosis_prd1.router,
    prefix=API_V1_PREFIX + "/diagnosis",
    tags=["诊断分析 (PRD1)"]
)

# 保留原有路由（向后兼容）
app.include_router(ontology.router, prefix="/api/ontology", tags=["本体管理"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识录入"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["诊断推理"])
app.include_router(visualization.router, prefix="/api/visualization", tags=["可视化"])
app.include_router(propagation.router, prefix="/api/propagation", tags=["故障传播"])
app.include_router(entity.router, prefix="/api/entity", tags=["实体详情"])
app.include_router(full_graph.router, prefix="/api/graph", tags=["全图谱"])


@app.get("/")
async def root():
    return {
        "message": "UIX-Graph API",
        "version": "1.0.0",
        "docs": "/docs",
        "prd1_endpoints": {
            "reject_errors": "/api/v1/reject-errors",
            "diagnosis": "/api/v1/diagnosis"
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}
