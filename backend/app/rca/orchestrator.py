from app.applications.context import ApplicationContextService
from app.db.session import SessionLocal
from app.integrations.gemini.provider import GeminiProvider
from app.rca.evidence_collector import EvidenceCollector
from app.rca.repository import InvestigationRepository
from app.rca.scope_resolver import ScopeResolver


class RCAOrchestrator:
    def __init__(self):
        self.scope_resolver = ScopeResolver()
        self.evidence_collector = EvidenceCollector()
        self.llm = GeminiProvider()

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

                evidence = []
                for candidate in scope.candidates:
                    service_evidence = self.evidence_collector.collect_for_service(
                        namespace=candidate.namespace,
                        service_name=candidate.service_name,
                        tail_lines=50,
                    )
                    evidence.append(
                        {
                            "scope_candidate": {
                                "service_name": candidate.service_name,
                                "namespace": candidate.namespace,
                                "confidence": candidate.confidence,
                                "reason": candidate.reason,
                            },
                            "kubernetes": service_evidence,
                        }
                    )

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

                rca = self.llm.analyze_rca(
                    symptom=investigation.query,
                    evidence=evidence,
                    application_context=compact_context,
                )

                InvestigationRepository.mark_completed(
                    db=db,
                    investigation=investigation,
                    scope={
                        "application_id": investigation.application_id,
                        "strategy": context["application"]["investigation_strategy"],
                        "resolved_scope": scope.model_dump(),
                    },
                    evidence=evidence,
                    rca_result=rca.model_dump(),
                )

            except Exception as exc:
                InvestigationRepository.mark_failed(db, investigation, str(exc))
