from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit


_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "bearer_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "rca_master_key",
    "database_url",
    "kubeconfig",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization:\s*(?:bearer|apikey)\s+)[^\s,]+"),
    re.compile(r"(?i)(password=)[^\s&]+"),
    re.compile(r"(?i)(api[_-]?key=)[^\s&]+"),
    re.compile(r"(?i)(token=)[^\s&]+"),
]


def set_request_id(value: str | None = None) -> str:
    request_id = value or uuid.uuid4().hex
    _request_id.set(request_id)
    return request_id


def get_request_id() -> str:
    return _request_id.get()


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except Exception:
        return value


def redact(value):
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or any(part in lowered for part in ("password", "secret", "token", "api_key", "kubeconfig")):
                result[key_text] = "***REDACTED***"
            else:
                result[key_text] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        text = value
        if "://" in text and "@" in text:
            text = sanitize_url(text)
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(r"\1***REDACTED***", text)
        return text
    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class HealthAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/v1/health" not in record.getMessage()


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", get_request_id()),
            "message": redact(record.getMessage()),
        }
        event = getattr(record, "event", None)
        fields = getattr(record, "fields", None)
        if event:
            payload["event"] = event
        if fields:
            payload.update(redact(fields))
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    resolved_level = getattr(logging, str(level).upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)
    root.setLevel(resolved_level)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(resolved_level)

    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = True
    access.setLevel(resolved_level)
    access.addFilter(HealthAccessFilter())


def log_event(logger: logging.Logger, level: int, event: str, message: str, **fields) -> None:
    logger.log(level, message, extra={"event": event, "fields": redact(fields)})


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
