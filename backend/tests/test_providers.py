import unittest

from app.integrations.prometheus.provider import PrometheusProvider
from app.rca.evidence_reducer import EvidenceReducer


class PrometheusProviderTests(unittest.TestCase):
    def test_render_query_replaces_context_placeholders(self):
        query = PrometheusProvider.render_query(
            'rate(http_requests_total{service="{service_name}",namespace="{namespace}"}[5m])',
            {"service_name": "payment", "namespace": "otel-demo"},
        )
        self.assertIn('service="payment"', query)
        self.assertIn('namespace="otel-demo"', query)


class EvidenceReducerTests(unittest.TestCase):
    def test_limits_elasticsearch_hits(self):
        evidence = [{"tool": {"tool_type": "logs", "provider_type": "elasticsearch"}, "logs": {"provider": "elasticsearch", "hits": [{"id": index} for index in range(200)]}}]
        reduced = EvidenceReducer.reduce(evidence)
        self.assertEqual(len(reduced[0]["logs"]["hits"]), EvidenceReducer.MAX_ELASTIC_HITS)

    def test_limits_prometheus_series_and_samples(self):
        series = [{"metric": {"instance": str(index)}, "values": [[sample, str(sample)] for sample in range(100)]} for index in range(100)]
        evidence = [{"tool": {"tool_type": "metrics", "provider_type": "prometheus"}, "metrics": {"provider": "prometheus", "queries": [{"name": "q", "promql": "up", "result": series}]}}]
        reduced = EvidenceReducer.reduce(evidence)
        result = reduced[0]["metrics"]["queries"][0]["result"]
        self.assertEqual(len(result), EvidenceReducer.MAX_METRIC_SERIES)
        self.assertEqual(len(result[0]["values"]), EvidenceReducer.MAX_SAMPLES_PER_SERIES)

    def test_limits_elastic_apm_traces(self):
        traces = [
            {"trace_id": f"trace-{i}", "documents": [{"id": j} for j in range(200)]}
            for i in range(20)
        ]
        evidence = [{
            "tool": {"tool_type": "traces", "provider_type": "elastic_apm"},
            "traces": {
                "provider": "elastic_apm",
                "trace_ids": [f"trace-{i}" for i in range(20)],
                "hits": [{"id": i} for i in range(100)],
                "traces": traces,
            },
        }]
        reduced = EvidenceReducer.reduce(evidence)[0]["traces"]
        self.assertEqual(len(reduced["trace_ids"]), EvidenceReducer.MAX_TRACES)
        self.assertEqual(len(reduced["hits"]), EvidenceReducer.MAX_TRACE_SEARCH_HITS)
        self.assertEqual(len(reduced["traces"]), EvidenceReducer.MAX_TRACES)
        self.assertEqual(len(reduced["traces"][0]["documents"]), EvidenceReducer.MAX_TRACE_DOCUMENTS)


if __name__ == "__main__":
    unittest.main()
