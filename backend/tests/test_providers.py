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
        evidence = [
            {
                "tool": {"tool_type": "logs", "provider_type": "elasticsearch"},
                "logs": {
                    "provider": "elasticsearch",
                    "hits": [{"id": index} for index in range(200)],
                },
            }
        ]
        reduced = EvidenceReducer.reduce(evidence)
        self.assertEqual(len(reduced[0]["logs"]["hits"]), EvidenceReducer.MAX_ELASTIC_HITS)

    def test_limits_prometheus_series_and_samples(self):
        series = [
            {
                "metric": {"instance": str(index)},
                "values": [[sample, str(sample)] for sample in range(100)],
            }
            for index in range(100)
        ]
        evidence = [
            {
                "tool": {"tool_type": "metrics", "provider_type": "prometheus"},
                "metrics": {
                    "provider": "prometheus",
                    "queries": [{"name": "q", "promql": "up", "result": series}],
                },
            }
        ]
        reduced = EvidenceReducer.reduce(evidence)
        result = reduced[0]["metrics"]["queries"][0]["result"]
        self.assertEqual(len(result), EvidenceReducer.MAX_METRIC_SERIES)
        self.assertEqual(len(result[0]["values"]), EvidenceReducer.MAX_SAMPLES_PER_SERIES)


if __name__ == "__main__":
    unittest.main()
