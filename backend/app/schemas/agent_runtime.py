from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.agent_loop.schemas import AgentState


class AgentRuntimeCreate(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1)
    workspace_id: int | None = Field(default=None, gt=0)
    autonomous: bool = False
    allow_follow_up_prompts: bool = True


class AgentRuntimeEvent(BaseModel):
    event: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeRead(BaseModel):
    task_id: str
    workspace_id: int | None
    objective: str
    state: AgentState
    iteration: int
    autonomous: bool
    allow_follow_up_prompts: bool
    payload: dict[str, Any]
    updated_at: datetime