from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExecutionReport(BaseModel):
    action_type: str
    command: str | None = None
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float = Field(ge=0)
    sandboxed: bool
    network_enabled: bool
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
