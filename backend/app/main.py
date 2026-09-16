from fastapi import FastAPI
from sqlalchemy import text

from app.api.alerts import router as alerts_router
from app.db.session import engine
from app.api.kubernetes import router as kubernetes_router
from app.api.ai import router as ai_router
from app.api.scope import router as scope_router
from app.api.evidence import router as evidence_router
from app.api.investigations import router as investigations_router

app = FastAPI(
    title="RCA Agent",
    version="0.1.0",
)

app.include_router(
    investigations_router,
    prefix="/api/v1",
)

app.include_router(
    alerts_router,
    prefix="/api/v1",
)

app.include_router(
    evidence_router,
    prefix="/api/v1",
)

app.include_router(
    kubernetes_router,
    prefix="/api/v1",
)

app.include_router(
    ai_router,
    prefix="/api/v1",
)

app.include_router(
    scope_router,
    prefix="/api/v1",
)

@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "service": "rca-agent",
        "version": "0.1.0",
    }


@app.get("/api/v1/health/database")
async def database_health():
    with engine.connect() as connection:

        result = connection.execute(
            text("SELECT 1")
        )

        result.scalar_one()

    return {
        "status": "ok",
        "database": "mysql",
    }