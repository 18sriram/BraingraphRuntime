from __future__ import annotations

from typing import Any, Protocol

from app.agent_loop.schemas import AgentAction, AgentLoopState


class SafetyEngine(Protocol):
    def check(self, action: AgentAction) -> bool:
        """Return whether an action may execute."""


class ActionExecutor(Protocol):
    def execute(self, action: AgentAction) -> Any:
        """Execute one safety-approved action and return its output."""


class StateStore(Protocol):
    def save(self, state: AgentLoopState) -> None:
        """Persist the latest loop state."""

    def get(self, task_id: str) -> AgentLoopState | None:
        """Load a previously persisted loop state."""


class AllowAllSafetyEngine:
    def check(self, action: AgentAction) -> bool:
        return True


class NullActionExecutor:
    def execute(self, action: AgentAction) -> dict[str, Any]:
        return {"action": action.type, "status": "executed", "parameters": action.parameters}


class InMemoryStateStore:
    def __init__(self) -> None:
        self.states: dict[str, AgentLoopState] = {}

    def save(self, state: AgentLoopState) -> None:
        self.states[state.task_id] = state.model_copy(deep=True)

    def get(self, task_id: str) -> AgentLoopState | None:
        state = self.states.get(task_id)
        return state.model_copy(deep=True) if state else None
