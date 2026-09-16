from pathlib import Path

from app.api.provider_catalog import PROVIDERS


def test_provider_catalog_matches_runtime_keys():
    prometheus = next(item for item in PROVIDERS if item["provider_type"] == "prometheus")
    elasticsearch = next(item for item in PROVIDERS if item["provider_type"] == "elasticsearch")
    kubernetes = next(item for item in PROVIDERS if item["provider_type"] == "kubernetes")
    openai = next(item for item in PROVIDERS if item["provider_type"] == "openai")
    gemini = next(item for item in PROVIDERS if item["provider_type"] == "gemini")

    prom_connection_fields = {item["name"] for item in prometheus["connection_fields"]}
    prom_tool_fields = {item["name"] for item in prometheus["tool_fields"]}
    es_connection_fields = {item["name"] for item in elasticsearch["connection_fields"]}
    es_tool_fields = {item["name"] for item in elasticsearch["tool_fields"]}
    k8s_connection_fields = {item["name"] for item in kubernetes["connection_fields"]}
    k8s_credential_fields = {item["name"] for item in kubernetes["credential_fields"]}
    k8s_tool_fields = {item["name"] for item in kubernetes["tool_fields"]}

    assert {"base_url", "verify_ssl", "timeout_seconds"} <= prom_connection_fields
    assert {"queries", "lookback_minutes"} <= prom_tool_fields
    assert {"base_url", "verify_ssl", "timeout_seconds"} <= es_connection_fields
    assert {"index_pattern", "time_field", "size", "filters"} <= es_tool_fields
    assert {"mode", "context", "verify_ssl"} <= k8s_connection_fields
    assert {"kubeconfig"} <= k8s_credential_fields
    assert {"namespace", "tail_lines"} <= k8s_tool_fields
    assert set(next(x for x in kubernetes["connection_fields"] if x["name"] == "mode")["options"]) == {"in_cluster", "kubeconfig"}

    assert openai["category"] == "llm"
    assert gemini["category"] == "llm"
    assert {"default_model", "base_url"} <= {x["name"] for x in openai["connection_fields"]}
    assert {"api_key"} <= {x["name"] for x in openai["credential_fields"]}
    assert {"model", "temperature", "max_output_tokens"} <= {x["name"] for x in openai["application_fields"]}
    assert {"api_key"} <= {x["name"] for x in gemini["credential_fields"]}


def test_ui_assets_are_bundled():
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    assert (ui_dir / "index.html").is_file()
    assert (ui_dir / "app.js").is_file()
    assert (ui_dir / "enhancements.js").is_file()
    assert (ui_dir / "styles.css").is_file()
