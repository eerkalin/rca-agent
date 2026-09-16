from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


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
        with httpx.Client(
            timeout=self.timeout,
            verify=self.verify_ssl,
            headers=self._headers(),
            auth=self._auth(),
        ) as client:
            response = client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {payload.get('error') or payload}")
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
        payload = self._get("/api/v1/query", params)
        return payload.get("data", {}).get("result", [])

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
        payload = self._get("/api/v1/query_range", params)
        return payload.get("data", {}).get("result", [])

    @staticmethod
    def render_query(template: str, variables: dict[str, Any]) -> str:
        # Deliberately limited to simple placeholder substitution. The query
        # template itself is user-configured for an Application/Dependency.
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
                    window_minutes = int(
                        query_config.get("window_minutes", default_window_minutes)
                    )
                    end = datetime.now(timezone.utc)
                    result = self.range_query(
                        query,
                        start=end - timedelta(minutes=window_minutes),
                        end=end,
                        step=query_config.get("step"),
                    )
                items.append(
                    {
                        "name": name,
                        "description": query_config.get("description"),
                        "promql": query,
                        "result": result,
                    }
                )
            except Exception as exc:
                items.append(
                    {
                        "name": name,
                        "promql": query,
                        "error": str(exc),
                        "result": [],
                    }
                )

        return {"provider": "prometheus", "queries": items}
