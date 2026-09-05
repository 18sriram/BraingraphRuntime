from __future__ import annotations

import hashlib
import json
from typing import Any

from app.agent_loop.schemas import ActionResult, AgentPlan
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNode, GraphNodeCreate, GraphRelationshipCreate


class MemoryUpdater:
    """Persist the structured memory produced by each agent execution."""

    def __init__(self, graph: GraphRepository) -> None:
        self.graph = graph

    def update(
        self,
        *,
        task_id: str,
        objective: str,
        iteration: int,
        plan: AgentPlan,
        action_results: list[ActionResult],
        model: str = "unknown",
    ) -> dict[str, GraphNode]:
        observation_data = {
            "iteration": iteration,
            "plan": plan.model_dump(mode="json"),
            "actions": [result.model_dump(mode="json") for result in action_results],
        }
        fingerprint = hashlib.sha256(
            json.dumps(observation_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        observations = self.graph.find_nodes("Observation", {"fingerprint": fingerprint})
        observation = observations[0] if observations else self.graph.create_node(
            GraphNodeCreate(
                type="Observation",
                name=f"Observation iteration {iteration}",
                properties={"fingerprint": fingerprint, "observation": observation_data},
            )
        )
        execution = self.graph.create_node(
            GraphNodeCreate(
                type="Execution",
                name=f"Execution iteration {iteration}",
                properties={"iteration": iteration, "action_count": len(action_results)},
            )
        )
        result = self.graph.create_node(
            GraphNodeCreate(
                type="Result",
                name=f"Result iteration {iteration}",
                properties={"iteration": iteration, "status": plan.status, "reason": plan.reason},
            )
        )
        prompt = self.graph.create_node(
            GraphNodeCreate(type="Prompt", name=objective, properties={"iteration": iteration})
        )
        model_node = self.graph.create_node(
            GraphNodeCreate(type="Model", name=model, properties={"iteration": iteration})
        )

        self._relate(execution.id, observation.id, "OBSERVED")
        self._relate(execution.id, result.id, "GENERATED")
        self._relate(prompt.id, execution.id, "GENERATED")
        self._relate(model_node.id, execution.id, "GENERATED")
        for node in (observation, execution, result, prompt, model_node):
            self._relate(node.id, task_id, "LINKED_TO_TASK")

        outcome_type = "SOLVED" if plan.status.lower() in {"success", "succeeded", "complete", "completed"} else "FAILED"
        self._relate(result.id, task_id, outcome_type)
        return {
            "observation": observation,
            "execution": execution,
            "result": result,
            "prompt": prompt,
            "model": model_node,
        }

    def _relate(self, source_id: str, target_id: str, relationship_type: str) -> None:
        self.graph.create_relationship(
            GraphRelationshipCreate(source_id=source_id, target_id=target_id, type=relationship_type)
        )