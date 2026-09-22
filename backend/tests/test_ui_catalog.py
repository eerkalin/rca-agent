from pathlib import Path

from app.api.provider_catalog import PROVIDERS


def test_provider_catalog_matches_runtime_keys():
    prometheus = next(item for item in PROVIDERS if item["provider_type"] == "prometheus")
    elasticsearch = next(item for item in PROVIDERS if item["provider_type"] == "elasticsearch")
    elastic_apm = next(item for item in PROVIDERS if item["provider_type"] == "elastic_apm")
    kubernetes = next(item for item in PROVIDERS if item["provider_type"] == "kubernetes")

    prom_connection_fields = {item["name"] for item in prometheus["connection_fields"]}
    prom_tool_fields = {item["name"] for item in prometheus["tool_fields"]}
    es_connection_fields = {item["name"] for item in elasticsearch["connection_fields"]}
    es_tool_fields = {item["name"] for item in elasticsearch["tool_fields"]}
    apm_connection_fields = {item["name"] for item in elastic_apm["connection_fields"]}
    apm_tool_fields = {item["name"] for item in elastic_apm["tool_fields"]}
    k8s_connection_fields = {item["name"] for item in kubernetes["connection_fields"]}
    k8s_credential_fields = {item["name"] for item in kubernetes["credential_fields"]}
    k8s_tool_fields = {item["name"] for item in kubernetes["tool_fields"]}

    assert {"base_url", "verify_ssl", "timeout_seconds"} <= prom_connection_fields
    assert {"queries", "lookback_minutes"} <= prom_tool_fields
    assert {"base_url", "verify_ssl", "timeout_seconds"} <= es_connection_fields
    assert {"index_pattern", "time_field", "size", "filters"} <= es_tool_fields
    assert elastic_apm["implemented"] is True
    assert elastic_apm["tool_types"] == ["traces"]
    assert {"base_url", "verify_ssl", "timeout_seconds"} <= apm_connection_fields
    assert {"index_pattern", "lookback_minutes", "max_traces", "trace_id_field", "filters"} <= apm_tool_fields
    assert {"mode", "context", "verify_ssl"} <= k8s_connection_fields
    assert {"kubeconfig"} <= k8s_credential_fields
    assert {"namespaces", "tail_lines"} <= k8s_tool_fields
    namespaces_field = next(x for x in kubernetes["tool_fields"] if x["name"] == "namespaces")
    assert namespaces_field["type"] == "tags"
    assert set(next(x for x in kubernetes["connection_fields"] if x["name"] == "mode")["options"]) == {"in_cluster", "kubeconfig"}


def test_llm_catalog_supports_multiple_provider_types():
    llms = {item["provider_type"]: item for item in PROVIDERS if item.get("category") == "llm"}
    assert {"gemini", "openai", "anthropic", "openai_compatible"} <= set(llms)
    for item in llms.values():
        assert item["implemented"] is True
        assert item["tool_types"] == []
        assert any(field["name"] == "model" for field in item["connection_fields"])
        assert any(field["name"] == "model" for field in item["application_fields"])


def test_gemini_is_native_and_does_not_require_base_url():
    gemini = next(item for item in PROVIDERS if item["provider_type"] == "gemini")
    connection_fields = {item["name"] for item in gemini["connection_fields"]}
    credential_fields = {item["name"] for item in gemini["credential_fields"]}

    assert gemini["label"] == "Google Gemini"
    assert "model" in connection_fields
    assert "base_url" not in connection_fields
    assert "api_key" in credential_fields


def test_ui_assets_are_bundled():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    assert (ui_dir / "index.html").is_file()
    assert (ui_dir / "app.js").is_file()
    assert (ui_dir / "enhancements.js").is_file()
    assert (ui_dir / "application-detail.js").is_file()
    assert (ui_dir / "connection-detail.js").is_file()
    assert (ui_dir / "friendly-ui.js").is_file()
    assert (ui_dir / "binding-hardening.js").is_file()
    assert (ui_dir / "auth-ui.js").is_file()
    assert (ui_dir / "investigations-ui.js").is_file()
    assert (ui_dir / "styles.css").is_file()


def test_ui_auth_relogin_and_visual_shell_contract():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    auth_js = (ui_dir / "auth-ui.js").read_text()
    index_html = (ui_dir / "index.html").read_text()
    styles = (ui_dir / "styles.css").read_text()

    assert "cache: 'no-store'" in auth_js
    assert "establishAuthenticatedSession" in auth_js
    assert "resetWorkspaceAfterLogout" in auth_js
    assert "Signing in…" in auth_js
    assert 'class="brand-mark"' in index_html
    assert 'class="topnav"' in index_html
    assert "--surface:" in styles
    assert "backdrop-filter" in styles
    assert ".tile-grid" in styles


def test_top_navigation_resets_nested_detail_views():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    app_js = (ui_dir / "app.js").read_text()
    assert "function resetViewDetailState" in app_js
    assert "closeApplicationDetail" in app_js
    assert "closeConnectionDetail" in app_js
    assert "investigation-detail" in app_js


def test_premium_navigation_uses_svg_icons():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    index_html = (ui_dir / "index.html").read_text()
    styles = (ui_dir / "styles.css").read_text()
    assert 'class="nav-icon" aria-hidden="true"><svg' in index_html
    assert ".nav-icon svg" in styles
    assert "Premium shell v2" in styles


def test_ui_assets_are_cache_busted_and_icons_are_hard_sized():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    index_html = (ui_dir / "index.html").read_text()
    styles = (ui_dir / "styles.css").read_text()

    assert "/ui/styles.css?v=20260922-5" in index_html
    assert "/ui/app.js?v=20260922-5" in index_html
    assert 'width="24" height="24"' in index_html
    assert 'width="17" height="17"' in index_html
    assert "Premium workspace v3" in styles
    assert ".tool-row:hover" in styles
    assert ".rca-grid .card" in styles


def test_failed_investigation_has_same_id_retry_control():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    source = (ui_dir / "investigations-ui.js").read_text()
    assert "async function retryInvestigation(id)" in source
    assert "/investigations/${id}/retry" in source
    assert "Retry investigation" in source
    assert "canRunInvestigationActions()" in source
