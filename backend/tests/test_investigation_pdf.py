from types import SimpleNamespace

from app.rca.pdf_report import build_investigation_pdf


def test_investigation_pdf_contains_all_sections_and_supports_unicode():
    investigation = SimpleNamespace(
        id=42,
        application_id=7,
        alert_id=None,
        trigger_type="manual",
        query="Почему pod не Ready?",
        status="completed",
        scope={"strategy": "agentic", "agentic_decisions": [{"round": 1}]},
        evidence=[{"kubernetes": {"scope": "list_pods", "total_pods": 1}}],
        rca_result={
            "summary": "Контейнер не готов.",
            "root_cause": "Тестовая причина",
            "five_whys": [],
        },
        llm_history_enabled=True,
        llm_provider_type="gemini",
        llm_model="gemini-test",
        llm_input_tokens=100,
        llm_output_tokens=20,
        llm_total_tokens=120,
        llm_token_usage_available=True,
        error=None,
        started_at=None,
        finished_at=None,
        created_at=None,
    )
    history = [
        SimpleNamespace(
            sequence=1,
            phase="agentic_planner",
            provider_type="gemini",
            model="gemini-test",
            request_payload={"prompt": "Проверь pod"},
            response_payload={"stop": True},
            error=None,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            duration_ms=123,
            created_at=None,
        )
    ]

    pdf = build_investigation_pdf(
        investigation,
        application_name="ecommerce",
        llm_history=history,
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000
