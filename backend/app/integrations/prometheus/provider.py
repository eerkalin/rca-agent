from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.observability.logging import elapsed_ms, log_event, sanitize_url


logger = logging.getLogger(__name__)


class PrometheusProvider:
    """Read-only Prometheus HTTP API client."""

    def __init__(self, config: dict, credentials: dict | None = None):
        self.config = config or {}
        self.credentials = credentials or {}

        base_url = self.config.get("base_url") or self.config.get("url")
        if not base_url:
            raise ValueError("Prometheus connection requires config.base_url")

        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(self.config.get("timeout_seconds", 10))
        self.verify_ssl = bool(self.config.get("verify_ssl", True))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = self.credentials.get("bearer_token") or self.credentials.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _auth(self):
        username = self.credentials.get("username")
        password = self.credentials.get("password")
        if username is not None and password is not None:
            return (username, password)
        return None

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        endpoint = f"{self.base_url}{path}"
        started = time.perf_counter()
        log_event(logger, logging.DEBUG, "prometheus.request.start", "Prometheus request started", method="GET", endpoint=sanitize_url(endpoint), timeout_seconds=self.timeout)
        try:
            with httpx.Client(
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=self._headers(),
                auth=self._auth(),
            ) as client:
                response = client.get(endpoint, params=params)
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
            log_event(logger, logging.INFO, "prometheus.request.success", "Prometheus request completed", method="GET", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started))
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "prometheus.request.failure", "Prometheus request failed", method="GET", endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Prometheus request failed endpoint=%s", sanitize_url(endpoint))
            raise

        if payload.get("status") != "success":
            error = payload.get("error") or "Prometheus returned non-success status"
            log_event(logger, logging.ERROR, "prometheus.response.failure", "Prometheus API returned failure", endpoint=sanitize_url(endpoint), error=error)
            raise RuntimeError(f"Prometheus query failed: {error}")
        return payload

    def test_connection(self) -> dict:
        payload = self._get("/api/v1/query", {"query": "vector(1)"})
        return {
            "connected": True,
            "provider": "prometheus",
            "result_count": len(payload.get("data", {}).get("result", [])),
        }

    def instant_query(self, promql: str, at: datetime | None = None) -> list[dict]:
        params: dict[str, Any] = {"query": promql}
        if at is not None:
            params["time"] = at.timestamp()
        log_event(logger, logging.DEBUG, "prometheus.query.instant", "Executing instant Prometheus query", query=promql)
        payload = self._get("/api/v1/query", params)
        result = payload.get("data", {}).get("result", [])
        log_event(logger, logging.DEBUG, "prometheus.query.result", "Prometheus instant query completed", result_count=len(result))
        return result

    def range_query(
        self,
        promql: str,
        start: datetime | None = None,
        end: datetime | None = None,
        step: str | int | None = None,
    ) -> list[dict]:
        end = end or datetime.now(timezone.utc)
        start = start or (end - timedelta(minutes=15))
        params = {
            "query": promql,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step or self.config.get("default_step", "30s"),
        }
        log_event(logger, logging.DEBUG, "prometheus.query.range", "Executing range Prometheus query", query=promql, start=start.isoformat(), end=end.isoformat(), step=params["step"])
        payload = self._get("/api/v1/query_range", params)
        result = payload.get("data", {}).get("result", [])
        log_event(logger, logging.DEBUG, "prometheus.query.result", "Prometheus range query completed", result_count=len(result))
        return result

    @staticmethod
    def render_query(template: str, variables: dict[str, Any]) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace("{" + key + "}", str(value or ""))
        return rendered

    def collect_configured_queries(
        self,
        queries: list[dict],
        variables: dict[str, Any],
        default_window_minutes: int = 15,
    ) -> dict:
        items = []
        log_event(logger, logging.INFO, "prometheus.collection.start", "Prometheus evidence collection started", configured_queries=len(queries))
        for query_config in queries:
            template = query_config.get("promql") or query_config.get("query")
            if not template:
                continue
            name = query_config.get("name") or template[:120]
            query = self.render_query(str(template), variables)
            mode = query_config.get("mode", "range")

            try:
                if mode == "instant":
                    result = self.instant_query(query)
                else:
                    window_minutes = int(query_config.get("window_minutes", default_window_minutes))
                    end = datetime.now(timezone.utc)
                    result = self.range_query(query, start=end - timedelta(minutes=window_minutes), end=end, step=query_config.get("step"))
                items.append({"name": name, "description": query_config.get("description"), "promql": query, "result": result})
            except Exception as exc:
                log_event(logger, logging.WARNING, "prometheus.collection.query_failure", "Configured Prometheus query failed", query_name=name, error_type=type(exc).__name__, error=str(exc))
                items.append({"name": name, "promql": query, "error": str(exc), "result": []})

        log_event(logger, logging.INFO, "prometheus.collection.complete", "Prometheus evidence collection completed", queries_executed=len(items), failed_queries=sum(1 for item in items if item.get("error")))
        return {"provider": "prometheus", "queries": items}
