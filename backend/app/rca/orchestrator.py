import json
import logging
import time

from sqlalchemy.orm import Session

from app.applications.context import ApplicationContextService
from app.applications.runtime import RuntimeConnectionResolver
from app.config import settings
from app.db.session import SessionLocal
from app.integrations.elastic_apm.provider import ElasticAPMProvider
from app.integrations.elasticsearch.provider import ElasticsearchLogsProvider
from app.integrations.gemini.provider import GeminiProvider
from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.integrations.llm.factory import LLMProviderFactory
from app.integrations.llm.recording import RecordingLLMProvider
from app.integrations.prometheus.provider import PrometheusProvider
from app.observability.logging import elapsed_ms, log_event, set_request_id
from app.rca.evidence_collector import EvidenceCollector
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.repository import InvestigationRepository
from app.rca.scope_resolver import ScopeResolver
from app.rca.tool_policy import ToolPolicy


logger = logging.getLogger(__name__)

MAX_AGENTIC_TRANSCRIPT_CHARS = 120_000


class RCAOrchestrator:
    def __init__(self):
        self.scope_resolver = ScopeResolver()
        self.evidence_collector = EvidenceCollector()
        self._kubernetes_providers: dict[int, object] = {}

    @staticmethod
    def _tool_descriptor(tool: dict) -> dict:
        return {"id": tool.get("id"), "tool_type": tool.get("tool_type"), "provider_type": tool.get("provider_type"), "connection_id": tool.get("connection_id")}

    @staticmethod
    def _safe_tool_context(tool: dict) -> dict:
        config = tool.get("config") or {}
        result = {
            "id": tool.get("id"),
            "tool_type": tool.get("tool_type"),
            "provider_type": tool.get("provider_type"),
        }
        if tool.get("priority") is not None:
            result["priority"] = tool.get("priority")

        if tool.get("tool_type") == "kubernetes" and tool.get("provider_type") == "kubernetes":
            namespaces = [str(item).strip() for item in (config.get("namespaces") or []) if str(item).strip()]
            if not namespaces and config.get("namespace"):
                namespaces = [str(config.get("namespace")).strip()]
            result["configured_scope"] = {
                "namespaces": namespaces,
                "tail_lines": config.get("tail_lines", 50),
            }
        elif tool.get("tool_type") == "metrics" and tool.get("provider_type") == "prometheus":
            query_names = []
            for item in config.get("queries") or []:
                if isinstance(item, dict) and item.get("name"):
                    query_names.append(str(item["name"]))
            result["configured_scope"] = {
                "preconfigured_query_names": query_names,
                "dynamic_promql_allowed": True,
            }
        elif tool.get("tool_type") == "logs" and tool.get("provider_type") in {"elasticsearch", "elastic"}:
            result["configured_scope"] = {
                "index_pattern": config.get("index_pattern"),
                "time_field": config.get("time_field", "@timestamp"),
                "service_field": config.get("service_field"),
                "namespace_field": config.get("namespace_field"),
                "lookback_minutes": config.get("lookback_minutes"),
            }
        elif tool.get("tool_type") == "traces" and tool.get("provider_type") == "elastic_apm":
            result["configured_scope"] = {
                "index_pattern": config.get("index_pattern"),
                "service_field": config.get("service_field"),
                "namespace_field": config.get("namespace_field"),
                "lookback_minutes": config.get("lookback_minutes"),
            }
        return result

    @classmethod
    def _llm_application_context(cls, context: dict) -> dict:
        application = context["application"]
        dependencies = []
        for dependency in context.get("dependencies", []):
            dependencies.append({
                "id": dependency.get("id"),
                "name": dependency.get("name"),
                "type": dependency.get("type"),
                "description": dependency.get("description"),
                "diagnostic_bindings": [
                    cls._safe_tool_context(tool)
                    for tool in dependency.get("tools", [])
                ],
            })

        return {
            "application": {
                "id": application.get("id"),
                "name": application.get("name"),
                "slug": application.get("slug"),
                "description": application.get("description"),
                "investigation_strategy": application.get("investigation_strategy"),
            },
            "enabled_diagnostic_bindings": [
                cls._safe_tool_context(tool)
                for tool in context.get("tools", [])
            ],
            "dependencies": dependencies,
        }

    @staticmethod
    def _variables(context: dict, candidate=None, dependency: dict | None = None) -> dict:
        application = context["application"]
        return {
            "application_id": application["id"],
            "application_name": application["name"],
            "application_slug": application["slug"],
            "service_name": getattr(candidate, "service_name", None),
            "namespace": getattr(candidate, "namespace", None),
            "dependency_name": (dependency or {}).get("name"),
            "dependency_type": (dependency or {}).get("type"),
        }

    @staticmethod
    def _legacy_llm():
        log_event(logger, logging.WARNING, "rca.llm.legacy", "Using legacy Gemini fallback")
        provider = GeminiProvider(
            config={"model": settings.gemini_model},
            credentials={"api_key": settings.gemini_api_key},
        )
        provider.provider_type = "gemini"
        return provider

    def _llm_provider(self, db: Session, context: dict):
        application = context["application"]
        connection_id = application.get("llm_connection_id")
        if connection_id is None:
            return self._legacy_llm()
        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
        log_event(logger, logging.INFO, "rca.llm.selected", "Resolved Application LLM provider", application_id=application.get("id"), connection_id=connection_id, provider_type=runtime.get("provider_type"), model=(application.get("llm_config") or {}).get("model") or (runtime.get("config") or {}).get("model"))
        provider = LLMProviderFactory.create(runtime, application.get("llm_config") or {})
        if not getattr(provider, "provider_type", None):
            provider.provider_type = runtime.get("provider_type")
        return provider

    @staticmethod
    def _analyze(query: str, evidence: list[dict], context: dict, llm):
        reduced = EvidenceReducer.reduce(evidence)
        compact_context = RCAOrchestrator._llm_application_context(context)
        log_event(logger, logging.INFO, "rca.analysis.start", "Starting LLM RCA analysis", evidence_items=len(evidence), reduced_evidence_items=len(reduced))
        started = time.perf_counter()
        result = llm.analyze_rca(symptom=query, evidence=reduced, application_context=compact_context)
        log_event(logger, logging.INFO, "rca.analysis.complete", "LLM RCA analysis completed", elapsed_ms=elapsed_ms(started), insufficient_evidence=result.insufficient_evidence, why_steps=len(result.five_whys or []))
        return result

    def _kubernetes_provider(self, db: Session, tool: dict):
        connection_id = tool.get("connection_id")
        if connection_id is None:
            raise ValueError("Kubernetes application tool requires connection_id. Configure a Kubernetes Connection in the UI.")
        if connection_id in self._kubernetes_providers:
            log_event(logger, logging.DEBUG, "rca.kubernetes.cache_hit", "Reusing Kubernetes provider", connection_id=connection_id)
            return self._kubernetes_providers[connection_id]
        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
        if runtime.get("provider_type") != "kubernetes":
            raise ValueError(f"Connection {connection_id} is not a Kubernetes connection")
        provider = KubernetesProviderFactory.create(runtime)
        self._kubernetes_providers[connection_id] = provider
        log_event(logger, logging.INFO, "rca.kubernetes.provider", "Created Kubernetes provider", connection_id=connection_id, mode=(runtime.get("config") or {}).get("mode"))
        return provider

    def _resolve_kubernetes_scope(self, db: Session, query: str, context: dict, llm):
        kubernetes_tool = ApplicationContextService.find_tool(context, tool_type="kubernetes", provider_type="kubernetes")
        if kubernetes_tool is None:
            log_event(logger, logging.INFO, "rca.scope.skip", "No Kubernetes tool configured; skipping Kubernetes scope resolution")
            return None, []
        provider = self._kubernetes_provider(db, kubernetes_tool)
        config = kubernetes_tool.get("config", {})
        namespaces = config.get("namespaces") or []
        namespace = config.get("namespace") if not namespaces else None
        started = time.perf_counter()
        log_event(logger, logging.INFO, "rca.scope.start", "Resolving Kubernetes investigation scope", namespaces=namespaces or ([namespace] if namespace else []))
        scope = self.scope_resolver.resolve(text=query, kubernetes=provider, llm=llm, namespace=namespace, namespaces=namespaces)
        candidates = list(scope.candidates)
        log_event(logger, logging.INFO, "rca.scope.complete", "Kubernetes scope resolved", namespaces=namespaces or ([namespace] if namespace else []), elapsed_ms=elapsed_ms(started), candidates=[{"service_name": item.service_name, "namespace": item.namespace, "confidence": item.confidence} for item in candidates], unresolved=scope.unresolved)
        return scope, candidates

    def _collect_kubernetes(self, db: Session, tool: dict, candidates: list, collect_all: bool) -> list[dict]:
        provider = self._kubernetes_provider(db, tool)
        if not candidates:
            config = tool.get("config", {})
            namespaces = list(config.get("namespaces") or [])
            if not namespaces and config.get("namespace"):
                namespaces = [config.get("namespace")]
            if namespaces:
                log_event(logger, logging.INFO, "rca.kubernetes.namespace_fallback", "No service candidate resolved; collecting namespace pod health", tool_id=tool.get("id"), namespaces=namespaces)
                snapshot = self.evidence_collector.collect_namespace_health(
                    kubernetes=provider,
                    namespaces=namespaces,
                )
                return [{
                    "tool": self._tool_descriptor(tool),
                    "scope_candidate": {},
                    "kubernetes": snapshot,
                }]
            log_event(logger, logging.WARNING, "rca.kubernetes.no_candidates", "Kubernetes collection skipped because no scope candidate and no namespace were resolved", tool_id=tool.get("id"))
            return [{"tool": self._tool_descriptor(tool), "error": "Kubernetes scope resolver did not identify a technical candidate and the tool has no namespace scope"}]
        selected = candidates if collect_all else candidates[:1]
        evidence = []
        for candidate in selected:
            started = time.perf_counter()
            log_event(logger, logging.INFO, "rca.kubernetes.collect.start", "Collecting Kubernetes evidence", tool_id=tool.get("id"), service_name=candidate.service_name, namespace=candidate.namespace)
            service_evidence = self.evidence_collector.collect_for_service(kubernetes=provider, namespace=candidate.namespace, service_name=candidate.service_name, tail_lines=int(tool.get("config", {}).get("tail_lines", 50)))
            log_event(logger, logging.INFO, "rca.kubernetes.collect.complete", "Kubernetes evidence collected", tool_id=tool.get("id"), service_name=candidate.service_name, namespace=candidate.namespace, elapsed_ms=elapsed_ms(started))
            evidence.append({"tool": self._tool_descriptor(tool), "scope_candidate": {"service_name": candidate.service_name, "namespace": candidate.namespace, "confidence": candidate.confidence, "reason": candidate.reason}, "kubernetes": service_evidence})
        return evidence

    def _collect_non_kubernetes_tool(self, db: Session, tool: dict, query: str, context: dict, candidate=None, dependency: dict | None = None) -> list[dict]:
        descriptor = self._tool_descriptor(tool)
        connection = RuntimeConnectionResolver.resolve(db, tool.get("connection_id"))
        variables = self._variables(context, candidate=candidate, dependency=dependency)
        base = {"tool": descriptor, "dependency": ({"id": dependency.get("id"), "name": dependency.get("name"), "type": dependency.get("type")} if dependency else None), "scope_candidate": ({"service_name": candidate.service_name, "namespace": candidate.namespace, "confidence": candidate.confidence, "reason": candidate.reason} if candidate else {})}
        tool_type = tool.get("tool_type")
        provider_type = tool.get("provider_type")
        started = time.perf_counter()
        log_event(logger, logging.INFO, "rca.tool.collect.start", "Collecting provider evidence", tool_id=tool.get("id"), tool_type=tool_type, provider_type=provider_type, connection_id=tool.get("connection_id"), dependency_name=(dependency or {}).get("name"))
        try:
            if tool_type == "metrics" and provider_type == "prometheus":
                provider = PrometheusProvider(config=connection.get("config", {}), credentials=connection.get("credentials", {}))
                metrics = self.evidence_collector.collect_prometheus(provider=provider, tool_config=tool.get("config", {}), variables=variables)
                result = [{**base, "metrics": metrics}]
            elif tool_type == "logs" and provider_type in {"elasticsearch", "elastic"}:
                provider = ElasticsearchLogsProvider(config=connection.get("config", {}), credentials=connection.get("credentials", {}))
                logs = self.evidence_collector.collect_elasticsearch_logs(provider=provider, tool_config=tool.get("config", {}), symptom=query, variables=variables)
                result = [{**base, "logs": logs}]
            elif tool_type == "traces" and provider_type == "elastic_apm":
                provider = ElasticAPMProvider(config=connection.get("config", {}), credentials=connection.get("credentials", {}))
                traces = self.evidence_collector.collect_elastic_apm(provider=provider, tool_config=tool.get("config", {}), variables=variables)
                result = [{**base, "traces": traces}]
            else:
                result = [{**base, "error": f"Provider {provider_type} for tool {tool_type} is configured but not implemented in this RCA Agent version"}]
            log_event(logger, logging.INFO, "rca.tool.collect.complete", "Provider evidence collection completed", tool_id=tool.get("id"), tool_type=tool_type, provider_type=provider_type, elapsed_ms=elapsed_ms(started), evidence_items=len(result))
            return result
        except Exception as exc:
            log_event(logger, logging.ERROR, "rca.tool.collect.failure", "Provider evidence collection failed", tool_id=tool.get("id"), tool_type=tool_type, provider_type=provider_type, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
            logger.exception("Evidence collection failed tool_id=%s provider=%s", tool.get("id"), provider_type)
            return [{**base, "error": str(exc)}]

    def _collect_application_tool(self, db: Session, tool: dict, query: str, context: dict, candidates: list, collect_all: bool) -> list[dict]:
        if tool.get("tool_type") == "kubernetes" and tool.get("provider_type") == "kubernetes":
            return self._collect_kubernetes(db=db, tool=tool, candidates=candidates, collect_all=collect_all)
        candidate = candidates[0] if candidates else None
        return self._collect_non_kubernetes_tool(db=db, tool=tool, query=query, context=context, candidate=candidate)

    def _collect_dependency_tool(self, db: Session, dependency: dict, tool: dict, query: str, context: dict, candidates: list) -> list[dict]:
        candidate = candidates[0] if candidates else None
        return self._collect_non_kubernetes_tool(db=db, tool=tool, query=query, context=context, candidate=candidate, dependency=dependency)

    @staticmethod
    def _configured_namespaces(tool: dict) -> list[str]:
        config = tool.get("config") or {}
        namespaces = [str(item).strip() for item in (config.get("namespaces") or []) if str(item).strip()]
        if not namespaces and config.get("namespace"):
            namespaces = [str(config["namespace"]).strip()]
        return namespaces

    def _agentic_tool_catalog(self, context: dict) -> tuple[list[dict], dict[str, tuple[dict, dict | None]]]:
        catalog: list[dict] = []
        bindings: dict[str, tuple[dict, dict | None]] = {}

        for tool in context["tools"]:
            key = f"application:{tool['id']}"
            bindings[key] = (tool, None)
            descriptor = {
                "tool_key": key,
                "scope": "application",
                "tool_type": tool.get("tool_type"),
                "provider_type": tool.get("provider_type"),
                "priority": tool.get("priority"),
                "read_only": True,
            }
            if tool.get("tool_type") == "kubernetes" and tool.get("provider_type") == "kubernetes":
                namespaces = self._configured_namespaces(tool)
                descriptor.update({
                    "description": "Read-only Kubernetes inspection for configured Application namespaces.",
                    "allowed_namespaces": namespaces,
                    "operations": [
                        {
                            "name": "namespace_health",
                            "description": "List pod readiness/current container state for one configured namespace or all configured namespaces.",
                            "arguments": {"operation": "namespace_health", "namespace": "optional configured namespace"},
                        },
                        {
                            "name": "pod_diagnostics",
                            "description": "Deep inspect one exact pod: status/conditions, requests and limits, QoS, owners, probes, images, restart/termination details, safe environment references, volumes, events and bounded current/previous logs. Literal env values, Secret values, probe headers and exec commands are never exposed.",
                            "arguments": {"operation": "pod_diagnostics", "namespace": "required configured namespace", "pod_name": "required exact pod name"},
                        },
                        {
                            "name": "pod_resources",
                            "description": "Inspect CPU/memory/ephemeral-storage requests and limits plus QoS for one exact pod.",
                            "arguments": {"operation": "pod_resources", "namespace": "required configured namespace", "pod_name": "required exact pod name"},
                        },
                        {
                            "name": "pod_logs",
                            "description": "Read bounded logs for one exact pod/container. Can request the previous terminated container log.",
                            "arguments": {"operation": "pod_logs", "namespace": "required configured namespace", "pod_name": "required exact pod name", "container_name": "required exact container name", "tail_lines": "optional integer max 500", "previous": "optional boolean"},
                        },
                        {
                            "name": "owner_chain",
                            "description": "Resolve controller ownership from an exact pod, for example Pod -> ReplicaSet -> Deployment or Pod -> Job.",
                            "arguments": {"operation": "owner_chain", "namespace": "required configured namespace", "pod_name": "required exact pod name"},
                        },
                        {
                            "name": "workload_diagnostics",
                            "description": "Inspect one exact Deployment, StatefulSet, DaemonSet, ReplicaSet, Job or CronJob: rollout/status, replicas, pod template, requests/limits, probes and safe configuration references.",
                            "arguments": {"operation": "workload_diagnostics", "namespace": "required configured namespace", "workload_kind": "required workload kind", "workload_name": "required exact workload name"},
                        },
                        {
                            "name": "node_diagnostics",
                            "description": "Inspect one exact node discovered from pod evidence: conditions/pressure, capacity, allocatable, taints and runtime/kubelet information.",
                            "arguments": {"operation": "node_diagnostics", "node_name": "required exact node name discovered from evidence"},
                        },
                        {
                            "name": "resource_usage",
                            "description": "Read current Metrics API usage for an exact pod or node when metrics.k8s.io is available.",
                            "arguments": {"operation": "resource_usage", "namespace": "required with pod_name", "pod_name": "optional exact pod name", "node_name": "optional exact node name; provide pod_name or node_name"},
                        },
                        {
                            "name": "namespace_constraints",
                            "description": "Inspect ResourceQuota and LimitRange constraints for one configured namespace.",
                            "arguments": {"operation": "namespace_constraints", "namespace": "required configured namespace"},
                        },
                        {
                            "name": "storage_diagnostics",
                            "description": "Inspect one exact PVC plus bound PV and StorageClass metadata without reading Secret data.",
                            "arguments": {"operation": "storage_diagnostics", "namespace": "required configured namespace", "pvc_name": "required exact PVC name discovered from pod volume evidence"},
                        },
                        {
                            "name": "networking_diagnostics",
                            "description": "Inspect bounded Ingress and NetworkPolicy configuration for one configured namespace. TLS Secret values are never read.",
                            "arguments": {"operation": "networking_diagnostics", "namespace": "required configured namespace"},
                        },
                        {
                            "name": "autoscaling_diagnostics",
                            "description": "Inspect HPA and PodDisruptionBudget state in one configured namespace, optionally filtered by workload.",
                            "arguments": {"operation": "autoscaling_diagnostics", "namespace": "required configured namespace", "workload_name": "optional exact workload name"},
                        },
                        {
                            "name": "resource_events",
                            "description": "Read bounded Kubernetes Events for one exact resource name inside a configured namespace.",
                            "arguments": {"operation": "resource_events", "namespace": "required configured namespace", "resource_name": "required exact resource name"},
                        },
                        {
                            "name": "service_diagnostics",
                            "description": "Inspect one Kubernetes Service, Endpoints, EndpointSlices and its selected pods/logs/events.",
                            "arguments": {"operation": "service_diagnostics", "namespace": "required configured namespace", "service_name": "required exact service name"},
                        },
                    ],
                })
            else:
                config = tool.get("config") or {}
                provider_type = tool.get("provider_type")
                tool_type = tool.get("tool_type")
                operations = []
                if tool_type == "metrics" and provider_type == "prometheus":
                    operations = [
                        {
                            "name": "configured_metrics",
                            "description": "Run the Application's preconfigured Prometheus queries.",
                            "arguments": {"operation": "configured_metrics"},
                        },
                        {
                            "name": "promql",
                            "description": "Run one read-only PromQL query chosen by the LLM.",
                            "arguments": {
                                "operation": "promql",
                                "promql": "required PromQL string",
                                "mode": "optional instant or range",
                                "window_minutes": "optional integer, max 120",
                                "step": "optional Prometheus step such as 30s",
                            },
                        },
                    ]
                elif tool_type == "logs" and provider_type in {"elasticsearch", "elastic"}:
                    operations = [{
                        "name": "search_logs",
                        "description": "Search configured read-only log indices. Index pattern remains fixed by Application configuration.",
                        "arguments": {
                            "operation": "search_logs",
                            "search_text": "optional text query",
                            "service_name": "optional exact service name",
                            "namespace": "optional namespace",
                            "lookback_minutes": "optional integer, max 120",
                            "size": "optional integer, max configured size",
                        },
                    }]
                elif tool_type == "traces" and provider_type == "elastic_apm":
                    operations = [{
                        "name": "search_traces",
                        "description": "Search configured Elastic APM trace indices and load bounded candidate traces.",
                        "arguments": {
                            "operation": "search_traces",
                            "service_name": "optional exact service name",
                            "namespace": "optional namespace",
                            "lookback_minutes": "optional integer, max 120",
                        },
                    }]
                descriptor.update({
                    "description": "Read-only observability binding. The LLM chooses one listed operation and its bounded arguments.",
                    "config_summary": {
                        key: value
                        for key, value in config.items()
                        if key not in {"queries", "filters", "source_fields", "message_fields"}
                    },
                    "operations": operations or [{
                        "name": "configured_collection",
                        "description": "Execute this configured read-only diagnostic binding.",
                        "arguments": {"operation": "configured_collection"},
                    }],
                })
            catalog.append(descriptor)

        for dependency in context["dependencies"]:
            for tool in dependency.get("tools", []):
                key = f"dependency:{dependency['id']}:{tool['id']}"
                bindings[key] = (tool, dependency)
                catalog.append({
                    "tool_key": key,
                    "scope": "dependency",
                    "dependency": {
                        "id": dependency.get("id"),
                        "name": dependency.get("name"),
                        "type": dependency.get("type"),
                        "description": dependency.get("description"),
                    },
                    "tool_type": tool.get("tool_type"),
                    "provider_type": tool.get("provider_type"),
                    "description": "Execute this configured read-only dependency diagnostic binding.",
                    "config": tool.get("config") or {},
                    "arguments": {},
                    "read_only": True,
                })

        return catalog, bindings

    @staticmethod
    def _choice_signature(tool_key: str, arguments: dict) -> str:
        return f"{tool_key}:{json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False, default=str)}"

    @staticmethod
    def _bounded_agentic_transcript(parts: list[str]) -> str:
        text = "\n\n".join(part for part in parts if part).strip()
        if len(text) <= MAX_AGENTIC_TRANSCRIPT_CHARS:
            return text
        keep_head = 8_000
        keep_tail = MAX_AGENTIC_TRANSCRIPT_CHARS - keep_head
        return (
            text[:keep_head]
            + "\n\n[... older transcript content truncated by RCA Agent ...]\n\n"
            + text[-keep_tail:]
        )

    @staticmethod
    def _tool_exchange_text(
        *,
        round_number: int,
        tool_key: str,
        reason: str,
        arguments: dict,
        observations: list[dict],
    ) -> str:
        reduced = EvidenceReducer.reduce(observations)
        operation = arguments.get("operation") or "configured_collection"
        return (
            f"ROUND {round_number} TOOL REQUEST\n"
            f"tool_key: {tool_key}\n"
            f"operation: {operation}\n"
            f"reason: {reason or 'No reason provided'}\n"
            f"arguments: {json.dumps(arguments or {}, ensure_ascii=False, default=str)}\n\n"
            f"ROUND {round_number} TOOL RESPONSE\n"
            f"{json.dumps(reduced, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _validate_agentic_namespace(tool: dict, namespace: str | None) -> str:
        allowed = RCAOrchestrator._configured_namespaces(tool)
        if not allowed:
            raise ValueError("Kubernetes tool has no configured namespace scope")
        if namespace is None:
            if len(allowed) == 1:
                return allowed[0]
            raise ValueError("A namespace is required when multiple namespaces are configured")
        namespace = str(namespace)
        if namespace not in allowed:
            raise ValueError(f"Namespace {namespace} is outside the configured Application scope")
        return namespace

    def _execute_agentic_choice(
        self,
        db: Session,
        *,
        tool: dict,
        dependency: dict | None,
        arguments: dict,
        query: str,
        context: dict,
    ) -> list[dict]:
        if tool.get("tool_type") != "kubernetes" or tool.get("provider_type") != "kubernetes":
            descriptor = self._tool_descriptor(tool)
            connection = RuntimeConnectionResolver.resolve(db, tool.get("connection_id"))
            provider_type = tool.get("provider_type")
            tool_type = tool.get("tool_type")
            config = tool.get("config") or {}
            operation = str((arguments or {}).get("operation") or "configured_collection")
            base = {
                "tool": descriptor,
                "dependency": (
                    {"id": dependency.get("id"), "name": dependency.get("name"), "type": dependency.get("type")}
                    if dependency else None
                ),
                "agentic_arguments": arguments or {},
                "scope_candidate": {},
            }

            if tool_type == "metrics" and provider_type == "prometheus":
                provider = PrometheusProvider(
                    config=connection.get("config", {}),
                    credentials=connection.get("credentials", {}),
                )
                if operation == "promql":
                    ToolPolicy.assert_allowed("prometheus", "query_range")
                    promql = str((arguments or {}).get("promql") or "").strip()
                    if not promql:
                        raise ValueError("promql operation requires promql")
                    mode = str((arguments or {}).get("mode") or "range")
                    if mode == "instant":
                        ToolPolicy.assert_allowed("prometheus", "query")
                        result = provider.instant_query(promql)
                    else:
                        from datetime import datetime, timedelta, timezone
                        window = min(max(int((arguments or {}).get("window_minutes") or 15), 1), 120)
                        end = datetime.now(timezone.utc)
                        result = provider.range_query(
                            promql,
                            start=end - timedelta(minutes=window),
                            end=end,
                            step=(arguments or {}).get("step"),
                        )
                    return [{**base, "metrics": {
                        "provider": "prometheus",
                        "queries": [{"name": "agentic_promql", "promql": promql, "result": result}],
                    }}]
                return self._collect_non_kubernetes_tool(
                    db=db,
                    tool=tool,
                    query=query,
                    context=context,
                    candidate=None,
                    dependency=dependency,
                )

            if tool_type == "logs" and provider_type in {"elasticsearch", "elastic"}:
                ToolPolicy.assert_allowed("elasticsearch", "search_logs")
                provider = ElasticsearchLogsProvider(
                    config=connection.get("config", {}),
                    credentials=connection.get("credentials", {}),
                )
                filters = dict(config.get("filters") or {})
                service_name = (arguments or {}).get("service_name")
                namespace = (arguments or {}).get("namespace")
                if service_name and config.get("service_field"):
                    filters[config["service_field"]] = service_name
                if namespace and config.get("namespace_field"):
                    filters[config["namespace_field"]] = namespace
                lookback = min(max(int((arguments or {}).get("lookback_minutes") or config.get("lookback_minutes", 15)), 1), 120)
                configured_size = min(max(int(config.get("size", 200)), 1), 1000)
                size = min(max(int((arguments or {}).get("size") or configured_size), 1), configured_size)
                logs = provider.search_logs(
                    index_pattern=config.get("index_pattern", ""),
                    symptom=(arguments or {}).get("search_text") or query,
                    filters=filters,
                    lookback_minutes=lookback,
                    size=size,
                    time_field=config.get("time_field", "@timestamp"),
                    message_fields=config.get("message_fields"),
                    source_fields=config.get("source_fields"),
                )
                return [{**base, "logs": logs}]

            if tool_type == "traces" and provider_type == "elastic_apm":
                ToolPolicy.assert_allowed("elastic_apm", "search_traces")
                ToolPolicy.assert_allowed("elastic_apm", "get_trace")
                provider = ElasticAPMProvider(
                    config=connection.get("config", {}),
                    credentials=connection.get("credentials", {}),
                )
                dynamic_config = dict(config)
                dynamic_config["lookback_minutes"] = min(
                    max(int((arguments or {}).get("lookback_minutes") or config.get("lookback_minutes", 15)), 1),
                    120,
                )
                variables = self._variables(context, candidate=None, dependency=dependency)
                if (arguments or {}).get("service_name"):
                    variables["service_name"] = (arguments or {}).get("service_name")
                if (arguments or {}).get("namespace"):
                    variables["namespace"] = (arguments or {}).get("namespace")
                traces = provider.collect_trace_evidence(
                    tool_config=dynamic_config,
                    variables=variables,
                )
                return [{**base, "traces": traces}]

            return self._collect_non_kubernetes_tool(
                db=db,
                tool=tool,
                query=query,
                context=context,
                candidate=None,
                dependency=dependency,
            )

        provider = self._kubernetes_provider(db, tool)
        operation = str((arguments or {}).get("operation") or "namespace_health")
        descriptor = self._tool_descriptor(tool)
        tail_lines = int((tool.get("config") or {}).get("tail_lines", 50))

        if operation == "namespace_health":
            requested_namespace = (arguments or {}).get("namespace")
            if requested_namespace:
                namespaces = [self._validate_agentic_namespace(tool, requested_namespace)]
            else:
                namespaces = self._configured_namespaces(tool)
                if not namespaces:
                    raise ValueError("Kubernetes tool has no configured namespace scope")
            snapshot = self.evidence_collector.collect_namespace_health(
                kubernetes=provider,
                namespaces=namespaces,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespaces": namespaces},
                "scope_candidate": {},
                "kubernetes": snapshot,
            }]

        if operation == "pod_diagnostics":
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            pod_name = str((arguments or {}).get("pod_name") or "").strip()
            if not pod_name:
                raise ValueError("pod_diagnostics requires pod_name")
            snapshot = self.evidence_collector.collect_pod_diagnostics(
                kubernetes=provider,
                namespace=namespace,
                pod_name=pod_name,
                tail_lines=tail_lines,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "pod_name": pod_name},
                "scope_candidate": {},
                "kubernetes": snapshot,
            }]

        if operation == "pod_resources":
            ToolPolicy.assert_allowed("kubernetes", "get_pod_resources")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            pod_name = str((arguments or {}).get("pod_name") or "").strip()
            if not pod_name:
                raise ValueError("pod_resources requires pod_name")
            snapshot = provider.get_pod_resources(namespace=namespace, pod_name=pod_name)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "pod_name": pod_name},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "pod_logs":
            ToolPolicy.assert_allowed("kubernetes", "get_logs")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            pod_name = str((arguments or {}).get("pod_name") or "").strip()
            container_name = str((arguments or {}).get("container_name") or "").strip()
            if not pod_name or not container_name:
                raise ValueError("pod_logs requires pod_name and container_name")
            requested_tail = int((arguments or {}).get("tail_lines") or tail_lines)
            bounded_tail = min(max(requested_tail, 1), 500)
            previous = bool((arguments or {}).get("previous", False))
            logs = provider.get_pod_logs(
                namespace=namespace,
                pod_name=pod_name,
                container=container_name,
                tail_lines=bounded_tail,
                previous=previous,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {
                    "operation": operation,
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": container_name,
                    "tail_lines": bounded_tail,
                    "previous": previous,
                },
                "scope_candidate": {},
                "kubernetes": {
                    "scope": operation,
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": container_name,
                    "previous": previous,
                    "logs": logs,
                },
            }]

        if operation == "owner_chain":
            ToolPolicy.assert_allowed("kubernetes", "get_owner_chain")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            pod_name = str((arguments or {}).get("pod_name") or "").strip()
            if not pod_name:
                raise ValueError("owner_chain requires pod_name")
            chain = provider.get_owner_chain(namespace=namespace, pod_name=pod_name)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "pod_name": pod_name},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, "namespace": namespace, "pod_name": pod_name, "owners": chain},
            }]

        if operation == "workload_diagnostics":
            ToolPolicy.assert_allowed("kubernetes", "get_workload")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            workload_kind = str((arguments or {}).get("workload_kind") or "").strip()
            workload_name = str((arguments or {}).get("workload_name") or "").strip()
            if not workload_kind or not workload_name:
                raise ValueError("workload_diagnostics requires workload_kind and workload_name")
            snapshot = provider.get_workload_diagnostics(
                namespace=namespace,
                workload_kind=workload_kind,
                workload_name=workload_name,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {
                    "operation": operation,
                    "namespace": namespace,
                    "workload_kind": workload_kind,
                    "workload_name": workload_name,
                },
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "node_diagnostics":
            ToolPolicy.assert_allowed("kubernetes", "get_node")
            node_name = str((arguments or {}).get("node_name") or "").strip()
            if not node_name:
                raise ValueError("node_diagnostics requires node_name")
            snapshot = provider.get_node_diagnostics(node_name=node_name)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "node_name": node_name},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "resource_usage":
            ToolPolicy.assert_allowed("kubernetes", "get_resource_usage")
            pod_name = str((arguments or {}).get("pod_name") or "").strip()
            node_name = str((arguments or {}).get("node_name") or "").strip()
            if pod_name:
                namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
                usage = provider.get_pod_resource_usage(namespace=namespace, pod_name=pod_name)
                target = {"namespace": namespace, "pod_name": pod_name}
            elif node_name:
                usage = provider.get_node_resource_usage(node_name=node_name)
                target = {"node_name": node_name}
            else:
                raise ValueError("resource_usage requires pod_name or node_name")
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, **target},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, "target": target, "usage": usage},
            }]

        if operation == "namespace_constraints":
            ToolPolicy.assert_allowed("kubernetes", "get_namespace_constraints")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            snapshot = provider.get_namespace_constraints(namespace=namespace)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "storage_diagnostics":
            ToolPolicy.assert_allowed("kubernetes", "get_storage")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            pvc_name = str((arguments or {}).get("pvc_name") or "").strip()
            if not pvc_name:
                raise ValueError("storage_diagnostics requires pvc_name")
            snapshot = provider.get_storage_diagnostics(namespace=namespace, pvc_name=pvc_name)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "pvc_name": pvc_name},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "networking_diagnostics":
            ToolPolicy.assert_allowed("kubernetes", "get_networking")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            snapshot = provider.get_networking_diagnostics(namespace=namespace)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace},
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "autoscaling_diagnostics":
            ToolPolicy.assert_allowed("kubernetes", "get_autoscaling")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            workload_name = str((arguments or {}).get("workload_name") or "").strip() or None
            snapshot = provider.get_autoscaling_diagnostics(
                namespace=namespace,
                workload_name=workload_name,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {
                    "operation": operation,
                    "namespace": namespace,
                    "workload_name": workload_name,
                },
                "scope_candidate": {},
                "kubernetes": {"scope": operation, **snapshot},
            }]

        if operation == "resource_events":
            ToolPolicy.assert_allowed("kubernetes", "get_events")
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            resource_name = str((arguments or {}).get("resource_name") or "").strip()
            if not resource_name:
                raise ValueError("resource_events requires resource_name")
            events = provider.get_events_for_resource(namespace=namespace, resource_name=resource_name)
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "resource_name": resource_name},
                "scope_candidate": {},
                "kubernetes": {
                    "scope": operation,
                    "namespace": namespace,
                    "resource_name": resource_name,
                    "events": events[-50:],
                },
            }]

        if operation == "service_diagnostics":
            namespace = self._validate_agentic_namespace(tool, (arguments or {}).get("namespace"))
            service_name = str((arguments or {}).get("service_name") or "").strip()
            if not service_name:
                raise ValueError("service_diagnostics requires service_name")
            snapshot = self.evidence_collector.collect_for_service(
                kubernetes=provider,
                namespace=namespace,
                service_name=service_name,
                tail_lines=tail_lines,
            )
            return [{
                "tool": descriptor,
                "agentic_arguments": {"operation": operation, "namespace": namespace, "service_name": service_name},
                "scope_candidate": {"service_name": service_name, "namespace": namespace},
                "kubernetes": snapshot,
            }]

        raise ValueError(f"Unsupported Kubernetes agentic operation: {operation}")

    def _run_agentic(self, db: Session, investigation, context: dict, llm):
        catalog, bindings = self._agentic_tool_catalog(context)
        if not catalog:
            raise ValueError("Application has no executable read-only tools")

        evidence: list[dict] = []
        executed_signatures: list[str] = []
        transcript_parts: list[str] = []
        decisions: list[dict] = []
        planner_context = self._llm_application_context(context)
        max_rounds = 6

        for round_number in range(1, max_rounds + 1):
            transcript_text = self._bounded_agentic_transcript(transcript_parts)
            decision = llm.plan_next_tools(
                application_context=planner_context,
                symptom=investigation.query,
                available_tools=catalog,
                investigation_transcript=transcript_text,
            )
            decisions.append({"round": round_number, **decision.model_dump(exclude_none=True)})

            if decision.stop:
                break

            executed_this_round = 0
            for choice in decision.choices:
                binding = bindings.get(choice.tool_key)
                if binding is None:
                    log_event(
                        logger,
                        logging.WARNING,
                        "rca.agentic.invalid_tool",
                        "LLM selected an unavailable tool key",
                        investigation_id=investigation.id,
                        tool_key=choice.tool_key,
                    )
                    continue

                arguments = choice.arguments_dict()
                signature = self._choice_signature(choice.tool_key, arguments)
                if signature in executed_signatures:
                    transcript_parts.append(
                        f"ROUND {round_number} TOOL REQUEST REJECTED\n"
                        f"tool_key: {choice.tool_key}\n"
                        f"arguments: {json.dumps(arguments, ensure_ascii=False, default=str)}\n"
                        "reason: identical tool call already exists in the transcript"
                    )
                    continue

                tool, dependency = binding
                try:
                    observations = self._execute_agentic_choice(
                        db,
                        tool=tool,
                        dependency=dependency,
                        arguments=arguments,
                        query=investigation.query,
                        context=context,
                    )
                except Exception as exc:
                    observations = [{
                        "tool": self._tool_descriptor(tool),
                        "dependency": dependency,
                        "agentic_arguments": arguments,
                        "error": str(exc),
                    }]
                evidence.extend(observations)
                transcript_parts.append(
                    self._tool_exchange_text(
                        round_number=round_number,
                        tool_key=choice.tool_key,
                        reason=choice.reason,
                        arguments=arguments,
                        observations=observations,
                    )
                )
                executed_signatures.append(signature)
                executed_this_round += 1

            if executed_this_round == 0 and not decision.choices:
                transcript_parts.append(
                    f"ROUND {round_number} PLANNER RESPONSE\n"
                    "No executable tool choice was requested. RCA Agent did not choose a tool on the LLM's behalf."
                )

        rca = self._analyze(investigation.query, evidence, context, llm)
        return evidence, decisions, rca

    @staticmethod
    def _persist_llm_usage(db: Session, investigation, llm) -> None:
        usage = dict(getattr(llm, "usage_totals", {}) or {})
        InvestigationRepository.update_llm_usage(
            db,
            investigation,
            provider_type=getattr(llm, "provider_type", None),
            model=getattr(llm, "model", None),
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
            token_usage_available=bool(usage.get("available", False)),
        )

    def run(self, investigation_id: int) -> None:
        set_request_id(f"investigation-{investigation_id}")
        started = time.perf_counter()
        self._kubernetes_providers = {}
        log_event(logger, logging.INFO, "rca.investigation.start", "Investigation started", investigation_id=investigation_id)

        with SessionLocal() as db:
            investigation = InvestigationRepository.get_by_id(db, investigation_id)
            if investigation is None:
                log_event(logger, logging.WARNING, "rca.investigation.not_found", "Investigation not found", investigation_id=investigation_id)
                return

            InvestigationRepository.mark_running(db, investigation)
            evidence: list[dict] = []
            resolved_scope_payload = None
            llm = None
            strategy = None

            try:
                if investigation.application_id is None:
                    raise ValueError("Investigation has no application_id")

                context = ApplicationContextService.load(db, investigation.application_id)
                if not context["tools"]:
                    raise ValueError("Application has no enabled investigation tools")

                strategy = context["application"]["investigation_strategy"]
                log_event(
                    logger,
                    logging.INFO,
                    "rca.context.loaded",
                    "Application context loaded",
                    investigation_id=investigation_id,
                    application_id=investigation.application_id,
                    strategy=strategy,
                    tools=len(context["tools"]),
                    dependencies=len(context["dependencies"]),
                )

                llm = self._llm_provider(db, context)
                if investigation.llm_history_enabled:
                    llm = RecordingLLMProvider(
                        llm,
                        db=db,
                        investigation_id=investigation.id,
                        provider_type=getattr(llm, "provider_type", None),
                        model=getattr(llm, "model", None),
                    )

                if strategy == "agentic":
                    evidence, decisions, rca = self._run_agentic(db, investigation, context, llm)
                    resolved_scope_payload = {
                        "application_id": investigation.application_id,
                        "strategy": strategy,
                        "llm_connection_id": context["application"].get("llm_connection_id"),
                        "agentic_decisions": decisions,
                    }
                else:
                    scope, candidates = self._resolve_kubernetes_scope(
                        db,
                        investigation.query,
                        context,
                        llm,
                    )
                    resolved_scope_payload = {
                        "application_id": investigation.application_id,
                        "strategy": strategy,
                        "llm_connection_id": context["application"].get("llm_connection_id"),
                        "resolved_scope": scope.model_dump() if scope is not None else None,
                    }
                    for tool in context["tools"]:
                        evidence.extend(self._collect_application_tool(
                            db=db,
                            tool=tool,
                            query=investigation.query,
                            context=context,
                            candidates=candidates,
                            collect_all=True,
                        ))
                    for dependency in context["dependencies"]:
                        for tool in dependency.get("tools", []):
                            evidence.extend(self._collect_dependency_tool(
                                db=db,
                                dependency=dependency,
                                tool=tool,
                                query=investigation.query,
                                context=context,
                                candidates=candidates,
                            ))
                    rca = self._analyze(investigation.query, evidence, context, llm)

                self._persist_llm_usage(db, investigation, llm)
                InvestigationRepository.mark_completed(
                    db=db,
                    investigation=investigation,
                    scope=resolved_scope_payload,
                    evidence=evidence,
                    rca_result=rca.model_dump(),
                )
                log_event(
                    logger,
                    logging.INFO,
                    "rca.investigation.complete",
                    "Investigation completed",
                    investigation_id=investigation_id,
                    application_id=investigation.application_id,
                    strategy=strategy,
                    evidence_items=len(evidence),
                    insufficient_evidence=rca.insufficient_evidence,
                    elapsed_ms=elapsed_ms(started),
                )
            except Exception as exc:
                if llm is not None:
                    try:
                        self._persist_llm_usage(db, investigation, llm)
                    except Exception:
                        logger.exception("Unable to persist LLM usage investigation_id=%s", investigation_id)
                log_event(
                    logger,
                    logging.ERROR,
                    "rca.investigation.failure",
                    "Investigation failed",
                    investigation_id=investigation_id,
                    application_id=investigation.application_id,
                    elapsed_ms=elapsed_ms(started),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                logger.exception("Investigation failed investigation_id=%s", investigation_id)
                InvestigationRepository.mark_failed(
                    db,
                    investigation,
                    str(exc),
                    scope=resolved_scope_payload,
                    evidence=evidence if evidence else None,
                )
