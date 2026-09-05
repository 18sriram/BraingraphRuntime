from __future__ import annotations

import json
from typing import Any

import httpx

from app.agent_loop.dependencies import ActionExecutor, InMemoryStateStore, SafetyEngine, StateStore
from app.agent_loop.protocol import parse_llm_response
from app.agent_loop.schemas import ActionResult, AgentLoopState, AgentPlan, AgentRun, AgentState
from app.gateway.gateway import ModelGateway
from app.gateway.schemas import ChatMessage, ChatRequest
from app.git.integration import GitIntegration
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.safety.audit import AuditLogger
from app.safety.engine import SafetyEngine as ConcreteSafetyEngine
from app.safety.executor import SandboxExecutor
from app.schemas.graph import GraphNodeCreate, GraphRelationshipCreate
from app.core.config import get_settings
from app.schemas.workspace_context import WorkspaceContext


class AgentLoopEngine:
    """Finite-state execution loop coordinating model, safety, actions, and memory."""

    def __init__(
        self,
        gateway: ModelGateway,
        context_builder: ContextBuilder | None = None,
        safety_engine: SafetyEngine | None = None,
        executor: ActionExecutor | None = None,
        state_store: StateStore | None = None,
        graph: GraphRepository | None = None,
        git_service: GitIntegration | None = None,
        auto_commit: bool | None = None,
        workspace_context_builder: Any | None = None,
        workspace_id: int | None = None,
    ) -> None:
        self.gateway = gateway
        self.graph = graph or (context_builder.graph if context_builder else GraphRepository())
        self.context_builder = context_builder or ContextBuilder(self.graph)
        settings = get_settings()
        self.git_commit_message = settings.git_commit_message
        self.git_service = git_service
        self.auto_commit = settings.git_auto_commit if auto_commit is None else auto_commit
        self.workspace_context_builder = workspace_context_builder
        self.workspace_id = workspace_id
        if self.auto_commit and self.git_service is None:
            self.git_service = GitIntegration(settings.project_root, self.graph)
        audit_logger = AuditLogger(settings.safety_audit_log)
        self.safety_engine = safety_engine or ConcreteSafetyEngine(
            project_root=settings.project_root,
            network_enabled=settings.safety_network_enabled,
            audit_logger=audit_logger,
        )
        self.executor = executor or SandboxExecutor(
            project_root=settings.project_root,
            docker_image=settings.safety_docker_image,
            cpu_limit=settings.safety_cpu_limit,
            memory_limit_mb=settings.safety_memory_limit_mb,
            timeout_seconds=settings.safety_timeout_seconds,
            network_enabled=settings.safety_network_enabled,
            audit_logger=audit_logger,
        )
        self.state_store = state_store or InMemoryStateStore()

    def run(
        self,
        task_id: str,
        objective: str,
        *,
        max_iterations: int = 10,
        user_stop: bool = False,
        pause_requested: bool = False,
    ) -> AgentRun:
        state = AgentLoopState(
            task_id=task_id,
            objective=objective,
            max_iterations=max_iterations,
        )
        self._persist(state)
        if user_stop:
            state.state = AgentState.ABORTED
            self._persist(state)
            return AgentRun(state=state)
        if pause_requested:
            state.state = AgentState.PAUSED
            self._persist(state)
            return AgentRun(state=state)

        try:
            while state.iteration < state.max_iterations:
                state.state = AgentState.PLANNING
                self._persist(state)
                context = self.context_builder.build_context(task_id)
                workspace_context = None
                if self.workspace_context_builder is not None and self.workspace_id is not None:
                    workspace_context = self.workspace_context_builder.build(self.workspace_id, current_task=task_id)
                plan = self._plan(objective, context, workspace_context)

                if plan.status.lower() in {"success", "succeeded", "complete", "completed"}:
                    state.state = AgentState.SUCCESS
                    self._persist(state)
                    return AgentRun(state=state, context=context)
                if plan.status.lower() in {"no_progress", "stalled"}:
                    state.state = AgentState.FAILED
                    state.last_error = plan.reason
                    self._persist(state)
                    return AgentRun(state=state, context=context)

                state.state = AgentState.EXECUTING
                action_results = self._execute_actions(plan.actions)
                state.state = AgentState.OBSERVING
                state.iteration += 1
                observation = {
                    "iteration": state.iteration,
                    "actions": [result.model_dump(mode="json") for result in action_results],
                }
                state.history.append(observation)
                state.last_progress = plan.status.lower() not in {"no_progress", "stalled"}
                self._persist(state)

                state.state = AgentState.UPDATING_MEMORY
                self._update_memory(task_id, state.iteration, observation)
                self._checkpoint_iteration(task_id, state.iteration, observation)
                self._persist(state)
                if user_stop:
                    state.state = AgentState.ABORTED
                    self._persist(state)
                    return AgentRun(state=state, context=context)

            state.state = AgentState.FAILED
            state.last_error = "Maximum iterations reached"
            self._persist(state)
            return AgentRun(state=state, context=context)
        except QuotaExhaustedError as error:
            state.state = AgentState.WAITING_QUOTA
            state.last_error = str(error)
            self._persist(state)
            return AgentRun(state=state)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 429:
                state.state = AgentState.WAITING_QUOTA
            else:
                state.state = AgentState.FAILED
            state.last_error = str(error)
            self._persist(state)
            return AgentRun(state=state)
        except Exception as error:
            state.state = AgentState.FAILED
            state.last_error = str(error)
            self._persist(state)
            return AgentRun(state=state)

    def _plan(self, objective: str, context: dict[str, Any], workspace_context: WorkspaceContext | None = None) -> AgentPlan:
        request_context = {
            "objective": objective,
            "context": context,
            "workspace_context": None if workspace_context is None else workspace_context.model_dump(mode="json"),
        }
        response = self.gateway.chat(
            ChatRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=(
                            "Return only JSON matching this schema: "
                            '{"status":"in_progress","reason":"string",'
                            '"actions":[{"type":"run_command","parameters":{}}],'
                            '"expected_result":"string","confidence":0.0}'
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=json.dumps(request_context),
                    ),
                ]
            )
        )
        try:
            return parse_llm_response(response.content)
        except ValueError as error:
            raise ValueError("Model returned invalid structured JSON protocol response") from error

    def _checkpoint_iteration(
        self, task_id: str, iteration: int, observation: dict[str, Any]
    ) -> None:
        if not self.auto_commit or self.git_service is None:
            return
        checkpoint = self.git_service.checkpoint(
            task_id=task_id,
            iteration=iteration,
            model_used=getattr(self.gateway.provider, "default_model", "unknown") or "unknown",
            message=self.git_commit_message,
        )
        if checkpoint is not None:
            observation["checkpoint"] = {
                "commit_hash": checkpoint.commit_hash,
                "files_changed": checkpoint.files_changed,
                "model_used": checkpoint.model_used,
            }

    def _execute_actions(self, actions: list[Any]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for action in actions:
            if not self.safety_engine.check(action):
                results.append(ActionResult(action=action, allowed=False, error="Blocked by Safety Engine"))
                continue
            try:
                results.append(ActionResult(action=action, allowed=True, output=self.executor.execute(action)))
            except Exception as error:
                results.append(ActionResult(action=action, allowed=True, error=str(error)))
        return results

    def _update_memory(self, task_id: str, iteration: int, observation: dict[str, Any]) -> None:
        result = self.graph.create_node(
            GraphNodeCreate(
                type="Result",
                name=f"Agent loop iteration {iteration}",
                properties={"iteration": iteration, "observation": observation},
            )
        )
        self.graph.create_relationship(
            GraphRelationshipCreate(source_id=task_id, target_id=result.id, type="GENERATED_BY")
        )

    def _persist(self, state: AgentLoopState) -> None:
        self.state_store.save(state)


class QuotaExhaustedError(RuntimeError):
    """Raised by a gateway adapter when the provider quota is exhausted."""
