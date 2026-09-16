from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import applications


def connection(provider_type: str):
    return SimpleNamespace(provider_type=provider_type)


def test_application_tool_requires_connection(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        applications._validate_tool_binding(
            object(),
            tool_type="metrics",
            provider_type="prometheus",
            connection_id=None,
        )
    assert exc.value.status_code == 400
    assert "connection_id" in str(exc.value.detail)


def test_application_tool_rejects_provider_mismatch(monkeypatch):
    monkeypatch.setattr(
        applications.ConnectionRepository,
        "get",
        lambda db, connection_id: connection("elasticsearch"),
    )

    with pytest.raises(HTTPException) as exc:
        applications._validate_tool_binding(
            object(),
            tool_type="metrics",
            provider_type="prometheus",
            connection_id=12,
        )

    assert exc.value.status_code == 400
    assert "provider mismatch" in str(exc.value.detail).lower()


def test_application_tool_accepts_matching_provider(monkeypatch):
    monkeypatch.setattr(
        applications.ConnectionRepository,
        "get",
        lambda db, connection_id: connection("elastic_apm"),
    )

    applications._validate_tool_binding(
        object(),
        tool_type="traces",
        provider_type="elastic_apm",
        connection_id=7,
    )


def test_dependency_tools_are_prometheus_metrics_only(monkeypatch):
    monkeypatch.setattr(
        applications.ConnectionRepository,
        "get",
        lambda db, connection_id: connection("elasticsearch"),
    )

    with pytest.raises(HTTPException) as exc:
        applications._validate_tool_binding(
            object(),
            tool_type="logs",
            provider_type="elasticsearch",
            connection_id=4,
            dependency=True,
        )

    assert exc.value.status_code == 400
    assert "unsupported dependency" in str(exc.value.detail).lower()


def test_connection_provider_catalog_is_restricted():
    applications._validate_connection_provider("gemini")
    applications._validate_connection_provider("kubernetes")

    with pytest.raises(HTTPException) as exc:
        applications._validate_connection_provider("planned-provider")

    assert exc.value.status_code == 400
