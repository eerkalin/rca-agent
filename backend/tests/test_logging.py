from app.observability.logging import redact, sanitize_url


def test_redact_masks_nested_secrets():
    payload = {
        "api_key": "abc123",
        "nested": {
            "password": "secret-password",
            "token": "secret-token",
            "safe": "visible",
        },
    }

    redacted = redact(payload)

    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["password"] == "***REDACTED***"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["nested"]["safe"] == "visible"


def test_redact_removes_credentials_from_database_url():
    value = "mysql+pymysql://rca_agent:very-secret@mysql:3306/rca_agent?charset=utf8mb4"

    redacted = redact(value)

    assert "very-secret" not in redacted
    assert "rca_agent@" not in redacted
    assert redacted == "mysql+pymysql://mysql:3306/rca_agent"


def test_sanitize_url_removes_query_and_credentials():
    value = "https://user:password@example.test:9443/api/search?token=secret"

    sanitized = sanitize_url(value)

    assert sanitized == "https://example.test:9443/api/search"
    assert "password" not in sanitized
    assert "secret" not in sanitized
