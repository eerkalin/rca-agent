from app.db.models.investigation import Investigation
from app.rca.repository import InvestigationRepository


class FakeDB:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.refreshed = []

    def execute(self, statement):
        self.executed.append(statement)

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        self.refreshed.append(item)


def test_retry_reset_keeps_identity_but_clears_runtime_state_and_usage():
    investigation = Investigation(
        id=42,
        application_id=7,
        trigger_type="manual",
        query="payment pod is not ready",
        status="failed",
        llm_history_enabled=True,
    )
    investigation.scope = {"old": True}
    investigation.evidence = [{"old": True}]
    investigation.rca_result = {"summary": "old"}
    investigation.error = "503"
    investigation.llm_provider_type = "openai_compatible"
    investigation.llm_model = "gemini-3.6-flash"
    investigation.llm_input_tokens = 100
    investigation.llm_output_tokens = 50
    investigation.llm_total_tokens = 150
    investigation.llm_token_usage_available = True

    db = FakeDB()
    InvestigationRepository.reset_for_retry(db, investigation)

    assert investigation.id == 42
    assert investigation.application_id == 7
    assert investigation.query == "payment pod is not ready"
    assert investigation.llm_history_enabled is True
    assert investigation.status == "queued"
    assert investigation.scope is None
    assert investigation.evidence is None
    assert investigation.rca_result is None
    assert investigation.error is None
    assert investigation.started_at is None
    assert investigation.finished_at is None
    assert investigation.llm_provider_type is None
    assert investigation.llm_model is None
    assert investigation.llm_total_tokens == 0
    assert investigation.llm_token_usage_available is False
    assert len(db.executed) == 1
    assert db.commits == 1
    assert db.refreshed == [investigation]
