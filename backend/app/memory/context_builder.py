from __future__ import annotations

from typing import Any

from app.memory.schemas import MemoryReference, RelevantContext
from app.repositories.graph_repository import GraphRepository


class ContextBuilder:
    """Build deterministic task context from graph memory, without an LLM."""

    _graph_types = {"Project", "Goal", "Task", "Function", "Model", "Result"}
    _artifact_types = {"GitCommit", "File", "TestReport", "Log"}
    _episodic_types = {"AgentExecution", "Prompt", "Response", "Iteration"}
    _ordered_types = ("File", "Decision", "Error", "Experiment", "Constraint")

    def __init__(self, graph: GraphRepository | None = None) -> None:
        self.graph = graph or GraphRepository()

    def build(self, task_id: str) -> RelevantContext:
        task = self.graph.get_node(task_id)
        if task is None:
            matching_tasks = [node for node in self.graph._nodes.values() if node.type == "Task" and node.name == task_id]
            if matching_tasks:
                task = self.graph.get_node(matching_tasks[0].id)
        if task is None:
            raise ValueError(f"Task node not found: {task_id}")

        subgraph = self.graph.retrieve_subgraph(task_id, max_depth=2, bidirectional=True)
        nodes = {node.id: node for node in subgraph.nodes}
        nodes.pop(task_id, None)

        def references(node: Any) -> MemoryReference:
            return MemoryReference(
                id=node.id,
                type=node.type,
                name=node.name,
                properties=node.properties,
            )

        graph_nodes = [node for node in nodes.values() if node.type in self._graph_types]
        artifact_nodes = [node for node in nodes.values() if node.type in self._artifact_types]
        episodic_nodes = [node for node in nodes.values() if node.type in self._episodic_types]
        selected_types = set(self._ordered_types)
        graph_nodes.extend(node for node in nodes.values() if node.type in selected_types)
        graph_nodes = list({node.id: node for node in graph_nodes}.values())

        artifact_nodes.sort(
            key=lambda node: str(
                node.properties.get("timestamp", node.properties.get("created_at", ""))
            ),
            reverse=True,
        )
        named = {
            node_type: [node.name for node in nodes.values() if node.type == node_type]
            for node_type in ("File", "Decision", "Error", "Constraint", "Experiment")
        }
        return RelevantContext(
            task=task.name,
            task_reference=references(task),
            files=named["File"],
            decisions=named["Decision"],
            errors=named["Error"],
            constraints=named["Constraint"],
            experiments=named["Experiment"],
            graph_memory=[references(node) for node in graph_nodes],
            artifact_memory=[references(node) for node in artifact_nodes],
            episodic_memory=[references(node) for node in episodic_nodes],
            relationships=[relationship.model_dump() for relationship in subgraph.relationships],
        )

    def build_context(self, task_id: str) -> dict[str, Any]:
        """Return the context as JSON-compatible data for API or task consumers."""
        return self.build(task_id).model_dump(mode="json")
