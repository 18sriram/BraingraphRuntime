from app.memory.context_builder import ContextBuilder
from app.memory.engine import ArtifactMemory, EpisodicMemory, GraphMemory
from app.schemas.graph import GraphNodeCreate
from app.repositories.graph_repository import GraphRepository


def test_context_builder_returns_structured_two_hop_context() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix runtime", properties={}))
    decision = GraphMemory(graph).store("Decision", "Use graph as source of truth")
    GraphMemory(graph).relate(task.id, decision.id, "HAS_DECISION")
    error = GraphMemory(graph).store("Error", "Previous failure")
    GraphMemory(graph).relate(error.id, task.id, "CAUSED")
    file_node = ArtifactMemory(graph).store_artifact(
        "File", "runtime.py", task.id, {"timestamp": "2026-08-30T10:00:00Z"}
    )
    EpisodicMemory(graph).record_execution(task.id, "Attempt 1", "Do it", "Done")

    context = ContextBuilder(graph).build(task.id)
    payload = context.model_dump()

    assert payload["task"] == task.name
    assert payload["task_reference"]["id"] == task.id
    assert {node["id"] for node in payload["graph_memory"]} >= {decision.id, error.id}
    assert payload["decisions"] == [decision.name]
    assert payload["errors"] == [error.name]
    assert payload["files"] == ["runtime.py"]
    assert payload["artifact_memory"][0]["id"] == file_node.id
    assert any(node["type"] == "AgentExecution" for node in payload["episodic_memory"])
    assert any(relationship["type"] == "CAUSED" for relationship in payload["relationships"])
