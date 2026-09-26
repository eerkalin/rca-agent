from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.integrations.kubernetes.provider import KubernetesProvider


class KubernetesProviderFactoryTests(unittest.TestCase):
    @patch("app.integrations.kubernetes.factory.client.VersionApi")
    @patch("app.integrations.kubernetes.factory.client.AppsV1Api")
    @patch("app.integrations.kubernetes.factory.client.CoreV1Api")
    @patch("app.integrations.kubernetes.factory.kubernetes_config.load_kube_config_from_dict")
    def test_kubeconfig_is_loaded_from_encrypted_runtime_memory(
        self,
        load_from_dict,
        core_api,
        apps_api,
        version_api,
    ):
        runtime = {
            "config": {
                "mode": "kubeconfig",
                "context": "demo-context",
                "verify_ssl": True,
            },
            "credentials": {
                "kubeconfig": "apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\nusers: []\n",
            },
        }

        provider = KubernetesProviderFactory.create(runtime)

        self.assertEqual(provider.connection_mode, "kubeconfig")
        args, kwargs = load_from_dict.call_args
        self.assertEqual(args[0]["kind"], "Config")
        self.assertEqual(kwargs["context"], "demo-context")
        self.assertFalse(kwargs["persist_config"])
        core_api.assert_called_once()
        apps_api.assert_called_once()
        version_api.assert_called_once()

    def test_kubeconfig_mode_requires_secret(self):
        with self.assertRaisesRegex(ValueError, "encrypted credential field 'kubeconfig'"):
            KubernetesProviderFactory.create(
                {"config": {"mode": "kubeconfig"}, "credentials": {}}
            )

    @patch("app.integrations.kubernetes.factory.client.VersionApi")
    @patch("app.integrations.kubernetes.factory.client.AppsV1Api")
    @patch("app.integrations.kubernetes.factory.client.CoreV1Api")
    @patch("app.integrations.kubernetes.factory.kubernetes_config.load_incluster_config")
    def test_in_cluster_uses_isolated_configuration(
        self,
        load_incluster,
        core_api,
        apps_api,
        version_api,
    ):
        provider = KubernetesProviderFactory.create(
            {"config": {"mode": "in_cluster"}, "credentials": {}}
        )
        self.assertEqual(provider.connection_mode, "in_cluster")
        self.assertIn("client_configuration", load_incluster.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()


def test_capability_discovery_detects_k3s_and_optional_apis():
    provider = KubernetesProvider.__new__(KubernetesProvider)
    provider.version_api = SimpleNamespace(
        get_code=lambda: SimpleNamespace(git_version="v1.33.4+k3s1")
    )
    provider.core_api = SimpleNamespace(
        get_api_versions=lambda: SimpleNamespace(versions=["v1"])
    )
    provider.apis_api = SimpleNamespace(
        get_api_versions=lambda: SimpleNamespace(groups=[
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="apps/v1"),
            ]),
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="batch/v1"),
            ]),
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="networking.k8s.io/v1"),
            ]),
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="storage.k8s.io/v1"),
            ]),
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="discovery.k8s.io/v1"),
            ]),
            SimpleNamespace(versions=[
                SimpleNamespace(group_version="metrics.k8s.io/v1beta1"),
            ]),
        ])
    )

    profile = provider.discover_capabilities()

    assert profile["server_version"] == "v1.33.4+k3s1"
    assert profile["distribution"] == "k3s"
    assert profile["capabilities"]["core_v1"] is True
    assert profile["capabilities"]["apps_v1"] is True
    assert profile["capabilities"]["metrics_v1beta1"] is True
    assert profile["capabilities"]["autoscaling_v2"] is False


def test_capability_discovery_degrades_to_unknown_when_api_group_discovery_fails():
    provider = KubernetesProvider.__new__(KubernetesProvider)
    provider.version_api = SimpleNamespace(
        get_code=lambda: SimpleNamespace(git_version="v1.30.0")
    )
    provider.core_api = SimpleNamespace(
        get_api_versions=lambda: SimpleNamespace(versions=["v1"])
    )

    def fail_discovery():
        raise RuntimeError("discovery blocked")

    provider.apis_api = SimpleNamespace(get_api_versions=fail_discovery)

    profile = provider.discover_capabilities()

    assert profile["distribution"] == "kubernetes"
    assert profile["api_discovery_available"] is False
    assert profile["capabilities"]["core_v1"] is True
    assert profile["capabilities"]["apps_v1"] is None
    assert "discovery blocked" in profile["discovery_error"]
