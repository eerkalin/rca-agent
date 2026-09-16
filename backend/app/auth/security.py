from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet, InvalidToken


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


class AuthenticationConfigurationError(RuntimeError):
    pass


class InvalidSessionToken(ValueError):
    pass


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, salt_b64, digest_b64 = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class SessionTokenService:
    def __init__(self, key: str | None, ttl_seconds: int):
        if not key:
            raise AuthenticationConfigurationError(
                "RCA_AUTH_KEY is required when authentication is enabled"
            )
        try:
            self.fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise AuthenticationConfigurationError(
                "RCA_AUTH_KEY must be a valid Fernet key"
            ) from exc
        self.ttl_seconds = int(ttl_seconds)
        if self.ttl_seconds <= 0:
            raise AuthenticationConfigurationError(
                "AUTH_SESSION_TTL_SECONDS must be greater than zero"
            )

    def issue(self, user_id: int) -> str:
        payload = json.dumps({"user_id": int(user_id)}, separators=(",", ":")).encode("utf-8")
        return self.fernet.encrypt(payload).decode("ascii")

    def decode_user_id(self, token: str) -> int:
        try:
            payload = self.fernet.decrypt(
                token.encode("ascii"),
                ttl=self.ttl_seconds,
            )
            data = json.loads(payload.decode("utf-8"))
            return int(data["user_id"])
        except (InvalidToken, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidSessionToken("Invalid or expired session") from exc
