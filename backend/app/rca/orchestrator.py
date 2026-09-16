from app.applications.context import ApplicationContextService
from app.db.session import SessionLocal
from app.integrations.gemini.provider import GeminiProvider
from app.rca.evidence_collector import EvidenceCollector
from app.rca.evidence_reducer import EvidenceReducer
from app.rca.repository import InvestigationRepository
from app.rca.scope_resolver import ScopeResolver


class RCAOrchestrator:
    def __init__(self):
        self.scope_resolver = ScopeResolver()
        self.evidence_collector = EvidenceCollector()
        self.llm = GeminiProvider()

    def _collect_candidate(self, candidate) -> dict:
        service_evidence = self.evidence_collector.collect_for_service(
            namespace=candidate.namespace,
            service_name=candidate.service_name,
            tail_lines=50,
        )
        return {
            "scope_candidate": {
                "service_name": candidate.service_name,
                "namespace": candidate.namespace,
                "confidence": candidate.confidence,
                "reason": candidate.reason,
            },
            "kubernetes": service_evidence,
        }

    def _analyze(self, query: str, evidence: list[dict], context: dict):
        compact_context = {
            "application": context["application"],
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
        return self.llm.analyze_rca(
            symptom=query,
            evidence=EvidenceReducer.reduce(evidence),
            application_context=compact_context,
        )

    def run(self, investigation_id: int) -> None:
        with SessionLocal() as db:
            investigation = InvestigationRepository.get_by_id(db, investigation_id)
            if investigation is None:
                return

            InvestigationRepository.mark_running(db, investigation)

            try:
                if investigation.application_id is None:
                    raise ValueError("Investigation has no application_id")

                context = ApplicationContextService.load(db, investigation.application_id)
                kubernetes_tool = ApplicationContextService.find_tool(
                    context,
                    tool_type="kubernetes",
                    provider_type="kubernetes",
                )
                if kubernetes_tool is None:
                    raise ValueError(
                        "Application has no supported investigation tool enabled. "
                        "Current MVP requires a Kubernetes tool binding."
                    )

                namespace = kubernetes_tool.get("config", {}).get("namespace")
                scope = self.scope_resolver.resolve(
                    text=investigation.query,
                    namespace=namespace,
                )
                if not scope.candidates:
                    raise ValueError("Scope resolver did not identify any technical candidate")

                strategy = context["application"]["investigation_strategy"]
                evidence: list[dict] = []

                if strategy == "collect_then_analyze":
                    evidence = [self._collect_candidate(candidate) for candidate in scope.candidates]
                    rca = self._analyze(investigation.query, evidence, context)
                else:
                    # Agentic mode minimizes tokens: inspect the strongest candidate first.
                    evidence.append(self._collect_candidate(scope.candidates[0]))
                    rca = self._analyze(investigation.query, evidence, context)

                    # Only expand to additional candidates when the first pass is insufficient.
                    if rca.insufficient_evidence and len(scope.candidates) > 1:
                        for candidate in scope.candidates[1:]:
                            evidence.append(self._collect_candidate(candidate))
                        rca = self._analyze(investigation.query, evidence, context)

                InvestigationRepository.mark_completed(
                    db=db,
                    investigation=investigation,
                    scope={
                        "application_id": investigation.application_id,
                        "strategy": strategy,
                        "resolved_scope": scope.model_dump(),
                    },
                    evidence=evidence,
                    rca_result=rca.model_dump(),
                )

            except Exception as exc:
                InvestigationRepository.mark_failed(db, investigation, str(exc))
