from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from app.gateway.schemas import ChatRequest, ChatResponse, ProviderStatus
from app.config.settings import Settings
from app.local_models.schemas import LocalModel, PullProgress


class LocalProvider(Protocol):
    """Provider contract used by orchestration code, independent of vendor APIs."""

    name: str

    def generate(self, prompt: str, model: str | None = None) -> str: ...
    def chat(self, request: ChatRequest) -> ChatResponse: ...
    def embedding(self, text: str, model: str | None = None) -> list[float]: ...
    def health(self) -> ProviderStatus: ...
    def model_info(self, model: str | None = None) -> dict[str, object]: ...


class LocalModelProvider(Protocol):
    """Lifecycle contract used by LocalModelManager."""

    name: str

    def available(self) -> bool: ...
    def list_models(self) -> list[LocalModel]: ...
    def install_model(self, model: str) -> Iterator[PullProgress]: ...
    def remove_model(self, model: str) -> None: ...


def create_local_provider(settings: Settings) -> LocalProvider:
    if settings.local_model_provider == "ollama":
        from app.local_models.ollama import OllamaProvider

        return OllamaProvider(settings.ollama_base_url, settings.model_timeout_seconds, settings.local_model)
    raise ValueError(f"Unsupported local provider: {settings.local_model_provider}")
