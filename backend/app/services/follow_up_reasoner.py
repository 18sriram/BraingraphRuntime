from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.gateway.schemas import ChatMessage, ChatRequest
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository


class FollowUpDecision(BaseModel):
    should_continue: bool = Field(...)
    reason: str = Field(min_length=1)
    next_action: str = Field(min_length=1)
    follow_up_prompt: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class FollowUpReasoner:
    """Decide whether a follow-up LLM call is necessary from a compact, validated context snapshot."""

    def __init__(self, gateway: Any, context_builder: ContextBuilder | None = None) -> None:
        self.gateway = gateway
        self.context_builder = context_builder or ContextBuilder(GraphRepository())

    def decide(
        self,
        *,
        current_task: str,
        graph: GraphRepository,
        workflow_state: dict[str, Any],
        latest_execution_result: dict[str, Any],
        git_diff: str,
        errors: list[str],
        constraints: list[str],
    ) -> FollowUpDecision:
        self.context_builder.graph = graph
        context = self._build_context(current_task, graph)
        prompt = self._build_prompt(
            goal=current_task,
            state=workflow_state,
            context=context,
            latest_execution_result=latest_execution_result,
            git_diff=git_diff,
            errors=errors,
            constraints=constraints,
        )
        response = self.gateway.chat(ChatRequest(messages=[ChatMessage(role="user", content=prompt)]))
        decision = self.validate_response(response.content)
        if not decision.should_continue:
            return decision
        return decision

    def validate_response(self, content: str) -> FollowUpDecision:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Follow-up reasoner response must be non-empty JSON")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Follow-up reasoner response must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Follow-up reasoner response must be a JSON object")
        try:
            return FollowUpDecision.model_validate(payload)
        except ValidationError as error:
            raise ValueError("Follow-up reasoner response does not match required schema") from error

    def _build_context(self, current_task: str, graph: GraphRepository) -> dict[str, Any]:
        try:
            context = self.context_builder.build(current_task)
        except ValueError:
            context = self.context_builder.build_context(current_task)
            return context if isinstance(context, dict) else {}
        return context.model_dump(mode="json")

    def _build_prompt(
        self,
        *,
        goal: str,
        state: dict[str, Any],
        context: dict[str, Any],
        latest_execution_result: dict[str, Any],
        git_diff: str,
        errors: list[str],
        constraints: list[str],
    ) -> str:
        relevant_files = ", ".join(context.get("files", []) or []) or "none"
        previous_decisions = ", ".join(context.get("decisions", []) or []) or "none"
        graph_memory = context.get("graph_memory", []) or []
        graph_summary = "; ".join(f"{item.get('type', 'node')}: {item.get('name', 'unknown')}" for item in graph_memory[:8]) or "none"

        prompt = (
            "GOAL\n"
            f"{goal}\n\n"
            "CURRENT STATE\n"
            f"{json.dumps(state, sort_keys=True)}\n\n"
            "RELEVANT FILES\n"
            f"{relevant_files}\n\n"
            "PREVIOUS DECISIONS\n"
            f"{previous_decisions}\n\n"
            "ERRORS\n"
            f"{json.dumps(errors or ['none'])}\n\n"
            "CONSTRAINTS\n"
            f"{json.dumps(constraints or ['none'])}\n\n"
            "LATEST OBSERVATION\n"
            f"{json.dumps(latest_execution_result, sort_keys=True)}\n\n"
            "GIT DIFF\n"
            f"{git_diff or 'none'}\n\n"
            "GRAPH MEMORY\n"
            f"{graph_summary}\n\n"
            "Return structured JSON only with keys: should_continue, reason, next_action, follow_up_prompt, confidence."
        )
        return prompt
