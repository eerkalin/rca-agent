from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.repository import UserRepository
from app.auth.security import InvalidSessionToken, SessionTokenService
from app.auth.service import ROLE_ADMIN, ROLE_INVESTIGATOR, ROLE_READONLY
from app.config import settings
from app.db.session import SessionLocal
from app.observability.logging import log_event


logger = logging.getLogger(__name__)
SESSION_COOKIE = "rca_session"

PUBLIC_API_PATHS = {
    "/api/v1/health",
    "/api/v1/health/database",
    "/api/v1/auth/login",
    # Grafana is an integration endpoint rather than an interactive user API.
    # A dedicated webhook secret can be layered on independently without tying
    # Grafana to a human user session.
    "/api/v1/alerts/grafana",
}

INVESTIGATOR_POST_PREFIXES = (
    "/api/v1/investigations",
    "/api/v1/ai",
    "/api/v1/scope",
    "/api/v1/kubernetes",
)


def _extract_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def _is_investigator_action(request: Request) -> bool:
    if request.method != "POST":
        return False
    path = request.url.path
    if path.startswith(INVESTIGATOR_POST_PREFIXES):
        return True
    return path.startswith("/api/v1/connections/") and path.endswith("/test")


def _authorized(role: str, request: Request) -> bool:
    if role == ROLE_ADMIN:
        return True
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return role in {ROLE_INVESTIGATOR, ROLE_READONLY}
    if role == ROLE_INVESTIGATOR and _is_investigator_action(request):
        return True
    if request.url.path == "/api/v1/auth/logout" and request.method == "POST":
        return role in {ROLE_INVESTIGATOR, ROLE_READONLY}
    return False


async def auth_rbac_middleware(request: Request, call_next):
    if not settings.auth_enabled:
        request.state.auth_user = None
        request.state.auth_role = ROLE_ADMIN
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/v1") or path in PUBLIC_API_PATHS:
        return await call_next(request)

    try:
        token_service = SessionTokenService(
            settings.rca_auth_key,
            settings.auth_session_ttl_seconds,
        )
        token = _extract_token(request)
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        user_id = token_service.decode_user_id(token)
        with SessionLocal() as db:
            user = UserRepository.get(db, user_id)
            if user is None or not user.enabled:
                return JSONResponse(status_code=401, content={"detail": "Invalid session"})
            request.state.auth_user = {
                "id": user.id,
                "username": user.username,
                "role": user.role,
            }
            request.state.auth_role = user.role
    except InvalidSessionToken:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired session"})
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "auth.middleware.failure",
            "Authentication middleware failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return JSONResponse(status_code=500, content={"detail": "Authentication is not configured correctly"})

    if not _authorized(request.state.auth_role, request):
        log_event(
            logger,
            logging.WARNING,
            "auth.access.denied",
            "RBAC denied request",
            user_id=request.state.auth_user["id"],
            username=request.state.auth_user["username"],
            role=request.state.auth_role,
            method=request.method,
            path=path,
        )
        return JSONResponse(status_code=403, content={"detail": "Insufficient role permissions"})

    return await call_next(request)
