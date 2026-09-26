from __future__ import annotations

import re
from typing import Any


class SensitiveDataSanitizer:
    """Best-effort sanitizer for payloads that may be sent to an external LLM.

    Full evidence may remain in RCA Agent storage, but planner/final-RCA prompts
    receive only sanitized reduced evidence and a sanitized tool catalog.
    """

    REDACTED = "[REDACTED]"
    MAX_STRING_CHARS = 12_000

    _SENSITIVE_KEY_PARTS = (
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set_cookie",
        "client_secret",
        "private_key",
        "access_key",
        "credential",
        "card_number",
        "account_number",
        "iban",
        "pan",
    )

    _BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
    _BASIC_RE = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}")
    _JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
    _KV_SECRET_RE = re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret)"
        r"\s*[:=]\s*([^\s,;]+)"
    )
    _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ()\-]{8,}\d)(?!\w)")
    _URL_USERINFO_RE = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")

    @classmethod
    def _sensitive_key(cls, key: Any) -> bool:
        normalized = str(key).strip().lower().replace("-", "_")
        return any(part in normalized for part in cls._SENSITIVE_KEY_PARTS)

    @classmethod
    def sanitize_text(cls, value: str) -> str:
        text = value
        text = cls._BEARER_RE.sub("Bearer " + cls.REDACTED, text)
        text = cls._BASIC_RE.sub("Basic " + cls.REDACTED, text)
        text = cls._JWT_RE.sub(cls.REDACTED, text)
        text = cls._KV_SECRET_RE.sub(lambda m: f"{m.group(1)}={cls.REDACTED}", text)
        text = cls._URL_USERINFO_RE.sub(lambda m: m.group(1) + cls.REDACTED + "@", text)
        text = cls._EMAIL_RE.sub("[REDACTED_EMAIL]", text)
        text = cls._PHONE_RE.sub("[REDACTED_PHONE]", text)
        if len(text) > cls.MAX_STRING_CHARS:
            return text[: cls.MAX_STRING_CHARS] + "\n[truncated by RCA Agent sanitizer]"
        return text

    @classmethod
    def sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if cls._sensitive_key(key):
                    result[key] = cls.REDACTED
                else:
                    result[key] = cls.sanitize(item)
            return result
        if isinstance(value, list):
            return [cls.sanitize(item) for item in value]
        if isinstance(value, tuple):
            return [cls.sanitize(item) for item in value]
        if isinstance(value, str):
            return cls.sanitize_text(value)
        return value
