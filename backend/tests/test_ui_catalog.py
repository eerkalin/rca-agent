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
    assert (ui_dir / "auth-ui.js").is_file()
    assert (ui_dir / "investigations-ui.js").is_file()
    assert (ui_dir / "styles.css").is_file()
