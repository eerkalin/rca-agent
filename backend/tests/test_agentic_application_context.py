from app.rca.agentic_prompt import build_agentic_planner_prompt
from app.rca.orchestrator import RCAOrchestrator


def _context():
    return {
        "application": {
            "id": 7,
            "name": "ecommerce",
            "slug": "ecommerce",
            "description": "Customer checkout application",
            "investigation_strategy": "agentic",
            "llm_connection_id": 99,
            "llm_config": {"model": "secret-model-config", "api_key": "must-not-leak"},
            "llm_history_enabled": True,
        },
        "tools": [
            {
                "id": 1,
                "tool_type": "kubernetes",
                "provider_type": "kubernetes",
                "connection_id": 10,
                "priority": 10,
                "config": {
                    "namespaces": ["otel-demo"],
                    "tail_lines": 75,
                    "token": "must-not-leak",
                },
            },
            {
                "id": 2,
                "tool_type": "metrics",
                "provider_type": "prometheus",
                "connection_id": 11,
                "priority": 20,
                "config": {
                    "queries": [
                        {"name": "error-rate", "promql": "sum(rate(secret_metric[5m]))"}
                    ],
                    "api_key": "must-not-leak",
                },
            },
        ],
        "dependencies": [
            {
                "id": 3,
                "name": "payments-db",
                "type": "postgresql",
                "description": "Stores payment and checkout state",
                "tools": [
                    {
                        "id": 4,
                        "tool_type": "metrics",
                        "provider_type": "prometheus",
                        "connection_id": 11,
                        "config": {
                            "queries": [
                                {"name": "db-saturation", "promql": "secret_db_query"}
                            ],
                            "password": "must-not-leak",
                        },
                    }
                ],
            }
        ],
    }


def test_llm_application_context_contains_semantics_and_dependency_bindings_without_secrets():
    safe = RCAOrchestrator._llm_application_context(_context())

    assert safe["application"] == {
        "id": 7,
        "name": "ecommerce",
        "slug": "ecommerce",
        "description": "Customer checkout application",
        "investigation_strategy": "agentic",
    }
    assert safe["enabled_diagnostic_bindings"][0]["configured_scope"]["namespaces"] == ["otel-demo"]
    assert safe["enabled_diagnostic_bindings"][1]["configured_scope"]["preconfigured_query_names"] == ["error-rate"]

    dependency = safe["dependencies"][0]
    assert dependency["name"] == "payments-db"
    assert dependency["type"] == "postgresql"
    assert dependency["description"] == "Stores payment and checkout state"
    assert dependency["diagnostic_bindings"][0]["configured_scope"]["preconfigured_query_names"] == ["db-saturation"]

    serialized = str(safe)
    assert "must-not-leak" not in serialized
    assert "secret_metric" not in serialized
    assert "secret_db_query" not in serialized
    assert "llm_connection_id" not in serialized
    assert "llm_config" not in serialized
    assert "connection_id" not in serialized


def test_agentic_prompt_includes_application_context_dependencies_and_autonomous_strategy():
    safe = RCAOrchestrator._llm_application_context(_context())
    prompt = build_agentic_planner_prompt(
        application_context=safe,
        symptom="Checkout latency increased",
        available_tools=[{
            "tool_key": "application:1",
            "tool_type": "kubernetes",
            "provider_type": "kubernetes",
            "operations": [{"name": "list_pods", "description": "Return every pod with raw Ready/container state fields."}],
            "read_only": True,
        }],
        investigation_transcript="ROUND 1 TOOL REQUEST\ntool_key: application:1\noperation: list_pods\n\nROUND 1 TOOL RESPONSE\n{\"pods\":[{\"name\":\"broken\",\"conditions\":[{\"type\":\"Ready\",\"status\":\"False\"}]}]}",
    )

    assert "autonomous Site Reliability / Application Support investigation agent" in prompt
    assert "YOU CONTROL THE INVESTIGATION STRATEGY" in prompt
    assert "Customer checkout application" in prompt
    assert "payments-db" in prompt
    assert "Stores payment and checkout state" in prompt
    assert "Checkout latency increased" in prompt
    assert "list_pods" in prompt
    assert "INVESTIGATION TRANSCRIPT" in prompt
    assert "ROUND 1 TOOL REQUEST" in prompt
    assert "\"status\":\"False\"" in prompt
    assert "Return exactly one JSON object and nothing else" in prompt
    assert "guidance, not a hard-coded workflow" in prompt
    assert "RCA Agent does not decide whether an object is healthy" in prompt
    assert "sole investigation strategist" in prompt
    assert "must-not-leak" not in prompt
