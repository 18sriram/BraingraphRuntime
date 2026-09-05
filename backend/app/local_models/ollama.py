from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from app.gateway.base import BaseProvider
from app.gateway.schemas import ChatMessage, ChatRequest, ChatResponse, ProviderStatus
from app.local_models.schemas import LocalModel, PullProgress


class OllamaProvider(BaseProvider):
    provider_name = "ollama"
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 30.0, default_model: str = "qwen3:8b-instruct", client: httpx.Client | None = None) -> None:
        super().__init__("", base_url, timeout=timeout, default_model=default_model, client=client)

    def available(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[LocalModel]:
        response = self._client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        return [LocalModel.model_validate(item) for item in response.json().get("models", [])]

    def install_model(self, model: str) -> Iterator[PullProgress]:
        with self._client.stream("POST", f"{self.base_url}/api/pull", json={"name": model, "stream": True}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    payload = json.loads(line)
                    yield PullProgress(model=model, status=payload.get("status", "unknown"), completed=payload.get("completed"), total=payload.get("total"), digest=payload.get("digest"))

    def remove_model(self, model: str) -> None:
        response = self._client.request("DELETE", f"{self.base_url}/api/delete", json={"name": model})
        response.raise_for_status()

    def generate(self, prompt: str, model: str | None = None) -> str:
        return self.chat(ChatRequest(messages=[ChatMessage(role="user", content=prompt)], model=model)).content

    def chat(self, request: ChatRequest) -> ChatResponse:
        selected = request.model or self.default_model or "qwen3:8b-instruct"
        payload: dict[str, object] = {"model": selected, "messages": [message.model_dump() for message in request.messages], "stream": False}
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}
        data = self._request("POST", "/api/chat", json=payload).json()
        return ChatResponse(content=data.get("message", {}).get("content", ""), provider=self.provider_name, model=data.get("model", selected), finish_reason=data.get("done_reason"))

    def embedding(self, text: str, model: str | None = None) -> list[float]:
        selected = model or self.default_model or "qwen3:8b-instruct"
        data = self._request("POST", "/api/embeddings", json={"model": selected, "prompt": text}).json()
        return [float(value) for value in data.get("embedding", [])]

    def health(self) -> ProviderStatus:
        return self._status(self.available(), None if self.available() else "Ollama is not installed or not running")

    def model_info(self, model: str | None = None) -> dict[str, object]:
        selected = model or self.default_model or "qwen3:8b-instruct"
        return self._request("POST", "/api/show", json={"name": selected}).json()

    def quota_status(self) -> ProviderStatus:
        return self.health()


OllamaLocalModelProvider = OllamaProvider
