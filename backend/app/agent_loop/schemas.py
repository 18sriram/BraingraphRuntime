from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentState(StrEnum):
    OFF = "OFF"
    ON = "ON"
    READY = "READY"
    WAITING_FOR_QUOTA = "WAITING_FOR_QUOTA"
    SENDING_FIRST_PROMPT = "SENDING_FIRST_PROMPT"
    DECISION = "DECISION"
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    UPDATING_MEMORY = "UPDATING_MEMORY"
    WAITING_QUOTA = "WAITING_QUOTA"
    PAUSED = "PAUSED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


ActionType = Literal[
    "edit_file",
    "run_command",
    "read_file",
    "create_file",
    "run_tests",
    "git_commit",
    "ask_user",
]


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ActionType
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    actions: list[AgentAction] = Field(default_factory=list)
    expected_result: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class AgentLoopState(BaseModel):
    task_id: str
    objective: str
    state: AgentState = AgentState.IDLE
    iteration: int = 0
    max_iterations: int = Field(default=10, gt=0)
    last_progress: bool | None = None
    last_error: str | None = None
    progress_score: float | None = None
    stop_report: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class AgentRun(BaseModel):
    state: AgentLoopState
    context: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    action: AgentAction
    allowed: bool
    output: Any = None
    error: str | None = None

