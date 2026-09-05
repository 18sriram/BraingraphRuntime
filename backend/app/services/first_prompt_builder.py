from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.gateway.schemas import ChatMessage, ChatRequest
from app.local_models.provider import LocalProvider
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNode, GraphNodeCreate, GraphRelationshipCreate


class StructuredFirstPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    current_state: str = Field(min_length=1, max_length=4000)
    relevant_files: list[str] = Field(default_factory=list, max_length=100)
    decisions: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    expected_output: str = Field(min_length=1, max_length=2000)


class FirstPromptResult(BaseModel):
    objective: str
    structured_prompt: StructuredFirstPrompt
    raw_prompt_node_id: str
    structured_prompt_node_id: str


class FirstPromptBuilder:
    """Expand a user objective into a structured, decision-ready first prompt."""

    _code_markers = re.compile(
        r"```|\b(?:shell|bash|python|javascript|typescript)\s*:\s|\b(?:rm|sudo|pip|npm|git)\s+-",
        re.IGNORECASE,
    )

    def __init__(
        self,
        provider: LocalProvider,
        graph: GraphRepository | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.provider = provider
        self.graph = graph or (context_builder.graph if context_builder else GraphRepository())
        self.context_builder = context_builder or ContextBuilder(self.graph)

    def build(
        self,
        *,
        objective: str,
        workspace_metadata: dict[str, Any],
        current_task: str,
        constraints: list[str] | None = None,
        task_id: str | None = None,
    ) -> FirstPromptResult:
        objective = objective.strip()
        current_task = current_task.strip()
        if not objective:
            raise ValueError("objective cannot be empty")
        if not current_task:
            raise ValueError("current_task cannot be empty")

        graph_context = self._graph_context(task_id, current_task)
        raw_prompt = self._build_controller_prompt(
            objective=objective,
            graph_context=graph_context,
            workspace_metadata=workspace_metadata,
            current_task=current_task,
            constraints=constraints or [],
        )
        response = self.provider.chat(
            ChatRequest(messages=[ChatMessage(role="user", content=raw_prompt)])
        )
        structured = self.validate_response(response.content)
        nodes = self._store_prompts(
            objective=objective,
            structured=structured,
            task_id=task_id,
            current_task=current_task,
            workspace_metadata=workspace_metadata,
        )
        return FirstPromptResult(
            objective=objective,
            structured_prompt=structured,
            raw_prompt_node_id=nodes["raw"].id,
            structured_prompt_node_id=nodes["structured"].id,
        )

    def validate_response(self, content: str) -> StructuredFirstPrompt:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("First prompt response must be non-empty JSON")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("First prompt response must contain JSON only") from error
        if not isinstance(payload, dict):
            raise ValueError("First prompt response must be a JSON object")
        try:
            prompt = StructuredFirstPrompt.model_validate(payload)
        except ValidationError as error:
            raise ValueError("First prompt response does not match the structured prompt schema") from error
        for value in (
            prompt.goal,
            prompt.current_state,
            prompt.expected_output,
            *prompt.relevant_files,
            *prompt.decisions,
            *prompt.constraints,
        ):
            if self._code_markers.search(value):
                raise ValueError("Structured first prompts must not contain executable code or shell commands")
        return prompt

    def _graph_context(self, task_id: str | None, current_task: str) -> dict[str, Any]:
        if task_id is None:
            return {"task": current_task, "files": [], "decisions": [], "errors": [], "graph_memory": []}
        try:
            return self.context_builder.build_context(task_id)
        except ValueError:
            return {"task": current_task, "files": [], "decisions": [], "errors": [], "graph_memory": []}

    @staticmethod
    def _build_controller_prompt(
        *,
        objective: str,
        graph_context: dict[str, Any],
        workspace_metadata: dict[str, Any],
        current_task: str,
        constraints: list[str],
    ) -> str:
        return (
            "You are Qwen, the local orchestration model. Expand the user's objective into a structured first prompt. "
            "Return JSON only with exactly these keys: goal, current_state, relevant_files, decisions, constraints, expected_output. "
            "Do not output executable code, shell commands, file edits, or action objects.\n\n"
            f"USER OBJECTIVE\n{objective}\n\n"
            f"BRAIN GRAPH\n{json.dumps(graph_context, sort_keys=True)}\n\n"
            f"WORKSPACE METADATA\n{json.dumps(workspace_metadata, sort_keys=True)}\n\n"
            f"CURRENT TASK\n{current_task}\n\n"
            f"CONSTRAINTS\n{json.dumps(constraints)}\n\n"
            "The expected_output must describe the desired result, not implementation code."
        )

    def _store_prompts(
        self,
        *,
        objective: str,
        structured: StructuredFirstPrompt,
        task_id: str | None,
        current_task: str,
        workspace_metadata: dict[str, Any],
    ) -> dict[str, GraphNode]:
        raw = self.graph.create_node(
            GraphNodeCreate(
                type="Prompt",
                name=f"User objective: {objective[:220]}",
                properties={
                    "kind": "user_objective",
                    "objective": objective,
                    "current_task": current_task,
                    "workspace_metadata": workspace_metadata,
                },
            )
        )
        expanded = self.graph.create_node(
            GraphNodeCreate(
                type="Prompt",
                name=f"Structured first prompt: {structured.goal[:200]}",
                properties={"kind": "structured_first_prompt", "prompt": structured.model_dump(mode="json")},
            )
        )
        self.graph.create_relationship(
            GraphRelationshipCreate(source_id=expanded.id, target_id=raw.id, type="GENERATED")
        )
        if task_id is not None:
            for node in (raw, expanded):
                self.graph.create_relationship(
                    GraphRelationshipCreate(source_id=node.id, target_id=task_id, type="LINKED_TO_TASK")
                )
        return {"raw": raw, "structured": expanded}
