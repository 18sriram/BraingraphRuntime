from __future__ import annotations

import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.gateway.schemas import ChatMessage, ChatRequest
from app.local_models.provider import LocalProvider
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository


RoutingChoice = Literal["NO_ACTION", "EXECUTE_LOCAL", "CALL_CLOUD", "ASK_USER", "PAUSE"]


class RoutingDecision(BaseModel):
    """Validated controller output. This describes work; it never contains code."""

    model_config = ConfigDict(extra="forbid")

    route: RoutingChoice
    reason: str = Field(min_length=1, max_length=2000)
    next_step: str = Field(min_length=1, max_length=500)
    follow_up_prompt: str | None = Field(default=None, max_length=2000)
    cloud_context: dict[str, Any] | None = None
    selected_provider: str | None = None
    progress_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class RoutingEngine:
    """Keep the local orchestration model in control of all routing decisions."""

    def __init__(
        self,
        local_provider: LocalProvider,
        context_builder: ContextBuilder | None = None,
        cloud_provider_selector: Callable[[list[str]], str | None] | None = None,
    ) -> None:
        self.local_provider = local_provider
        self.context_builder = context_builder or ContextBuilder(GraphRepository())
        self.cloud_provider_selector = cloud_provider_selector or self._select_default_cloud_provider

    def route(
        self,
        *,
        task_id: str,
        workflow_state: dict[str, Any],
        latest_observation: dict[str, Any],
        progress: dict[str, Any] | None = None,
        available_cloud_providers: list[str] | None = None,
        constraints: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> RoutingDecision:
        graph_context = self._graph_context(task_id)
        prompt = self._build_controller_prompt(
            task_id=task_id,
            workflow_state=workflow_state,
            graph_context=graph_context,
            latest_observation=latest_observation,
            progress=progress or {},
            constraints=constraints or [],
            errors=errors or [],
            available_cloud_providers=available_cloud_providers or [],
        )
        response = self.local_provider.chat(ChatRequest(messages=[ChatMessage(role="user", content=prompt)]))
        decision = self.validate_response(response.content)
        if decision.route == "CALL_CLOUD":
            providers = available_cloud_providers or []
            selected = self.cloud_provider_selector(providers)
            if selected is None:
                raise ValueError("Qwen requested cloud reasoning but no cloud provider is available")
            decision = decision.model_copy(
                update={
                    "selected_provider": selected,
                    "cloud_context": self._cloud_context(
                        task_id=task_id,
                        graph_context=graph_context,
                        workflow_state=workflow_state,
                        latest_observation=latest_observation,
                        progress=progress or {},
                        constraints=constraints or [],
                        errors=errors or [],
                    ),
                }
            )
        return decision

    def validate_response(self, content: str) -> RoutingDecision:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Routing response must be non-empty JSON")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Routing response must contain JSON only") from error
        if not isinstance(payload, dict):
            raise ValueError("Routing response must be a JSON object")
        try:
            decision = RoutingDecision.model_validate(payload)
        except ValidationError as error:
            raise ValueError("Routing response does not match the routing schema") from error
        if decision.route == "CALL_CLOUD" and not decision.follow_up_prompt:
            raise ValueError("CALL_CLOUD requires a follow-up prompt")
        if decision.route != "CALL_CLOUD" and (decision.cloud_context or decision.selected_provider):
            raise ValueError("Cloud routing fields are only valid for CALL_CLOUD")
        return decision

    def _graph_context(self, task_id: str) -> dict[str, Any]:
        try:
            return self.context_builder.build_context(task_id)
        except ValueError:
            return {"task": task_id, "files": [], "decisions": [], "errors": [], "graph_memory": []}

    @staticmethod
    def _select_default_cloud_provider(providers: list[str]) -> str | None:
        for provider in ("openai", "anthropic", "gemini"):
            if provider in providers:
                return provider
        return providers[0] if providers else None

    @staticmethod
    def _cloud_context(
        *,
        task_id: str,
        graph_context: dict[str, Any],
        workflow_state: dict[str, Any],
        latest_observation: dict[str, Any],
        progress: dict[str, Any],
        constraints: list[str],
        errors: list[str],
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "workflow_state": workflow_state,
            "latest_observation": latest_observation,
            "progress": progress,
            "constraints": constraints,
            "errors": errors,
            "brain_graph": {
                "task": graph_context.get("task", task_id),
                "files": graph_context.get("files", [])[:20],
                "decisions": graph_context.get("decisions", [])[:20],
                "errors": graph_context.get("errors", [])[:20],
                "graph_memory": graph_context.get("graph_memory", [])[:20],
            },
        }

    @staticmethod
    def _build_controller_prompt(
        *,
        task_id: str,
        workflow_state: dict[str, Any],
        graph_context: dict[str, Any],
        latest_observation: dict[str, Any],
        progress: dict[str, Any],
        constraints: list[str],
        errors: list[str],
        available_cloud_providers: list[str],
    ) -> str:
        return (
            "You are Qwen, the local runtime controller. You always decide the route. "
            "Cloud models never decide workflow or routing. Return JSON only and never output code, commands, or action objects. "
            "Choose exactly one route: NO_ACTION, EXECUTE_LOCAL, CALL_CLOUD, ASK_USER, PAUSE. "
            "For CALL_CLOUD, provide a natural-language follow_up_prompt; cloud_context and selected_provider must be null because the runtime fills them.\n\n"
            f"TASK\n{task_id}\n\n"
            f"WORKFLOW STATE\n{json.dumps(workflow_state, sort_keys=True)}\n\n"
            f"BRAIN GRAPH\n{json.dumps(graph_context, sort_keys=True)}\n\n"
            f"LATEST OBSERVATION\n{json.dumps(latest_observation, sort_keys=True)}\n\n"
            f"PROGRESS\n{json.dumps(progress, sort_keys=True)}\n\n"
            f"CONSTRAINTS\n{json.dumps(constraints)}\n\n"
            f"ERRORS\n{json.dumps(errors)}\n\n"
            f"AVAILABLE CLOUD PROVIDERS\n{json.dumps(available_cloud_providers)}\n\n"
            "Schema: {route, reason, next_step, follow_up_prompt, cloud_context, selected_provider, progress_score, confidence}."
        )
