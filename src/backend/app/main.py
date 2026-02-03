from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import ontology, knowledge, diagnosis, visualization, propagation, full_graph, entity

app = FastAPI(
    title="SMEE-LITHO-RCA API",
    description="光刻机拒片根因分析系统",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(ontology.router, prefix="/api/ontology", tags=["本体管理"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识录入"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["诊断推理"])
app.include_router(visualization.router, prefix="/api/visualization", tags=["可视化"])
app.include_router(propagation.router, prefix="/api/propagation", tags=["故障传播"])
app.include_router(entity.router, prefix="/api/entity", tags=["实体详情"])
app.include_router(full_graph.router, prefix="/api/graph", tags=["全图谱"])


@app.get("/")
async def root():
    return {"message": "SMEE-LITHO-RCA API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
