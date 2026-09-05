from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.gateway.schemas import ChatRequest, ChatResponse, ProviderStatus


class BaseProvider(ABC):
    provider_name: str

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        default_model: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_model = default_model
        self._client = client or httpx.Client(timeout=timeout)

    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def quota_status(self) -> ProviderStatus:
        raise NotImplementedError

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method,
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
                if response.status_code not in {408, 429} and response.status_code < 500:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"Provider returned HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as error:
                last_error = error
            if attempt < self.max_retries:
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("Provider request failed without an error")

    def _status(self, available: bool, message: str | None = None, **details: Any) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider_name,
            available=available,
            message=message,
            details=details,
        )
