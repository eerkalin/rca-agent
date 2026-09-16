from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.repository import UserRepository
from app.auth.security import hash_password, verify_password


ROLE_ADMIN = "admin"
ROLE_INVESTIGATOR = "investigator"
ROLE_READONLY = "readonly"
VALID_ROLES = {ROLE_ADMIN, ROLE_INVESTIGATOR, ROLE_READONLY}


class AuthenticationService:
    @staticmethod
    def serialize_user(user) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "enabled": user.enabled,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    @staticmethod
    def authenticate(db: Session, username: str, password: str):
        user = UserRepository.get_by_username(db, username.strip())
        if user is None or not user.enabled:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    def create_user(
        db: Session,
        username: str,
        password: str,
        role: str,
        enabled: bool = True,
    ):
        username = username.strip()
        if not username:
            raise ValueError("Username must not be empty")
        if role not in VALID_ROLES:
            raise ValueError(f"Unsupported role: {role}")
        if UserRepository.get_by_username(db, username) is not None:
            raise ValueError("Username already exists")
        return UserRepository.create(
            db,
            username=username,
            password_hash=hash_password(password),
            role=role,
            enabled=enabled,
        )

    @staticmethod
    def update_user(db: Session, user, **values):
        if "role" in values and values["role"] not in VALID_ROLES:
            raise ValueError(f"Unsupported role: {values['role']}")
        if "password" in values:
            password = values.pop("password")
            if password:
                values["password_hash"] = hash_password(password)
        if "username" in values:
            username = str(values["username"]).strip()
            if not username:
                raise ValueError("Username must not be empty")
            existing = UserRepository.get_by_username(db, username)
            if existing is not None and existing.id != user.id:
                raise ValueError("Username already exists")
            values["username"] = username
        return UserRepository.update(db, user, **values)

    @staticmethod
    def bootstrap_admin(
        db: Session,
        username: str | None,
        password: str | None,
    ):
        if UserRepository.count(db) > 0:
            return None
        if not username or not password:
            raise RuntimeError(
                "Authentication is enabled but no users exist. Set "
                "BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD for the first start."
            )
        return AuthenticationService.create_user(
            db=db,
            username=username,
            password=password,
            role=ROLE_ADMIN,
            enabled=True,
        )
