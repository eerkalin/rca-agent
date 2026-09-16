import unittest
from unittest.mock import patch

from app.integrations.kubernetes.factory import KubernetesProviderFactory


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
