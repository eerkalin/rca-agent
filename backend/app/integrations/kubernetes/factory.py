from __future__ import annotations

import yaml
from kubernetes import client, config as kubernetes_config

from app.integrations.kubernetes.provider import KubernetesProvider


class KubernetesProviderFactory:
    """Build isolated Kubernetes clients from DB-backed runtime connections.

    Kubeconfig data is decrypted in memory and loaded directly into a dedicated
    ``client.Configuration``. It is never intentionally persisted to disk and
    never copied into RCA evidence or LLM context.
    """

    @staticmethod
    def create(runtime: dict) -> KubernetesProvider:
        connection_config = runtime.get("config") or {}
        credentials = runtime.get("credentials") or {}
        mode = connection_config.get("mode", "in_cluster")

        configuration = client.Configuration()

        if mode == "in_cluster":
            kubernetes_config.load_incluster_config(
                client_configuration=configuration,
            )
        elif mode == "kubeconfig":
            raw_kubeconfig = credentials.get("kubeconfig") or credentials.get("kubeconfig_yaml")
            if not raw_kubeconfig:
                raise ValueError(
                    "Kubernetes kubeconfig mode requires encrypted credential field 'kubeconfig'"
                )

            if isinstance(raw_kubeconfig, str):
                parsed = yaml.safe_load(raw_kubeconfig)
            elif isinstance(raw_kubeconfig, dict):
                parsed = raw_kubeconfig
            else:
                raise ValueError("Kubernetes kubeconfig must be YAML text or an object")

            if not isinstance(parsed, dict):
                raise ValueError("Kubernetes kubeconfig did not parse into an object")

            kubernetes_config.load_kube_config_from_dict(
                parsed,
                context=connection_config.get("context") or None,
                client_configuration=configuration,
                persist_config=False,
            )
        elif mode == "local_kubeconfig":
            # Legacy compatibility. New UI-created connections use either
            # in_cluster or encrypted kubeconfig mode.
            kubernetes_config.load_kube_config(
                context=connection_config.get("context") or None,
                client_configuration=configuration,
                persist_config=False,
            )
        else:
            raise ValueError(f"Unsupported Kubernetes connection mode: {mode}")

        if "verify_ssl" in connection_config:
            configuration.verify_ssl = bool(connection_config["verify_ssl"])

        api_client = client.ApiClient(configuration=configuration)

        # KubernetesProvider historically loaded process-global config in its
        # constructor. Build an isolated instance without invoking that legacy
        # constructor so different Applications can safely target different
        # clusters in the same RCA Agent process.
        provider = KubernetesProvider.__new__(KubernetesProvider)
        provider.connection_mode = mode
        provider.core_v1 = client.CoreV1Api(api_client)
        provider.apps_v1 = client.AppsV1Api(api_client)
        provider.batch_v1 = client.BatchV1Api(api_client)
        provider.autoscaling_v2 = client.AutoscalingV2Api(api_client)
        provider.policy_v1 = client.PolicyV1Api(api_client)
        provider.networking_v1 = client.NetworkingV1Api(api_client)
        provider.storage_v1 = client.StorageV1Api(api_client)
        provider.discovery_v1 = client.DiscoveryV1Api(api_client)
        provider.custom_objects = client.CustomObjectsApi(api_client)
        provider.version_api = client.VersionApi(api_client)
        provider.api_client = api_client
        return provider
