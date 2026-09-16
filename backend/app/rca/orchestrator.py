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

    def investigate(
        self,
        text: str,
        namespace: str | None = None,
        trigger_type: str = "manual",
        alert_id: int | None = None,
    ) -> dict:

        scope = self.scope_resolver.resolve(
            text=text,
            namespace=namespace,
        )

        evidence = []

        for candidate in scope.candidates:

            service_evidence = (
                self.evidence_collector.collect_for_service(
                    namespace=candidate.namespace,
                    service_name=candidate.service_name,
                    tail_lines=50,
                )
            )

            evidence.append(
                {
                    "scope_candidate": {
                        "service_name":
                            candidate.service_name,

                        "namespace":
                            candidate.namespace,

                        "confidence":
                            candidate.confidence,

                        "reason":
                            candidate.reason,
                    },
                    "kubernetes":
                        service_evidence,
                }
            )

        rca = self.llm.analyze_rca(
            symptom=text,
            evidence=evidence,
        )

        scope_dict = scope.model_dump()
        rca_dict = rca.model_dump()

        with SessionLocal() as db:
            saved = InvestigationRepository.create(
                db=db,
                trigger_type=trigger_type,
                query=text,
                namespace=namespace,
                scope=scope_dict,
                evidence=evidence,
                rca_result=rca_dict,
                alert_id=alert_id,
            )

            investigation_id = saved.id
            created_at = saved.created_at

        return {
            "investigation_id": investigation_id,
            "created_at": created_at,
            "query": text,
            "scope": scope_dict,
            "evidence": evidence,
            "rca": rca_dict,
        }