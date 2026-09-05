from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.graph import (
    GraphNode,
    GraphNodeCreate,
    GraphRelationship,
    GraphRelationshipCreate,
    GraphSubgraph,
)


@dataclass
class InMemoryGraphNode:
    id: str
    type: str
    name: str
    properties: dict[str, Any]


@dataclass
class InMemoryGraphRelationship:
    id: str
    source_id: str
    target_id: str
    type: str
    properties: dict[str, Any]


class GraphRepository:
    """In-memory graph abstraction for Phase 2 infrastructure testing.

    This repository intentionally uses a lightweight in-memory store so the graph
    contracts can be validated without requiring a live Neo4j instance for unit
    tests. The public API matches the shape needed by a Neo4j-backed production
    implementation later.
    """

    _nodes: dict[str, InMemoryGraphNode] = {}
    _relationships: dict[str, InMemoryGraphRelationship] = {}

    def __init__(self) -> None:
        self._nodes = dict(self.__class__._nodes)
        self._relationships = dict(self.__class__._relationships)

    def create_node(self, node: GraphNodeCreate) -> GraphNode:
        node_id = f"{node.type.lower()}-{len(self._nodes) + 1}"
        record = InMemoryGraphNode(
            id=node_id,
            type=node.type,
            name=node.name,
            properties=dict(node.properties),
        )
        self._nodes[node_id] = record
        return GraphNode(id=record.id, type=record.type, name=record.name, properties=record.properties)

    def get_node(self, node_id: str) -> GraphNode | None:
        record = self._nodes.get(node_id)
        if record is None:
            return None
        return GraphNode(id=record.id, type=record.type, name=record.name, properties=record.properties)

    def find_nodes(self, node_type: str, properties: dict[str, Any]) -> list[GraphNode]:
        return [
            GraphNode(id=record.id, type=record.type, name=record.name, properties=dict(record.properties))
            for record in self._nodes.values()
            if record.type == node_type and all(record.properties.get(key) == value for key, value in properties.items())
        ]

    def update_node(self, node_id: str, values: dict[str, Any]) -> GraphNode:
        record = self._nodes[node_id]
        if "name" in values:
            record.name = values["name"]
        if "properties" in values:
            record.properties = dict(values["properties"])
        if "type" in values:
            record.type = values["type"]
        return GraphNode(id=record.id, type=record.type, name=record.name, properties=record.properties)

    def delete_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        self._relationships = {
            rel_id: rel
            for rel_id, rel in self._relationships.items()
            if rel.source_id != node_id and rel.target_id != node_id
        }
        return True

    def create_relationship(
        self,
        relationship: GraphRelationshipCreate | None = None,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        type: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphRelationship:
        if relationship is None:
            if source_id is None or target_id is None or type is None:
                raise ValueError("source_id, target_id, and type are required when creating a relationship")
            relationship = GraphRelationshipCreate(
                source_id=source_id,
                target_id=target_id,
                type=type,
                properties=properties or {},
            )
        rel_id = f"{relationship.type.lower()}-{len(self._relationships) + 1}"
        record = InMemoryGraphRelationship(
            id=rel_id,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            type=relationship.type,
            properties=dict(relationship.properties),
        )
        self._relationships[rel_id] = record
        return GraphRelationship(
            id=record.id,
            source_id=record.source_id,
            target_id=record.target_id,
            type=record.type,
            properties=record.properties,
        )

    def get_neighbors(self, node_id: str) -> list[GraphNode]:
        neighbors: list[GraphNode] = []
        for rel in self._relationships.values():
            if rel.source_id == node_id:
                neighbor = self._nodes.get(rel.target_id)
                if neighbor is not None:
                    neighbors.append(
                        GraphNode(
                            id=neighbor.id,
                            type=neighbor.type,
                            name=neighbor.name,
                            properties=neighbor.properties,
                        )
                    )
        return neighbors

    def retrieve_subgraph(
        self,
        root_node_id: str,
        max_depth: int = 1,
        bidirectional: bool = False,
    ) -> GraphSubgraph:
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(root_node_id, 0)]
        relationship_ids: set[str] = set()
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            if depth >= max_depth:
                continue
            for rel in self._relationships.values():
                if rel.source_id == current_id:
                    relationship_ids.add(rel.id)
                    queue.append((rel.target_id, depth + 1))
                elif bidirectional and rel.target_id == current_id:
                    relationship_ids.add(rel.id)
                    queue.append((rel.source_id, depth + 1))

        nodes = [self.get_node(node_id) for node_id in visited if self.get_node(node_id) is not None]
        relationships = [
            GraphRelationship(
                id=rel.id,
                source_id=rel.source_id,
                target_id=rel.target_id,
                type=rel.type,
                properties=rel.properties,
            )
            for rel in self._relationships.values()
            if rel.id in relationship_ids or rel.source_id == root_node_id
        ]
        return GraphSubgraph(nodes=[node for node in nodes if node is not None], relationships=relationships)

    def delete_relationship(self, relationship_id: str) -> bool:
        if relationship_id not in self._relationships:
            return False
        del self._relationships[relationship_id]
        return True


class TaskRepository:
    def __init__(self, graph: GraphRepository | None = None) -> None:
        self.graph = graph or GraphRepository()

    def create_task(self, name: str, project_id: str | None = None) -> GraphNode:
        task = self.graph.create_node(
            GraphNodeCreate(
                type="Task",
                name=name,
                properties={"project_id": project_id} if project_id is not None else {},
            )
        )
        if project_id is not None:
            self.graph.create_relationship(
                GraphRelationshipCreate(
                    source_id=project_id,
                    target_id=task.id,
                    type="HAS_TASK",
                )
            )
        return task

    def get_tasks_for_project(self, project_id: str) -> list[GraphNode]:
        return self.graph.get_neighbors(project_id)


class DecisionRepository:
    def __init__(self, graph: GraphRepository | None = None) -> None:
        self.graph = graph or GraphRepository()

    def create_decision(self, name: str, project_id: str | None = None) -> GraphNode:
        decision = self.graph.create_node(
            GraphNodeCreate(
                type="Decision",
                name=name,
                properties={"project_id": project_id} if project_id is not None else {},
            )
        )
        if project_id is not None:
            self.graph.create_relationship(
                GraphRelationshipCreate(
                    source_id=project_id,
                    target_id=decision.id,
                    type="HAS_DECISION",
                )
            )
        return decision


class ExperimentRepository:
    def __init__(self, graph: GraphRepository | None = None) -> None:
        self.graph = graph or GraphRepository()

    def create_experiment(self, name: str, task_id: str | None = None) -> GraphNode:
        experiment = self.graph.create_node(
            GraphNodeCreate(
                type="Experiment",
                name=name,
                properties={"task_id": task_id} if task_id is not None else {},
            )
        )
        if task_id is not None:
            self.graph.create_relationship(
                GraphRelationshipCreate(
                    source_id=task_id,
                    target_id=experiment.id,
                    type="CONTAINS",
                )
            )
        return experiment
