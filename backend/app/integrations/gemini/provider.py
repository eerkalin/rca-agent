from google import genai
from google.genai import types

from app.config import settings
from app.integrations.llm.prompts import build_rca_prompt, build_scope_prompt
from app.rca.rca_models import RCAResult
from app.rca.scope_models import ScopeResolution


class GeminiProvider:
    provider_type = "gemini"

    def __init__(
        self,
        config: dict | None = None,
        credentials: dict | None = None,
        model_config: dict | None = None,
    ):
        config = config or {}
        credentials = credentials or {}
        model_config = model_config or {}

        api_key = credentials.get("api_key") or config.get("api_key") or settings.gemini_api_key
        if not api_key:
            raise ValueError("Gemini connection requires api_key")

        self.client = genai.Client(api_key=api_key)
        self.model = (
            model_config.get("model")
            or config.get("default_model")
            or config.get("model")
            or settings.gemini_model
        )
        self.temperature = float(model_config.get("temperature", 0.1))
        self.max_output_tokens = int(model_config.get("max_output_tokens", 4096))

    def test_connection(self) -> dict:
        response = self.client.models.generate_content(
            model=self.model,
            contents="Reply only with OK",
        )
        return {
            "connected": True,
            "provider": "gemini",
            "model": self.model,
            "response": response.text,
        }

    def analyze_rca(
        self,
        symptom: str,
        evidence: list[dict],
        application_context: dict,
    ) -> RCAResult:
        response = self.client.models.generate_content(
            model=self.model,
            contents=build_rca_prompt(symptom, evidence, application_context),
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                response_mime_type="application/json",
                response_schema=RCAResult,
            ),
        )
        return RCAResult.model_validate_json(response.text)

    def resolve_scope(
        self,
        alert_text: str,
        technical_services: list[dict],
    ) -> ScopeResolution:
        response = self.client.models.generate_content(
            model=self.model,
            contents=build_scope_prompt(alert_text, technical_services),
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                response_mime_type="application/json",
                response_schema=ScopeResolution,
            ),
        )
        return ScopeResolution.model_validate_json(response.text)
