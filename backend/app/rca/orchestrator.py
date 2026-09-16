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
from app.integrations.prometheus.provider import PrometheusProvider
from app.observability.logging import elapsed_ms, log_event, set_request_id
from app.rca.evidence_collector import EvidenceCollector
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.repository import InvestigationRepository
from app.rca.scope_resolver import ScopeResolver


logger = logging.getLogger(__name__)


class RCAOrchestrator:
    def __init__(self):
        self.scope_resolver = ScopeResolver()
        self.evidence_collector = EvidenceCollector()
        self._kubernetes_providers: dict[int, object] = {}

    @staticmethod
    def _tool_descriptor(tool: dict) -> dict:
        return {"id": tool.get("id"), "tool_type": tool.get("tool_type"), "provider_type": tool.get("provider_type"), "connection_id": tool.get("connection_id")}

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
        return GeminiProvider(config={"model": settings.gemini_model}, credentials={"api_key": settings.gemini_api_key})

    def _llm_provider(self, db: Session, context: dict):
        application = context["application"]
        connection_id = application.get("llm_connection_id")
        if connection_id is None:
            return self._legacy_llm()
        runtime = RuntimeConnectionResolver.resolve(db, connection_id)
        log_event(logger, logging.INFO, "rca.llm.selected", "Resolved Application LLM provider", application_id=application.get("id"), connection_id=connection_id, provider_type=runtime.get("provider_type"), model=(application.get("llm_config") or {}).get("model") or (runtime.get("config") or {}).get("model"))
        return LLMProviderFactory.create(runtime, application.get("llm_config") or {})

    @staticmethod
    def _analyze(query: str, evidence: list[dict], context: dict, llm):
        reduced = EvidenceReducer.reduce(evidence)
        compact_context = {
            "application": {key: value for key, value in context["application"].items() if key not in {"llm_connection_id", "llm_config"}},
            "enabled_tools": [{"tool_type": item["tool_type"], "provider_type": item["provider_type"], "config": item["config"]} for item in context["tools"]],
            "dependencies": context["dependencies"],
        }
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
        namespace = kubernetes_tool.get("config", {}).get("namespace")
        started = time.perf_counter()
        log_event(logger, logging.INFO, "rca.scope.start", "Resolving Kubernetes investigation scope", namespace=namespace)
        scope = self.scope_resolver.resolve(text=query, kubernetes=provider, llm=llm, namespace=namespace)
        candidates = list(scope.candidates)
        log_event(logger, logging.INFO, "rca.scope.complete", "Kubernetes scope resolved", namespace=namespace, elapsed_ms=elapsed_ms(started), candidates=[{"service_name": item.service_name, "namespace": item.namespace, "confidence": item.confidence} for item in candidates], unresolved=scope.unresolved)
        return scope, candidates

    def _collect_kubernetes(self, db: Session, tool: dict, candidates: list, collect_all: bool) -> list[dict]:
        if not candidates:
            log_event(logger, logging.WARNING, "rca.kubernetes.no_candidates", "Kubernetes collection skipped because no scope candidate was resolved", tool_id=tool.get("id"))
            return [{"tool": self._tool_descriptor(tool), "error": "Kubernetes scope resolver did not identify a technical candidate"}]
        provider = self._kubernetes_provider(db, tool)
        selected = candidates if collect_all else candidates[:1]
        evidence = []
        for candidate in selected:
            started = time.perf_counter()
            log_event(logger, logging.INFO, "rca.kubernetes.collect.start", "Collecting Kubernetes evidence", tool_id=tool.get("id"), service_name=candidate.service_name, namespace=candidate.namespace)
            service_evidence = self.evidence_collector.collect_for_service(
                kubernetes=provider,
                namespace=candidate.namespace,
                service_name=candidate.service_name,
                tail_lines=int(tool.get("config", {}).get("tail_lines", 50)),
            )
            log_event(logger, logging.INFO, "rca.kubernetes.collect.complete", "Kubernetes evidence collected", tool_id=tool.get("id"), service_name=candidate.service_name, namespace=candidate.namespace, elapsed_ms=elapsed_ms(started))
            evidence.append({
                "tool": self._tool_descriptor(tool),
                "scope_candidate": {"service_name": candidate.service_name, "namespace": candidate.namespace, "confidence": candidate.confidence, "reason": candidate.reason},
                "kubernetes": service_evidence,
            })
        return evidence

    def _collect_non_kubernetes_tool(self, db: Session, tool: dict, query: str, context: dict, candidate=None, dependency: dict | None = None) -> list[dict]:
        descriptor = self._tool_descriptor(tool)
        connection = RuntimeConnectionResolver.resolve(db, tool.get("connection_id"))
        variables = self._variables(context, candidate=candidate, dependency=dependency)
        base = {
            "tool": descriptor,
            "dependency": ({"id": dependency.get("id"), "name": dependency.get("name"), "type": dependency.get("type")} if dependency else None),
            "scope_candidate": ({"service_name": candidate.service_name, "namespace": candidate.namespace, "confidence": candidate.confidence, "reason": candidate.reason} if candidate else {}),
        }
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
            try:
                if investigation.application_id is None:
                    raise ValueError("Investigation has no application_id")
                context = ApplicationContextService.load(db, investigation.application_id)
                if not context["tools"]:
                    raise ValueError("Application has no enabled investigation tools")
                strategy = context["application"]["investigation_strategy"]
                log_event(logger, logging.INFO, "rca.context.loaded", "Application context loaded", investigation_id=investigation_id, application_id=investigation.application_id, strategy=strategy, tools=len(context["tools"]), dependencies=len(context["dependencies"]))
                llm = self._llm_provider(db, context)
                scope, candidates = self._resolve_kubernetes_scope(db, investigation.query, context, llm)
                evidence: list[dict] = []
                rca = None

                if strategy == "collect_then_analyze":
                    for tool in context["tools"]:
                        evidence.extend(self._collect_application_tool(db=db, tool=tool, query=investigation.query, context=context, candidates=candidates, collect_all=True))
                    for dependency in context["dependencies"]:
                        for tool in dependency.get("tools", []):
                            evidence.extend(self._collect_dependency_tool(db=db, dependency=dependency, tool=tool, query=investigation.query, context=context, candidates=candidates))
                    rca = self._analyze(investigation.query, evidence, context, llm)
                else:
                    for tool in context["tools"]:
                        evidence.extend(self._collect_application_tool(db=db, tool=tool, query=investigation.query, context=context, candidates=candidates, collect_all=False))
                        rca = self._analyze(investigation.query, evidence, context, llm)
                        if not rca.insufficient_evidence:
                            log_event(logger, logging.INFO, "rca.agentic.stop", "Agentic investigation stopped after sufficient evidence", tool_id=tool.get("id"), evidence_items=len(evidence))
                            break
                    if rca is None or rca.insufficient_evidence:
                        for dependency in context["dependencies"]:
                            for tool in dependency.get("tools", []):
                                evidence.extend(self._collect_dependency_tool(db=db, dependency=dependency, tool=tool, query=investigation.query, context=context, candidates=candidates))
                                rca = self._analyze(investigation.query, evidence, context, llm)
                                if not rca.insufficient_evidence:
                                    break
                            if rca is not None and not rca.insufficient_evidence:
                                break

                if rca is None:
                    raise ValueError("No supported evidence tools could be executed")
                InvestigationRepository.mark_completed(
                    db=db,
                    investigation=investigation,
                    scope={"application_id": investigation.application_id, "strategy": strategy, "llm_connection_id": context["application"].get("llm_connection_id"), "resolved_scope": scope.model_dump() if scope is not None else None},
                    evidence=evidence,
                    rca_result=rca.model_dump(),
                )
                log_event(logger, logging.INFO, "rca.investigation.complete", "Investigation completed", investigation_id=investigation_id, application_id=investigation.application_id, strategy=strategy, evidence_items=len(evidence), insufficient_evidence=rca.insufficient_evidence, elapsed_ms=elapsed_ms(started))
            except Exception as exc:
                log_event(logger, logging.ERROR, "rca.investigation.failure", "Investigation failed", investigation_id=investigation_id, application_id=investigation.application_id, elapsed_ms=elapsed_ms(started), error_type=type(exc).__name__, error=str(exc))
                logger.exception("Investigation failed investigation_id=%s", investigation_id)
                InvestigationRepository.mark_failed(db, investigation, str(exc))
