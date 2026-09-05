from __future__ import annotations

import json
from typing import Any, Callable

from app.agent_loop.dependencies import (
    ActionExecutor,
    AllowAllSafetyEngine,
    InMemoryStateStore,
    NullActionExecutor,
    SafetyEngine,
    StateStore,
)
from app.agent_loop.protocol import parse_llm_response
from app.agent_loop.schemas import ActionResult, AgentLoopState, AgentPlan, AgentRun, AgentState
from app.gateway.gateway import ModelGateway
from app.gateway.schemas import ChatMessage, ChatRequest
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate, GraphRelationshipCreate
from app.services.progress_evaluator import ProgressEvaluator, ProgressEvaluation
from app.services.memory_updater import MemoryUpdater


class KnowledgeLoop:
    """Iteratively reason over graph knowledge, execute safe actions, and learn from results."""

    def __init__(
        self,
        gateway: ModelGateway,
        graph: GraphRepository | None = None,
        context_builder: ContextBuilder | None = None,
        safety_engine: SafetyEngine | None = None,
        executor: ActionExecutor | None = None,
        state_store: StateStore | None = None,
        progress_evaluator: ProgressEvaluator | Callable[[AgentPlan, list[ActionResult], dict[str, Any]], bool] | None = None,
        user_requester: Callable[[AgentLoopState], None] | None = None,
        control_state: Callable[[], AgentState] | None = None,
    ) -> None:
        self.gateway = gateway
        self.graph = graph or (context_builder.graph if context_builder else GraphRepository())
        self.context_builder = context_builder or ContextBuilder(self.graph)
        self.safety_engine = safety_engine or AllowAllSafetyEngine()
        self.executor = executor or NullActionExecutor()
        self.state_store = state_store or InMemoryStateStore()
        self.progress_evaluator = progress_evaluator or ProgressEvaluator()
        self.memory_updater = MemoryUpdater(self.graph)
        self.user_requester = user_requester
        self.control_state = control_state

    def run(
        self,
        task_id: str,
        objective: str,
        *,
        max_iterations: int = 10,
        no_progress_limit: int = 3,
    ) -> AgentRun:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be greater than zero")
        if no_progress_limit <= 0:
            raise ValueError("no_progress_limit must be greater than zero")

        state = AgentLoopState(task_id=task_id, objective=objective, max_iterations=max_iterations)
        self._persist(state)
        context: dict[str, Any] = {}
        consecutive_no_progress = 0

        while state.iteration < state.max_iterations:
            if self.control_state is not None and self.control_state() == AgentState.OFF:
                state.state = AgentState.OFF
                state.last_error = "Agent control is OFF"
                return AgentRun(state=state, context=context)
            state.state = AgentState.PLANNING
            # Retrieval and context construction happen afresh before every model call.
            context = self.context_builder.build_context(task_id)
            context["retrieved_graph"] = {
                "nodes": context.get("graph_memory", []),
                "relationships": context.get("relationships", []),
            }
            plan = self._call_llm(objective, context)

            if self._objective_achieved(plan):
                state.state = AgentState.SUCCESS
                state.last_progress = True
                self._persist(state)
                return AgentRun(state=state, context=context)

            state.state = AgentState.EXECUTING
            action_results = self._execute_actions(plan.actions)
            state.iteration += 1
            state.state = AgentState.OBSERVING
            observation = {
                "iteration": state.iteration,
                "plan": plan.model_dump(mode="json"),
                "actions": [result.model_dump(mode="json") for result in action_results],
            }
            state.history.append(observation)
            state.state = AgentState.UPDATING_MEMORY
            self.memory_updater.update(
                task_id=task_id,
                objective=objective,
                iteration=state.iteration,
                plan=plan,
                action_results=action_results,
                model=getattr(self.gateway, "model", getattr(self.gateway, "default_model", "unknown")),
            )
            evaluation = self._evaluate_progress_result(plan, action_results, context, state.iteration)
            state.last_progress = (
                evaluation.score_delta >= 0
                and not evaluation.is_stuck
                and plan.status.lower() not in {"no_progress", "stalled"}
            )
            state.progress_score = evaluation.progress_score
            state.stop_report = evaluation.stop_report
            consecutive_no_progress = 0 if state.last_progress else consecutive_no_progress + 1
            self._persist(state)

            if self.control_state is not None and self.control_state() == AgentState.PAUSED:
                state.state = AgentState.PAUSED
                self._persist(state)
                return AgentRun(state=state, context=context)

            if evaluation.is_stuck or consecutive_no_progress >= no_progress_limit:
                state.state = AgentState.PAUSED
                state.last_error = evaluation.stop_report or "No progress threshold reached; user input required"
                state.stop_report = state.last_error
                state.history.append({"iteration": state.iteration, "request_user": True, "reason": state.last_error, "status": "STUCK" if evaluation.is_stuck else "PAUSED"})
                if self.user_requester is not None:
                    self.user_requester(state)
                self._persist(state)
                return AgentRun(state=state, context=context)

        state.state = AgentState.FAILED
        state.last_error = "Maximum iterations reached"
        self._persist(state)
        return AgentRun(state=state, context=context)

    def _call_llm(self, objective: str, context: dict[str, Any]) -> AgentPlan:
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
                        content=json.dumps({"objective": objective, "context": context}),
                    ),
                ]
            )
        )
        try:
            return parse_llm_response(response.content)
        except ValueError as error:
            raise ValueError("Model returned invalid structured JSON protocol response") from error

    @staticmethod
    def _objective_achieved(plan: AgentPlan) -> bool:
        return plan.status.lower() in {"success", "succeeded", "complete", "completed"}

    def _execute_actions(self, actions: list[Any]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for action in actions:
            if self.control_state is not None and self.control_state() == AgentState.OFF:
                results.append(ActionResult(action=action, allowed=False, error="Blocked because agent control is OFF"))
                continue
            if not self.safety_engine.check(action):
                results.append(ActionResult(action=action, allowed=False, error="Blocked by Safety Engine"))
                continue
            try:
                results.append(ActionResult(action=action, allowed=True, output=self.executor.execute(action)))
            except Exception as error:
                results.append(ActionResult(action=action, allowed=True, error=str(error)))
        return results

    @staticmethod
    def _observe(plan: AgentPlan, results: list[ActionResult], iteration: int) -> dict[str, Any]:
        return {
            "iteration": iteration,
            "plan": plan.model_dump(mode="json"),
            "actions": [result.model_dump(mode="json") for result in results],
        }

    @staticmethod
    def _evaluate_progress(
        plan: AgentPlan, results: list[ActionResult], context: dict[str, Any] | None = None
    ) -> bool:
        if plan.status.lower() in {"no_progress", "stalled"}:
            return False
        return any(result.allowed and result.error is None for result in results)

    def _evaluate_progress_result(
        self,
        plan: AgentPlan,
        results: list[ActionResult],
        context: dict[str, Any],
        iteration: int,
    ) -> ProgressEvaluation:
        if isinstance(self.progress_evaluator, ProgressEvaluator):
            metrics = {
                **context.get("progress_metrics", {}),
                "iteration_count": iteration,
                "files_modified": context.get("progress_metrics", {}).get(
                    "files_modified", sum(1 for result in results if result.allowed and result.error is None)
                ),
            }
            if plan.status.lower() in {"success", "succeeded", "complete", "completed"}:
                metrics["objective_completion"] = 1.0
            if plan.status.lower() in {"no_progress", "stalled"}:
                metrics["errors_reduced"] = 0.0
            return self.progress_evaluator.evaluate(metrics)
        progressed = self.progress_evaluator(plan, results, context)
        return ProgressEvaluation(
            metrics={"iteration_count": iteration},
            progress_score=1.0 if progressed else 0.0,
            score_delta=1.0 if progressed else -1.0,
            is_stuck=False,
        )

    def _update_graph(self, task_id: str, iteration: int, observation: dict[str, Any]) -> None:
        result = self.graph.create_node(
            GraphNodeCreate(
                type="Result",
                name=f"Knowledge loop iteration {iteration}",
                properties={"iteration": iteration, "observation": observation},
            )
        )
        self.graph.create_relationship(
            GraphRelationshipCreate(source_id=task_id, target_id=result.id, type="GENERATED_BY")
        )

    def _persist(self, state: AgentLoopState) -> None:
        self.state_store.save(state)