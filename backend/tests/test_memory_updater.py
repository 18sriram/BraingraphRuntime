from __future__ import annotations

from app.agent_loop.schemas import ActionResult, AgentAction, AgentPlan
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.memory_updater import MemoryUpdater


def test_memory_updater_creates_rich_execution_memory_without_duplicate_observations() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Build feature"))
    plan = AgentPlan(status="in_progress", reason="working", actions=[], expected_result="done", confidence=0.8)
    results = [ActionResult(action=AgentAction(type="read_file"), allowed=True, output="ok")]
    updater = MemoryUpdater(graph)

    updater.update(task_id=task.id, objective="Build feature", iteration=1, plan=plan, action_results=results, model="test-model")
    updater.update(task_id=task.id, objective="Build feature", iteration=1, plan=plan, action_results=results, model="test-model")

    assert len(graph.find_nodes("Observation", {})) == 1
    assert len(graph.find_nodes("Execution", {})) == 2
    assert len(graph.find_nodes("Result", {})) == 2
    relationship_types = {relationship.type for relationship in graph._relationships.values()}
    assert {"GENERATED", "OBSERVED", "FAILED", "LINKED_TO_TASK"}.issubset(relationship_types)