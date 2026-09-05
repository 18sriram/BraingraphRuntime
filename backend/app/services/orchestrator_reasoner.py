from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.local_models.provider import LocalProvider
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository


class OrchestratorDecision(BaseModel):
    """Decision-only output for runtime orchestration."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["continue", "pause", "resume", "finish", "fail"]
    next_step: str = Field(min_length=1, max_length=500)
    follow_up_prompt: str | None = Field(default=None, max_length=2000)
    cloud_reasoning_required: bool
    progress_score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)


class OrchestratorReasoner:
    """Use the local model to make validated, non-executable runtime decisions."""

    _code_markers = re.compile(r"```|\b(?:shell|bash|python|javascript|typescript)\s*:\s|\b(?:rm|sudo|pip|npm|git)\s+-", re.IGNORECASE)

    def __init__(self, provider: LocalProvider, context_builder: ContextBuilder | None = None) -> None:
        self.provider = provider
        self.context_builder = context_builder or ContextBuilder(GraphRepository())

    def decide(
        self,
        *,
        task_id: str,
        workflow_state: dict[str, Any],
        latest_observation: dict[str, Any],
        progress: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> OrchestratorDecision:
        context = self._graph_context(task_id)
        prompt = self._prompt(
            task_id=task_id,
            workflow_state=workflow_state,
            graph_context=context,
            latest_observation=latest_observation,
            progress=progress or {},
            constraints=constraints or [],
            errors=errors or [],
        )
        response = self.provider.chat(self._request(prompt))
        return self.validate_response(response.content)

    def validate_response(self, content: str) -> OrchestratorDecision:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Orchestrator response must be non-empty JSON")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Orchestrator response must contain JSON only") from error
        if not isinstance(payload, dict):
            raise ValueError("Orchestrator response must be a JSON object")
        try:
            decision = OrchestratorDecision.model_validate(payload)
        except ValidationError as error:
            raise ValueError("Orchestrator response does not match the decision schema") from error
        self._validate_decision(decision)
        return decision

    def _graph_context(self, task_id: str) -> dict[str, Any]:
        try:
            return self.context_builder.build_context(task_id)
        except ValueError:
            return {"task": task_id, "graph_memory": [], "artifact_memory": [], "episodic_memory": []}

    @staticmethod
    def _request(prompt: str):
        from app.gateway.schemas import ChatMessage, ChatRequest

        return ChatRequest(messages=[ChatMessage(role="user", content=prompt)])

    @classmethod
    def _validate_decision(cls, decision: OrchestratorDecision) -> None:
        for value in (decision.next_step, decision.follow_up_prompt or "", decision.reason):
            if cls._code_markers.search(value):
                raise ValueError("Orchestrator decisions must not contain executable code or shell commands")
        if decision.decision == "continue" and not decision.follow_up_prompt:
            raise ValueError("A continue decision requires a follow-up prompt")
        if decision.decision in {"pause", "finish", "fail"} and decision.follow_up_prompt:
            raise ValueError("Terminal or paused decisions must not include a follow-up prompt")

    def _prompt(
        self,
        *,
        task_id: str,
        workflow_state: dict[str, Any],
        graph_context: dict[str, Any],
        latest_observation: dict[str, Any],
        progress: dict[str, Any],
        constraints: list[str],
        errors: list[str],
    ) -> str:
        compact_graph = {
            "task": graph_context.get("task", task_id),
            "files": graph_context.get("files", [])[:20],
            "decisions": graph_context.get("decisions", [])[:20],
            "errors": graph_context.get("errors", [])[:20],
            "graph_memory": graph_context.get("graph_memory", [])[:20],
        }
        return (
            "You are the local orchestration model. Make a decision only. "
            "Never output executable code, shell commands, file edits, or action objects. "
            "Return JSON only with exactly these keys: decision, next_step, follow_up_prompt, "
            "cloud_reasoning_required, progress_score, reason, confidence.\n\n"
            f"TASK ID\n{task_id}\n\n"
            f"WORKFLOW STATE\n{json.dumps(workflow_state, sort_keys=True)}\n\n"
            f"BRAIN GRAPH\n{json.dumps(compact_graph, sort_keys=True)}\n\n"
            f"LATEST OBSERVATION\n{json.dumps(latest_observation, sort_keys=True)}\n\n"
            f"PROGRESS\n{json.dumps(progress, sort_keys=True)}\n\n"
            f"CONSTRAINTS\n{json.dumps(constraints)}\n\n"
            f"ERRORS\n{json.dumps(errors)}\n\n"
            "Allowed decisions: continue, pause, resume, finish, fail. "
            "follow_up_prompt must be natural-language guidance only and null unless decision is continue or resume."
        )
