import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
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
from app.db.schema_compat import assert_schema_current, schema_status
from app.db.session import engine
from app.observability.logging import configure_logging, elapsed_ms, log_event, set_request_id


configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="RCA Agent", version="0.7.0")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = set_request_id(request.headers.get("x-request-id"))
    started = time.perf_counter()
    path = request.url.path
    is_health = path.startswith("/api/v1/health")
    if not is_health:
        log_event(
            logger,
            logging.INFO,
            "http.request.start",
            "HTTP request started",
            method=request.method,
            path=path,
            client=request.client.host if request.client else None,
        )
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "http.request.error",
            "Unhandled HTTP request error",
            method=request.method,
            path=path,
            elapsed_ms=elapsed_ms(started),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        logger.exception("Unhandled HTTP request error")
        raise
    response.headers["x-request-id"] = request_id
    if not is_health:
        level = logging.INFO if response.status_code < 400 else logging.WARNING
        log_event(
            logger,
            level,
            "http.request.complete",
            "HTTP request completed",
            method=request.method,
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms(started),
        )
    return response


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


@app.on_event("startup")
async def verify_database_schema() -> None:
    assert_schema_current(engine)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/ui/")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "rca-agent", "version": "0.7.0"}


@app.get("/api/v1/health/database")
async def database_health():
    started = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        migration_status = schema_status(engine)
        log_event(
            logger,
            logging.DEBUG,
            "health.database.ok",
            "Database health check succeeded",
            elapsed_ms=elapsed_ms(started),
            schema=migration_status,
        )
        return {
            "status": "ok" if migration_status["up_to_date"] else "error",
            "database": "mysql",
            "schema": migration_status,
        }
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "health.database.error",
            "Database health check failed",
            elapsed_ms=elapsed_ms(started),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        logger.exception("Database health check failed")
        raise
