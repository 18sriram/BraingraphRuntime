from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNode, GraphNodeCreate, GraphRelationshipCreate


class GraphMemory:
    """Long-term structured knowledge stored in the source-of-truth graph."""

    def __init__(self, graph: GraphRepository | None = None) -> None:
        self.graph = graph or GraphRepository()

    def store(self, node_type: str, name: str, properties: dict[str, Any] | None = None) -> GraphNode:
        return self.graph.create_node(
            GraphNodeCreate(type=node_type, name=name, properties=properties or {})
        )

    def relate(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.graph.create_relationship(
            GraphRelationshipCreate(
                source_id=source_id,
                target_id=target_id,
                type=relationship_type,
                properties=properties or {},
            )
        )


class ArtifactMemory(GraphMemory):
    """Durable references to commits, files, test reports, and logs."""

    def store_commit(
        self,
        name: str,
        task_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        return self.store_artifact("GitCommit", name, task_id, properties)

    def store_file(
        self,
        name: str,
        task_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        return self.store_artifact("File", name, task_id, properties)

    def store_test_report(
        self,
        name: str,
        task_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        return self.store_artifact("TestReport", name, task_id, properties)

    def store_log(
        self,
        name: str,
        task_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        return self.store_artifact("Log", name, task_id, properties)

    def store_artifact(
        self,
        artifact_type: str,
        name: str,
        task_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        artifact = self.store(artifact_type, name, properties)
        if task_id is not None:
            self.relate(artifact.id, task_id, "REFERENCES")
        return artifact


class EpisodicMemory(GraphMemory):
    """Agent execution history, including prompts, responses, and iterations."""

    def record_execution(
        self,
        task_id: str,
        name: str,
        prompt: str,
        response: str,
        iteration: int = 1,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        execution_properties = {
            **(properties or {}),
            "iteration": iteration,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        execution = self.store("AgentExecution", name, execution_properties)
        prompt_node = self.store("Prompt", prompt, {"execution_id": execution.id})
        response_node = self.store("Response", response, {"execution_id": execution.id})
        iteration_node = self.store("Iteration", f"Iteration {iteration}", {"number": iteration})
        self.relate(execution.id, task_id, "EXECUTED_FOR")
        self.relate(execution.id, prompt_node.id, "HAS_PROMPT")
        self.relate(execution.id, response_node.id, "HAS_RESPONSE")
        self.relate(execution.id, iteration_node.id, "HAS_ITERATION")
        return execution
