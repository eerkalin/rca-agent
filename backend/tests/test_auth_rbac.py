from types import SimpleNamespace

from app.auth.middleware import _authorized
from app.auth.service import ROLE_ADMIN, ROLE_INVESTIGATOR, ROLE_READONLY


def request(method: str, path: str):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


def test_admin_can_mutate_configuration():
    assert _authorized(ROLE_ADMIN, request("DELETE", "/api/v1/applications/1")) is True


def test_readonly_can_read_entire_workspace_but_not_mutate_or_execute():
    readable_paths = [
        "/api/v1/provider-catalog",
        "/api/v1/applications",
        "/api/v1/applications/1",
        "/api/v1/connections",
        "/api/v1/dependencies/1/tools",
        "/api/v1/investigations",
        "/api/v1/investigations/42",
    ]
    for path in readable_paths:
        assert _authorized(ROLE_READONLY, request("GET", path)) is True

    forbidden_actions = [
        ("POST", "/api/v1/applications"),
        ("PATCH", "/api/v1/applications/1"),
        ("DELETE", "/api/v1/applications/1"),
        ("POST", "/api/v1/connections/3/test"),
        ("POST", "/api/v1/investigations/manual"),
        ("DELETE", "/api/v1/investigations/42"),
    ]
    for method, path in forbidden_actions:
        assert _authorized(ROLE_READONLY, request(method, path)) is False


def test_investigator_can_run_diagnostics_but_not_change_configuration():
    assert _authorized(ROLE_INVESTIGATOR, request("GET", "/api/v1/applications")) is True
    assert _authorized(ROLE_INVESTIGATOR, request("POST", "/api/v1/investigations")) is True
    assert _authorized(ROLE_INVESTIGATOR, request("POST", "/api/v1/connections/3/test")) is True
    assert _authorized(ROLE_INVESTIGATOR, request("POST", "/api/v1/applications")) is False
    assert _authorized(ROLE_INVESTIGATOR, request("DELETE", "/api/v1/connections/3")) is False


def test_user_management_is_admin_only_even_for_reads():
    assert _authorized(ROLE_ADMIN, request("GET", "/api/v1/auth/users")) is True
    assert _authorized(ROLE_INVESTIGATOR, request("GET", "/api/v1/auth/users")) is False
    assert _authorized(ROLE_READONLY, request("GET", "/api/v1/auth/users")) is False


def test_non_admin_users_can_logout():
    assert _authorized(ROLE_INVESTIGATOR, request("POST", "/api/v1/auth/logout")) is True
    assert _authorized(ROLE_READONLY, request("POST", "/api/v1/auth/logout")) is True
