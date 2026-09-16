from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.observability.logging import elapsed_ms, log_event, sanitize_url


logger = logging.getLogger(__name__)


class ElasticsearchLogsProvider:
    """Read-only Elasticsearch Search API client for application logs."""

    def __init__(self, config: dict, credentials: dict | None = None):
        self.config = config or {}
        self.credentials = credentials or {}

        base_url = self.config.get("base_url") or self.config.get("url")
        if not base_url:
            raise ValueError("Elasticsearch connection requires config.base_url")

        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(self.config.get("timeout_seconds", 15))
        self.verify_ssl = bool(self.config.get("verify_ssl", True))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        api_key = self.credentials.get("api_key")
        bearer_token = self.credentials.get("bearer_token") or self.credentials.get("token")
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        elif bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        return headers

    def _auth(self):
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        if username is not None and password is not None:
            return (username, password)
        return None

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        endpoint = f"{self.base_url}{path}"
        started = time.perf_counter()
        log_event(logger, logging.DEBUG, "elasticsearch.request.start", "Elasticsearch request started", method=method, endpoint=sanitize_url(endpoint), timeout_seconds=self.timeout)
        try:
            with httpx.Client(timeout=self.timeout, verify=self.verify_ssl, headers=self._headers(), auth=self._auth()) as client:
                response = client.request(method, endpoint, json=json)
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
            log_event(logger, logging.INFO, "elasticsearch.request.success", "Elasticsearch request completed", method=method, endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started))
            return payload
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "elasticsearch.request.failure", "Elasticsearch request failed", method=method, endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Elasticsearch request failed method=%s endpoint=%s", method, sanitize_url(endpoint))
            raise

    def test_connection(self) -> dict:
        payload = self._request("GET", "/")
        return {"connected": True, "provider": "elasticsearch", "cluster_name": payload.get("cluster_name"), "version": (payload.get("version") or {}).get("number")}

    def search_logs(self, index_pattern: str, symptom: str | None = None, filters: dict[str, Any] | None = None, lookback_minutes: int = 15, size: int = 200, time_field: str = "@timestamp", message_fields: list[str] | None = None, source_fields: list[str] | None = None) -> dict:
        if not index_pattern:
            raise ValueError("Elasticsearch logs tool requires config.index_pattern")

        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        log_event(logger, logging.INFO, "elasticsearch.logs.search.start", "Elasticsearch log search started", index_pattern=index_pattern, lookback_minutes=lookback_minutes, requested_size=size, filters=filters or {})

        bool_query: dict[str, Any] = {"filter": [{"range": {time_field: {"gte": start.isoformat(), "lte": end.isoformat()}}}], "must": [], "should": []}
        for field, value in (filters or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, list):
                bool_query["filter"].append({"terms": {field: value}})
            else:
                bool_query["filter"].append({"term": {field: value}})

        if symptom:
            bool_query["should"].append({"multi_match": {"query": symptom, "fields": message_fields or ["message^3", "log.original^2", "error.message^3", "event.original"], "type": "best_fields"}})
            bool_query["minimum_should_match"] = 0

        bool_query["should"].extend([
            {"terms": {"log.level": ["error", "ERROR", "fatal", "FATAL"]}},
            {"terms": {"event.outcome": ["failure"]}},
            {"exists": {"field": "error.message"}},
        ])

        body = {
            "size": min(max(int(size), 1), 1000),
            "sort": [{time_field: {"order": "desc", "unmapped_type": "date"}}],
            "query": {"bool": bool_query},
            "_source": source_fields or [time_field, "message", "log.original", "log.level", "error.*", "service.*", "kubernetes.*", "trace.id", "span.id", "event.*", "host.*"],
        }

        payload = self._request("POST", f"/{index_pattern}/_search", json=body)
        hits = payload.get("hits", {}).get("hits", [])
        total = (payload.get("hits", {}).get("total") or {}).get("value")
        log_event(logger, logging.INFO, "elasticsearch.logs.search.complete", "Elasticsearch log search completed", index_pattern=index_pattern, returned_hits=len(hits), total_hits=total)
        return {"provider": "elasticsearch", "index_pattern": index_pattern, "lookback_minutes": lookback_minutes, "total": total, "hits": [{"index": hit.get("_index"), "id": hit.get("_id"), "score": hit.get("_score"), "source": hit.get("_source", {})} for hit in hits]}
