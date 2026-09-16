import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.ai import router as ai_router
from app.api.alerts import router as alerts_router
from app.api.applications import router as applications_router
from app.api.connection_secrets import router as connection_secrets_router
from app.api.connection_tests import router as connection_tests_router
from app.api.evidence import router as evidence_router
from app.api.investigations import router as investigations_router
from app.api.kubernetes import router as kubernetes_router
from app.api.provider_catalog import router as provider_catalog_router
from app.api.scope import router as scope_router
from app.config import settings
from app.db.session import engine


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

app = FastAPI(title="RCA Agent", version="0.7.0")

app.include_router(applications_router, prefix="/api/v1")
app.include_router(connection_secrets_router, prefix="/api/v1")
app.include_router(connection_tests_router, prefix="/api/v1")
app.include_router(provider_catalog_router, prefix="/api/v1")
app.include_router(investigations_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")
app.include_router(kubernetes_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(scope_router, prefix="/api/v1")

ui_dir = Path(__file__).resolve().parent / "ui"
app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/ui/")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "rca-agent", "version": "0.7.0"}


@app.get("/api/v1/health/database")
async def database_health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
    return {"status": "ok", "database": "mysql"}
