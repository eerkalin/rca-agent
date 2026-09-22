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


def test_readonly_ui_hides_actions_not_workspace_data():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    auth_source = (ui_dir / "auth-ui.js").read_text()
    core_source = (ui_dir / "app.js").read_text()

    # Every authenticated role is rehydrated through the same read path.
    assert "await refresh()" in auth_source
    assert "api('/connections')" in core_source
    assert "api('/applications')" in core_source

    # Read-only loses execution/mutation controls, not the cards themselves.
    assert "qs('#new-application')?.classList.toggle('hidden', !admin)" in auth_source
    assert "qs('#new-connection')?.classList.toggle('hidden', !admin)" in auth_source
    assert "qs('#new-investigation')?.classList.toggle('hidden', !(admin || investigator))" in auth_source
    assert "applications-list" not in auth_source
    assert "connections-list" not in auth_source
