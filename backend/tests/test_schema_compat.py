from app.db import schema_compat


def test_expected_head_revision_is_current_release_head():
    assert schema_compat.expected_head_revisions() == {"d2e3f4a5b6c7"}


def test_schema_status_reports_current(monkeypatch):
    monkeypatch.setattr(schema_compat, "current_database_revisions", lambda engine: {"d2e3f4a5b6c7"})
    monkeypatch.setattr(schema_compat, "expected_head_revisions", lambda: {"d2e3f4a5b6c7"})
    status = schema_compat.schema_status(object())
    assert status["up_to_date"] is True
    assert status["current_revisions"] == ["d2e3f4a5b6c7"]


def test_schema_status_reports_stale(monkeypatch):
    monkeypatch.setattr(schema_compat, "current_database_revisions", lambda engine: {"c1a2b3c4d5e6"})
    monkeypatch.setattr(schema_compat, "expected_head_revisions", lambda: {"d2e3f4a5b6c7"})
    status = schema_compat.schema_status(object())
    assert status["up_to_date"] is False
