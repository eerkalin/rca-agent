from unittest.mock import patch

from app.integrations.elastic_apm.provider import ElasticAPMProvider


def test_search_traces_extracts_unique_trace_ids_and_scopes_service():
    provider = ElasticAPMProvider({"base_url": "https://elastic.example"})
    payload = {
        "hits": {
            "total": {"value": 3},
            "hits": [
                {"_index": "traces-apm", "_id": "1", "_source": {"trace": {"id": "a"}}},
                {"_index": "traces-apm", "_id": "2", "_source": {"trace": {"id": "a"}}},
                {"_index": "traces-apm", "_id": "3", "_source": {"trace": {"id": "b"}}},
            ],
        }
    }
    with patch.object(provider, "_request", return_value=payload) as request:
        result = provider.search_traces(
            index_pattern="traces-apm*",
            service_name="checkout",
            namespace="otel-demo",
        )
    assert result["trace_ids"] == ["a", "b"]
    body = request.call_args.kwargs["json"]
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"service.name": "checkout"}} in filters
    assert {"term": {"kubernetes.namespace": "otel-demo"}} in filters


def test_collect_trace_evidence_bounds_requested_trace_count():
    provider = ElasticAPMProvider({"base_url": "https://elastic.example"})
    search_result = {
        "provider": "elastic_apm",
        "index_pattern": "traces-apm*",
        "trace_ids": [f"t{i}" for i in range(30)],
        "hits": [],
    }
    with patch.object(provider, "search_traces", return_value=search_result), patch.object(
        provider, "get_trace", side_effect=lambda **kw: {"trace_id": kw["trace_id"], "documents": []}
    ) as get_trace:
        result = provider.collect_trace_evidence(
            {"index_pattern": "traces-apm*", "max_traces": 50},
            {"service_name": "checkout", "namespace": "otel-demo"},
        )
    assert len(result["traces"]) == 20
    assert get_trace.call_count == 20
