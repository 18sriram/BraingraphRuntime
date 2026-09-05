from __future__ import annotations

from typing import Any

from app.gateway.base import BaseProvider
from app.gateway.schemas import ChatRequest, ChatResponse, ProviderStatus


def _messages(request: ChatRequest) -> list[dict[str, str]]:
    return [message.model_dump() for message in request.messages]


def _usage(data: dict[str, Any]) -> dict[str, int]:
    usage = data.get("usage", {})
    return {
        key: int(value)
        for key, value in usage.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"}
        and isinstance(value, (int, float))
    }


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def chat(self, request: ChatRequest) -> ChatResponse:
        model = request.model or self.default_model or "gpt-4o-mini"
        data: dict[str, Any] = {"model": model, "messages": _messages(request)}
        if request.temperature is not None:
            data["temperature"] = request.temperature
        if request.max_tokens is not None:
            data["max_tokens"] = request.max_tokens
        payload = self._request(
            "POST", "/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json=data
        ).json()
        choice = payload["choices"][0]
        return ChatResponse(
            content=choice["message"]["content"],
            provider=self.provider_name,
            model=payload.get("model", model),
            finish_reason=choice.get("finish_reason"),
            usage=_usage(payload),
        )

    def health(self) -> ProviderStatus:
        try:
            self._request("GET", "/models", headers={"Authorization": f"Bearer {self.api_key}"})
            return self._status(True)
        except Exception as error:
            return self._status(False, str(error))

    def quota_status(self) -> ProviderStatus:
        return self.health()


class AnthropicProvider(BaseProvider):
    provider_name = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    def chat(self, request: ChatRequest) -> ChatResponse:
        messages = [message for message in request.messages if message.role != "system"]
        data: dict[str, Any] = {
            "model": request.model or self.default_model or "claude-3-5-haiku-latest",
            "max_tokens": request.max_tokens or 1024,
            "messages": _messages(ChatRequest(messages=messages or request.messages)),
        }
        system = next((message.content for message in request.messages if message.role == "system"), None)
        if system:
            data["system"] = system
        if request.temperature is not None:
            data["temperature"] = request.temperature
        payload = self._request("POST", "/v1/messages", headers=self._headers(), json=data).json()
        return ChatResponse(
            content="".join(block["text"] for block in payload["content"] if block["type"] == "text"),
            provider=self.provider_name,
            model=payload.get("model", data["model"]),
            finish_reason=payload.get("stop_reason"),
            usage=_usage(payload),
        )

    def health(self) -> ProviderStatus:
        try:
            self._request("GET", "/v1/models", headers=self._headers())
            return self._status(True)
        except Exception as error:
            return self._status(False, str(error))

    def quota_status(self) -> ProviderStatus:
        return self.health()


class GeminiProvider(BaseProvider):
    provider_name = "gemini"

    def chat(self, request: ChatRequest) -> ChatResponse:
        model = request.model or self.default_model or "gemini-1.5-flash"
        contents = [
            {"role": "model" if message.role == "assistant" else "user", "parts": [{"text": message.content}]}
            for message in request.messages
            if message.role != "system"
        ]
        data: dict[str, Any] = {"contents": contents}
        if request.temperature is not None:
            data["generationConfig"] = {"temperature": request.temperature}
        payload = self._request(
            "POST", f"/v1beta/models/{model}:generateContent", params={"key": self.api_key}, json=data
        ).json()
        candidate = payload["candidates"][0]
        return ChatResponse(
            content="".join(part["text"] for part in candidate["content"]["parts"]),
            provider=self.provider_name,
            model=model,
            finish_reason=candidate.get("finishReason"),
            usage=_usage(payload),
        )

    def health(self) -> ProviderStatus:
        try:
            self._request("GET", "/v1beta/models", params={"key": self.api_key})
            return self._status(True)
        except Exception as error:
            return self._status(False, str(error))

    def quota_status(self) -> ProviderStatus:
        return self.health()


