from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LocalModel(BaseModel):
    name: str
    size: int | None = None
    digest: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PullProgress(BaseModel):
    model: str
    status: str
    completed: int | None = None
    total: int | None = None
    digest: str | None = None
