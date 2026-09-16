from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.observability.logging import elapsed_ms, log_event, sanitize_url


logger = logging.getLogger(__name__)


class ElasticAPMProvider:
    """Read-only Elastic APM trace search backed by Elasticsearch Search API."""

    def __init__(self, config: dict, credentials: dict | None = None):
        self.config = config or {}
        self.credentials = credentials or {}
        base_url = self.config.get("base_url") or self.config.get("url")
        if not base_url:
            raise ValueError("Elastic APM connection requires config.base_url")
        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(self.config.get("timeout_seconds", 15))
        self.verify_ssl = bool(self.config.get("verify_ssl", True))

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        api_key = self.credentials.get("api_key")
        bearer = self.credentials.get("bearer_token") or self.credentials.get("token")
        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        elif bearer:
            headers["Authorization"] = f"Bearer {bearer}"
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
        log_event(logger, logging.DEBUG, "elastic_apm.request.start", "Elastic APM request started", method=method, endpoint=sanitize_url(endpoint), timeout_seconds=self.timeout)
        try:
            with httpx.Client(timeout=self.timeout, verify=self.verify_ssl, headers=self._headers(), auth=self._auth()) as client:
                response = client.request(method, endpoint, json=json)
                status_code = response.status_code
                response.raise_for_status()
                payload = response.json()
            log_event(logger, logging.INFO, "elastic_apm.request.success", "Elastic APM request completed", method=method, endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started))
            return payload
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log_event(logger, logging.ERROR, "elastic_apm.request.failure", "Elastic APM request failed", method=method, endpoint=sanitize_url(endpoint), status_code=status_code, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Elastic APM request failed method=%s endpoint=%s", method, sanitize_url(endpoint))
            raise

    def test_connection(self) -> dict:
        payload = self._request("GET", "/")
        return {"connected": True, "provider": "elastic_apm", "cluster_name": payload.get("cluster_name"), "version": (payload.get("version") or {}).get("number")}

    @staticmethod
    def _source(hit: dict) -> dict:
        source = hit.get("_source", {})
        return {"index": hit.get("_index"), "id": hit.get("_id"), "source": source}

    def search_traces(self, index_pattern: str, service_name: str | None = None, namespace: str | None = None, filters: dict[str, Any] | None = None, lookback_minutes: int = 15, size: int = 100, time_field: str = "@timestamp", service_field: str = "service.name", namespace_field: str | None = "kubernetes.namespace", outcome_field: str = "event.outcome", trace_id_field: str = "trace.id", source_fields: list[str] | None = None) -> dict:
        if not index_pattern:
            raise ValueError("Elastic APM traces tool requires config.index_pattern")
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        log_event(logger, logging.INFO, "elastic_apm.search.start", "Elastic APM trace search started", index_pattern=index_pattern, service_name=service_name, namespace=namespace, lookback_minutes=lookback_minutes, requested_size=size)
        query_filter: list[dict] = [
            {"range": {time_field: {"gte": start.isoformat(), "lte": end.isoformat()}}},
            {"exists": {"field": trace_id_field}},
        ]
        if service_name:
            query_filter.append({"term": {service_field: service_name}})
        if namespace and namespace_field:
            query_filter.append({"term": {namespace_field: namespace}})
        for field, value in (filters or {}).items():
            if value in (None, ""):
                continue
            query_filter.append({"terms": {field: value}} if isinstance(value, list) else {"term": {field: value}})
        body = {
            "size": min(max(int(size), 1), 500),
            "sort": [{time_field: {"order": "desc", "unmapped_type": "date"}}],
            "query": {"bool": {"filter": query_filter, "should": [
                {"term": {outcome_field: "failure"}},
                {"exists": {"field": "error.id"}},
                {"exists": {"field": "error.exception.message"}},
            ]}},
            "_source": source_fields or [time_field, "trace.id", "transaction.id", "span.id", "parent.id", "service.name", "service.environment", "service.version", "kubernetes.namespace", "kubernetes.pod.name", "processor.event", "event.outcome", "transaction.*", "span.*", "http.*", "url.*", "destination.*", "error.*", "labels.*"],
        }
        payload = self._request("POST", f"/{index_pattern}/_search", json=body)
        hits = payload.get("hits", {}).get("hits", [])
        trace_ids = []
        for hit in hits:
            trace_id = (hit.get("_source") or {}).get("trace", {}).get("id")
            if trace_id and trace_id not in trace_ids:
                trace_ids.append(trace_id)
        total = (payload.get("hits", {}).get("total") or {}).get("value")
        log_event(logger, logging.INFO, "elastic_apm.search.complete", "Elastic APM trace search completed", returned_hits=len(hits), total_hits=total, trace_ids=len(trace_ids))
        return {"provider": "elastic_apm", "index_pattern": index_pattern, "lookback_minutes": lookback_minutes, "total": total, "trace_ids": trace_ids, "hits": [self._source(hit) for hit in hits]}

    def get_trace(self, index_pattern: str, trace_id: str, trace_id_field: str = "trace.id", time_field: str = "@timestamp", size: int = 300, source_fields: list[str] | None = None) -> dict:
        if not trace_id:
            raise ValueError("trace_id is required")
        log_event(logger, logging.DEBUG, "elastic_apm.trace.start", "Loading full trace", trace_id=trace_id, requested_size=size)
        body = {
            "size": min(max(int(size), 1), 1000),
            "sort": [{time_field: {"order": "asc", "unmapped_type": "date"}}],
            "query": {"term": {trace_id_field: trace_id}},
            "_source": source_fields or [time_field, "trace.id", "transaction.id", "span.id", "parent.id", "service.name", "service.environment", "processor.event", "event.outcome", "transaction.*", "span.*", "http.*", "url.*", "destination.*", "error.*"],
        }
        payload = self._request("POST", f"/{index_pattern}/_search", json=body)
        hits = payload.get("hits", {}).get("hits", [])
        log_event(logger, logging.DEBUG, "elastic_apm.trace.complete", "Full trace loaded", trace_id=trace_id, documents=len(hits))
        return {"trace_id": trace_id, "documents": [self._source(hit) for hit in hits]}

    def collect_trace_evidence(self, tool_config: dict, variables: dict) -> dict:
        index_pattern = tool_config.get("index_pattern", "traces-apm*,apm-*-transaction*,apm-*-span*,apm-*-error*")
        search = self.search_traces(
            index_pattern=index_pattern,
            service_name=variables.get("service_name"),
            namespace=variables.get("namespace"),
            filters=tool_config.get("filters") or {},
            lookback_minutes=int(tool_config.get("lookback_minutes", 15)),
            size=int(tool_config.get("search_size", 100)),
            time_field=tool_config.get("time_field", "@timestamp"),
            service_field=tool_config.get("service_field", "service.name"),
            namespace_field=tool_config.get("namespace_field", "kubernetes.namespace"),
            outcome_field=tool_config.get("outcome_field", "event.outcome"),
            trace_id_field=tool_config.get("trace_id_field", "trace.id"),
            source_fields=tool_config.get("source_fields"),
        )
        max_traces = min(max(int(tool_config.get("max_traces", 5)), 0), 20)
        traces = []
        for trace_id in search.get("trace_ids", [])[:max_traces]:
            try:
                traces.append(self.get_trace(index_pattern=index_pattern, trace_id=trace_id, trace_id_field=tool_config.get("trace_id_field", "trace.id"), time_field=tool_config.get("time_field", "@timestamp"), size=int(tool_config.get("max_documents_per_trace", 300)), source_fields=tool_config.get("source_fields")))
            except Exception as exc:
                log_event(logger, logging.WARNING, "elastic_apm.trace.failure", "Failed to load trace", trace_id=trace_id, error_type=type(exc).__name__, error=str(exc))
                traces.append({"trace_id": trace_id, "error": str(exc), "documents": []})
        log_event(logger, logging.INFO, "elastic_apm.collection.complete", "Elastic APM evidence collection completed", candidate_traces=len(search.get("trace_ids", [])), traces_loaded=len(traces))
        return {**search, "traces": traces}
