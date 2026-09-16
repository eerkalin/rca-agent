from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str
    log_level: str = "INFO"

    # Optional legacy fallback for Applications created before per-Application
    # LLM connections existed. New Applications should select an encrypted DB-
    # backed LLM Connection in the UI.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    # Fernet key used only to encrypt/decrypt connection credentials stored in DB.
    # In Kubernetes this must come from a Kubernetes Secret, never values.yaml.
    rca_master_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
