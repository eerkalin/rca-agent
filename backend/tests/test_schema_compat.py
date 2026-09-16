from app.db import schema_compat


def test_expected_head_revision_is_current_release_head():
    assert schema_compat.expected_head_revisions() == {"f4a5b6c7d8e9"}


def test_schema_status_reports_current(monkeypatch):
    monkeypatch.setattr(schema_compat, "current_database_revisions", lambda engine: {"f4a5b6c7d8e9"})
    monkeypatch.setattr(schema_compat, "expected_head_revisions", lambda: {"f4a5b6c7d8e9"})
    status = schema_compat.schema_status(object())
    assert status["up_to_date"] is True
    assert status["current_revisions"] == ["f4a5b6c7d8e9"]


def test_schema_status_reports_stale(monkeypatch):
    monkeypatch.setattr(schema_compat, "current_database_revisions", lambda engine: {"e3f4a5b6c7d8"})
    monkeypatch.setattr(schema_compat, "expected_head_revisions", lambda: {"f4a5b6c7d8e9"})
    status = schema_compat.schema_status(object())
    assert status["up_to_date"] is False
