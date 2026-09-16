from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth.middleware import SESSION_COOKIE
from app.auth.repository import UserRepository
from app.auth.security import SessionTokenService
from app.auth.service import AuthenticationService, ROLE_ADMIN, VALID_ROLES
from app.config import settings
from app.db.session import SessionLocal


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = "readonly"
    enabled: bool = True


class UserUpdateRequest(BaseModel):
    username: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = None
    enabled: bool | None = None


def _require_auth_enabled() -> None:
    if not settings.auth_enabled:
        raise HTTPException(status_code=409, detail="Authentication is disabled")


def _admin_count(db) -> int:
    return sum(1 for user in UserRepository.list(db) if user.enabled and user.role == ROLE_ADMIN)


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    _require_auth_enabled()
    with SessionLocal() as db:
        user = AuthenticationService.authenticate(db, request.username, request.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = SessionTokenService(
            settings.rca_auth_key,
            settings.auth_session_ttl_seconds,
        ).issue(user.id)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=settings.auth_session_ttl_seconds,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="lax",
            path="/",
        )
        return {
            "authenticated": True,
            "user": AuthenticationService.serialize_user(user),
        }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"authenticated": False}


@router.get("/me")
async def me(request: Request):
    if not settings.auth_enabled:
        return {"auth_enabled": False, "user": None, "effective_role": ROLE_ADMIN}
    return {
        "auth_enabled": True,
        "user": request.state.auth_user,
        "effective_role": request.state.auth_role,
    }


@router.get("/users")
async def list_users():
    _require_auth_enabled()
    with SessionLocal() as db:
        return {
            "items": [AuthenticationService.serialize_user(user) for user in UserRepository.list(db)],
            "roles": sorted(VALID_ROLES),
        }


@router.post("/users", status_code=201)
async def create_user(request: UserCreateRequest):
    _require_auth_enabled()
    with SessionLocal() as db:
        try:
            user = AuthenticationService.create_user(
                db=db,
                username=request.username,
                password=request.password,
                role=request.role,
                enabled=request.enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return AuthenticationService.serialize_user(user)


@router.patch("/users/{user_id}")
async def update_user(user_id: int, request: UserUpdateRequest):
    _require_auth_enabled()
    with SessionLocal() as db:
        user = UserRepository.get(db, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        values = request.model_dump(exclude_unset=True)
        if (
            user.role == ROLE_ADMIN
            and user.enabled
            and _admin_count(db) <= 1
            and (values.get("role", ROLE_ADMIN) != ROLE_ADMIN or values.get("enabled") is False)
        ):
            raise HTTPException(status_code=409, detail="Cannot disable or demote the last enabled administrator")
        try:
            user = AuthenticationService.update_user(db, user, **values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return AuthenticationService.serialize_user(user)


@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    _require_auth_enabled()
    with SessionLocal() as db:
        user = UserRepository.get(db, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user.role == ROLE_ADMIN and user.enabled and _admin_count(db) <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last enabled administrator")
        UserRepository.delete(db, user)
        return {"deleted": True, "user_id": user_id}
