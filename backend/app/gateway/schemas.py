from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


class ChatResponse(BaseModel):
    content: str
    provider: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


class ProviderStatus(BaseModel):
    provider: str
    available: bool
    quota_remaining: str | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
