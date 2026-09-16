from fastapi import APIRouter, HTTPException

from app.rca.evidence_collector import EvidenceCollector


router = APIRouter(
    prefix="/evidence",
    tags=["evidence"],
)


@router.get("/service/{namespace}/{service_name}")
async def collect_service_evidence(
    namespace: str,
    service_name: str,
    tail_lines: int = 50,
):
    try:
        collector = EvidenceCollector()

        return collector.collect_for_service(
            namespace=namespace,
            service_name=service_name,
            tail_lines=tail_lines,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )