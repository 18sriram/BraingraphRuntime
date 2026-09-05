from __future__ import annotations

from app.agent_loop.schemas import AgentAction


class ActionParser:
    """Validate protocol actions before policy evaluation."""

    def parse(self, action: AgentAction | dict[str, object]) -> AgentAction:
        return AgentAction.model_validate(action)
