from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.agent_loop.schemas import AgentAction, AgentPlan


class MalformedLLMResponse(ValueError):
    """Raised when an LLM response is not valid protocol JSON."""


def parse_llm_response(content: str) -> AgentPlan:
    """Parse JSON-only model output and reject prose, markdown, or invalid schema."""
    if not isinstance(content, str) or not content.strip():
        raise MalformedLLMResponse("LLM response must be a non-empty JSON object")
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as error:
        raise MalformedLLMResponse("LLM response must contain JSON only") from error
    if not isinstance(payload, dict):
        raise MalformedLLMResponse("LLM response must be a JSON object")
    try:
        return AgentPlan.model_validate(payload)
    except ValidationError as error:
        raise MalformedLLMResponse("LLM response does not match the structured protocol") from error


def serialize_llm_response(response: AgentPlan) -> str:
    """Serialize a validated protocol response as compact JSON only."""
    return response.model_dump_json()


def serialize_action(action: AgentAction) -> dict[str, Any]:
    """Return a JSON-compatible action payload."""
    return action.model_dump(mode="json")
