from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.gateway.base import BaseProvider
from app.gateway.providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from app.local_models.provider import create_local_provider
from app.gateway.schemas import ChatRequest, ChatResponse, ProviderStatus


class ModelGateway:
    """Provider-neutral model interface used by the rest of the application."""

    def __init__(self, settings: Settings | None = None, provider: BaseProvider | None = None) -> None:
        self.provider = provider
        if self.provider is None:
            self.provider = self._create_provider(settings or get_settings())

    @staticmethod
    def _create_provider(settings: Settings) -> BaseProvider:
        common = {"timeout": settings.model_timeout_seconds, "max_retries": settings.model_max_retries}
        if settings.model_provider == "openai":
            return OpenAIProvider(
                settings.openai_api_key, "https://api.openai.com/v1", default_model=settings.openai_model, **common
            )
        if settings.model_provider == "anthropic":
            return AnthropicProvider(
                settings.anthropic_api_key, "https://api.anthropic.com", default_model=settings.anthropic_model, **common
            )
        if settings.model_provider == "ollama":
            return create_local_provider(settings)
        return GeminiProvider(
            settings.gemini_api_key,
            "https://generativelanguage.googleapis.com",
            default_model=settings.gemini_model,
            **common,
        )

    def chat(self, request: ChatRequest) -> ChatResponse:
        return self.provider.chat(request)

    def health(self) -> ProviderStatus:
        return self.provider.health()

    def quota_status(self) -> ProviderStatus:
        return self.provider.quota_status()
