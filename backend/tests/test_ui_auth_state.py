from pathlib import Path


def test_auth_ui_rehydrates_session_after_login_and_resets_after_logout():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    source = (ui_dir / "auth-ui.js").read_text()

    assert "async function establishAuthenticatedSession()" in source
    assert "await authFetch('/auth/me')" in source
    assert "await refresh()" in source
    assert "function resetWorkspaceAfterLogout()" in source
    assert "setRoleDisabled(control, !admin)" in source
    assert "control.dataset.rbacDisabled === 'role'" in source


def test_core_api_fetch_is_session_aware_and_does_not_auto_refresh_before_auth():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    source = (ui_dir / "app.js").read_text()

    assert "credentials:'same-origin'" in source
    assert "refresh().catch(e=>toast(e.message));" not in source
