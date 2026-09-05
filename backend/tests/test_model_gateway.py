import httpx

from app.gateway.gateway import ModelGateway
from app.gateway.providers import OpenAIProvider
from app.gateway.schemas import ChatMessage, ChatRequest


def test_gateway_returns_common_openai_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
            request=request,
        )

    provider = OpenAIProvider(
        "test-key",
        "https://api.openai.com/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = ModelGateway(provider=provider).chat(
        ChatRequest(messages=[ChatMessage(role="user", content="Hi")], model="test-model")
    )

    assert response.model == "test-model"
    assert response.provider == "openai"
    assert response.content == "Hello"
    assert response.usage["total_tokens"] == 3


def test_gateway_retries_transient_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=request)

    provider = OpenAIProvider(
        "test-key",
        "https://api.openai.com/v1",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="Hi")]))

    assert response.content == "ok"
    assert attempts == 2
