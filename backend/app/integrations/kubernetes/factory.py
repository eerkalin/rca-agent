from __future__ import annotations

import yaml
from kubernetes import client, config as kubernetes_config

from app.integrations.kubernetes.provider import KubernetesProvider


class KubernetesProviderFactory:
    """Build isolated Kubernetes clients from DB-backed runtime connections.

    The factory never persists kubeconfig data to disk. Kubeconfig credentials are
    expected to arrive from the encrypted connection credential store.
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
            raw_kubeconfig = (
                credentials.get("kubeconfig")
                or credentials.get("kubeconfig_yaml")
            )
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
            # Backward compatibility only. New UI configurations should use
            # encrypted kubeconfig mode instead of relying on host files.
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
        return KubernetesProvider(
            api_client=api_client,
            connection_mode=mode,
        )
