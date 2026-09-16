from sqlalchemy.orm import Session

from app.applications.context import ApplicationContextService
from app.applications.runtime import RuntimeConnectionResolver
from app.db.session import SessionLocal
from app.integrations.elasticsearch.provider import ElasticsearchLogsProvider
from app.integrations.kubernetes.factory import KubernetesProviderFactory
from app.integrations.llm.factory import LLMProviderFactory, SUPPORTED_LLM_PROVIDER_TYPES
from app.integrations.prometheus.provider import PrometheusProvider
from app.rca.evidence_collector import EvidenceCollector
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.repository import InvestigationRepository
from app.rca.scope_resolver import ScopeResolver


class RCAOrchestrator:
    def __init__(self):
        self.scope_resolver = ScopeResolver()
        self.evidence_collector = EvidenceCollector()
        self._kubernetes_providers: dict[int, object] = {}

    @staticmethod
    def _tool_descriptor(tool: dict) -> dict:
        return {
            "id": tool.get("id"),
            "tool_type": tool.get("tool_type"),
            "provider_type": tool.get("provider_type"),
            "connection_id": tool.get("connection_id"),
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
    def _llm_provider(db: Session, context: dict):
        application = context["application"]
        connection_id = application.get("llm_connection_id")
        model_config = application.get("llm_config") or {}

        if connection_id is None:
            return LLMProviderFactory.create(None, model_config=model_config)

        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
        if runtime.get("provider_type") not in SUPPORTED_LLM_PROVIDER_TYPES:
            raise ValueError(
                f"Application LLM connection {connection_id} uses unsupported provider "
                f"{runtime.get('provider_type')}"
            )
        return LLMProviderFactory.create(runtime, model_config=model_config)

    @staticmethod
    def _analyze(llm, query: str, evidence: list[dict], context: dict):
        compact_context = {
            "application": {
                "id": context["application"]["id"],
                "name": context["application"]["name"],
                "slug": context["application"]["slug"],
                "description": context["application"].get("description"),
                "investigation_strategy": context["application"]["investigation_strategy"],
            },
            "enabled_tools": [
                {
                    "tool_type": item["tool_type"],
                    "provider_type": item["provider_type"],
                    "config": item["config"],
                }
                for item in context["tools"]
            ],
            "dependencies": context["dependencies"],
        }
        return llm.analyze_rca(
            symptom=query,
            evidence=EvidenceReducer.reduce(evidence),
            application_context=compact_context,
        )

    def _kubernetes_provider(self, db: Session, tool: dict):
        connection_id = tool.get("connection_id")
        if connection_id is None:
            raise ValueError(
                "Kubernetes application tool requires connection_id. Configure a Kubernetes Connection in the UI."
            )
        if connection_id in self._kubernetes_providers:
            return self._kubernetes_providers[connection_id]

        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
        if runtime.get("provider_type") != "kubernetes":
            raise ValueError(
                f"Connection {connection_id} is not a Kubernetes connection"
            )
        provider = KubernetesProviderFactory.create(runtime)
        self._kubernetes_providers[connection_id] = provider
        return provider

    def _resolve_kubernetes_scope(self, db: Session, query: str, context: dict, llm):
        kubernetes_tool = ApplicationContextService.find_tool(
            context,
            tool_type="kubernetes",
            provider_type="kubernetes",
        )
        if kubernetes_tool is None:
            return None, []

        provider = self._kubernetes_provider(db, kubernetes_tool)
        namespace = kubernetes_tool.get("config", {}).get("namespace")
        scope = self.scope_resolver.resolve(
            text=query,
            kubernetes=provider,
            llm=llm,
            namespace=namespace,
        )
        return scope, list(scope.candidates)

    def _collect_kubernetes(
        self,
        db: Session,
        tool: dict,
        candidates: list,
        collect_all: bool,
    ) -> list[dict]:
        if not candidates:
            return [
                {
                    "tool": self._tool_descriptor(tool),
                    "error": "Kubernetes scope resolver did not identify a technical candidate",
                }
            ]

        provider = self._kubernetes_provider(db, tool)
        selected = candidates if collect_all else candidates[:1]
        evidence = []
        for candidate in selected:
            service_evidence = self.evidence_collector.collect_for_service(
                kubernetes=provider,
                namespace=candidate.namespace,
                service_name=candidate.service_name,
                tail_lines=int(tool.get("config", {}).get("tail_lines", 50)),
            )
            evidence.append(
                {
                    "tool": self._tool_descriptor(tool),
                    "scope_candidate": {
                        "service_name": candidate.service_name,
                        "namespace": candidate.namespace,
                        "confidence": candidate.confidence,
                        "reason": candidate.reason,
                    },
                    "kubernetes": service_evidence,
                }
            )
        return evidence

    def _collect_non_kubernetes_tool(
        self,
        db: Session,
        tool: dict,
        query: str,
        context: dict,
        candidate=None,
        dependency: dict | None = None,
    ) -> list[dict]:
        descriptor = self._tool_descriptor(tool)
        connection = RuntimeConnectionResolver.resolve(db, tool.get("connection_id"))
        variables = self._variables(context, candidate=candidate, dependency=dependency)

        base = {
            "tool": descriptor,
            "dependency": (
                {
                    "id": dependency.get("id"),
                    "name": dependency.get("name"),
                    "type": dependency.get("type"),
                }
                if dependency
                else None
            ),
            "scope_candidate": (
                {
                    "service_name": candidate.service_name,
                    "namespace": candidate.namespace,
                    "confidence": candidate.confidence,
                    "reason": candidate.reason,
                }
                if candidate
                else {}
            ),
        }

        try:
            tool_type = tool.get("tool_type")
            provider_type = tool.get("provider_type")

            if tool_type == "metrics" and provider_type == "prometheus":
                provider = PrometheusProvider(
                    config=connection.get("config", {}),
                    credentials=connection.get("credentials", {}),
                )
                metrics = self.evidence_collector.collect_prometheus(
                    provider=provider,
                    tool_config=tool.get("config", {}),
                    variables=variables,
                )
                return [{**base, "metrics": metrics}]

            if tool_type == "logs" and provider_type in {"elasticsearch", "elastic"}:
                provider = ElasticsearchLogsProvider(
                    config=connection.get("config", {}),
                    credentials=connection.get("credentials", {}),
                )
                logs = self.evidence_collector.collect_elasticsearch_logs(
                    provider=provider,
                    tool_config=tool.get("config", {}),
                    symptom=query,
                    variables=variables,
                )
                return [{**base, "logs": logs}]

            return [
                {
                    **base,
                    "error": (
                        f"Provider {provider_type} for tool {tool_type} is configured "
                        "but not implemented in this RCA Agent version"
                    ),
                }
            ]
        except Exception as exc:
            return [{**base, "error": str(exc)}]

    def _collect_application_tool(
        self,
        db: Session,
        tool: dict,
        query: str,
        context: dict,
        candidates: list,
        collect_all: bool,
    ) -> list[dict]:
        if tool.get("tool_type") == "kubernetes" and tool.get("provider_type") == "kubernetes":
            return self._collect_kubernetes(
                db=db,
                tool=tool,
                candidates=candidates,
                collect_all=collect_all,
            )

        candidate = candidates[0] if candidates else None
        return self._collect_non_kubernetes_tool(
            db=db,
            tool=tool,
            query=query,
            context=context,
            candidate=candidate,
        )

    def _collect_dependency_tool(
        self,
        db: Session,
        dependency: dict,
        tool: dict,
        query: str,
        context: dict,
        candidates: list,
    ) -> list[dict]:
        candidate = candidates[0] if candidates else None
        return self._collect_non_kubernetes_tool(
            db=db,
            tool=tool,
            query=query,
            context=context,
            candidate=candidate,
            dependency=dependency,
        )

    def run(self, investigation_id: int) -> None:
        self._kubernetes_providers = {}
        with SessionLocal() as db:
            investigation = InvestigationRepository.get_by_id(db, investigation_id)
            if investigation is None:
                return

            InvestigationRepository.mark_running(db, investigation)

            try:
                if investigation.application_id is None:
                    raise ValueError("Investigation has no application_id")

                context = ApplicationContextService.load(db, investigation.application_id)
                if not context["tools"]:
                    raise ValueError("Application has no enabled investigation tools")

                llm = self._llm_provider(db, context)
                scope, candidates = self._resolve_kubernetes_scope(
                    db,
                    investigation.query,
                    context,
                    llm,
                )
                strategy = context["application"]["investigation_strategy"]
                evidence: list[dict] = []
                rca = None

                if strategy == "collect_then_analyze":
                    for tool in context["tools"]:
                        evidence.extend(
                            self._collect_application_tool(
                                db=db,
                                tool=tool,
                                query=investigation.query,
                                context=context,
                                candidates=candidates,
                                collect_all=True,
                            )
                        )

                    for dependency in context["dependencies"]:
                        for tool in dependency.get("tools", []):
                            evidence.extend(
                                self._collect_dependency_tool(
                                    db=db,
                                    dependency=dependency,
                                    tool=tool,
                                    query=investigation.query,
                                    context=context,
                                    candidates=candidates,
                                )
                            )

                    rca = self._analyze(llm, investigation.query, evidence, context)
                else:
                    for tool in context["tools"]:
                        evidence.extend(
                            self._collect_application_tool(
                                db=db,
                                tool=tool,
                                query=investigation.query,
                                context=context,
                                candidates=candidates,
                                collect_all=False,
                            )
                        )
                        rca = self._analyze(llm, investigation.query, evidence, context)
                        if not rca.insufficient_evidence:
                            break

                    if rca is None or rca.insufficient_evidence:
                        for dependency in context["dependencies"]:
                            for tool in dependency.get("tools", []):
                                evidence.extend(
                                    self._collect_dependency_tool(
                                        db=db,
                                        dependency=dependency,
                                        tool=tool,
                                        query=investigation.query,
                                        context=context,
                                        candidates=candidates,
                                    )
                                )
                                rca = self._analyze(llm, investigation.query, evidence, context)
                                if not rca.insufficient_evidence:
                                    break
                            if rca is not None and not rca.insufficient_evidence:
                                break

                if rca is None:
                    raise ValueError("No supported evidence tools could be executed")

                InvestigationRepository.mark_completed(
                    db=db,
                    investigation=investigation,
                    scope={
                        "application_id": investigation.application_id,
                        "strategy": strategy,
                        "llm_provider": getattr(llm, "provider_type", type(llm).__name__),
                        "llm_model": getattr(llm, "model", None),
                        "resolved_scope": scope.model_dump() if scope is not None else None,
                    },
                    evidence=evidence,
                    rca_result=rca.model_dump(),
                )

            except Exception as exc:
                InvestigationRepository.mark_failed(db, investigation, str(exc))
