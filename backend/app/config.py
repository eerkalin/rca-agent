from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str

    # Transitional global LLM configuration. It will move to encrypted Connection
    # records once multi-LLM support is introduced.
    gemini_api_key: str
    gemini_model: str = "gemini-3.6-flash"

    # Fernet key used only to encrypt/decrypt connection credentials stored in DB.
    # In Kubernetes this must come from a Kubernetes Secret, never values.yaml.
    rca_master_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
