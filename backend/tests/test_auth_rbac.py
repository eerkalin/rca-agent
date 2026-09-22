from types import SimpleNamespace

from app.auth.middleware import _authorized
from app.auth.service import ROLE_ADMIN, ROLE_INVESTIGATOR, ROLE_READONLY


def request(method: str, path: str):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


def test_admin_can_mutate_configuration():
    assert _authorized(ROLE_ADMIN, request("DELETE", "/api/v1/applications/1")) is True


def test_readonly_can_read_all_operator_views_but_not_mutate_or_execute():
    for path in (
        "/api/v1/applications",
        "/api/v1/applications/1",
        "/api/v1/connections",
        "/api/v1/investigations",
        "/api/v1/investigations/12",
        "/api/v1/dependencies/4/tools",
    ):
        assert _authorized(ROLE_READONLY, request("GET", path)) is True

    assert _authorized(ROLE_READONLY, request("POST", "/api/v1/investigations/manual")) is False
    assert _authorized(ROLE_READONLY, request("POST", "/api/v1/connections/3/test")) is False
    assert _authorized(ROLE_READONLY, request("PATCH", "/api/v1/applications/1")) is False
    assert _authorized(ROLE_READONLY, request("DELETE", "/api/v1/connections/3")) is False


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
