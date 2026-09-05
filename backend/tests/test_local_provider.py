from __future__ import annotations

from app.gateway.schemas import ChatMessage, ChatRequest
from app.local_models.ollama import OllamaProvider
from app.local_models.provider import LocalProvider


class FakeLocalProvider:
    name = "fake"

    def generate(self, prompt: str, model: str | None = None) -> str:
        return prompt

    def chat(self, request: ChatRequest):
        return {"content": request.messages[0].content}

    def embedding(self, text: str, model: str | None = None) -> list[float]:
        return [float(len(text))]

    def health(self):
        return True

    def model_info(self, model: str | None = None):
        return {"model": model or "fake"}


def test_local_provider_contract_is_vendor_neutral() -> None:
    provider: LocalProvider = FakeLocalProvider()
    assert provider.generate("plan") == "plan"
    assert provider.embedding("hello") == [5.0]
    assert provider.model_info()["model"] == "fake"


def test_ollama_provider_exposes_local_provider_methods() -> None:
    provider = OllamaProvider()
    assert hasattr(provider, "generate")
    assert hasattr(provider, "chat")
    assert hasattr(provider, "embedding")
    assert hasattr(provider, "health")
    assert hasattr(provider, "model_info")