from __future__ import annotations

import json

from app.agent_loop.dependencies import InMemoryStateStore
from app.agent_loop.schemas import AgentState
from app.gateway.schemas import ChatRequest, ChatResponse
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.knowledge_loop import KnowledgeLoop


class FakeGateway:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = iter(payloads)
        self.calls: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        return ChatResponse(
            content=json.dumps(next(self.payloads)),
            provider="test",
            model="test-model",
        )


class RecordingGraph(GraphRepository):
    def __init__(self) -> None:
        super().__init__()
        self.retrievals = 0

    def retrieve_subgraph(self, *args, **kwargs):
        self.retrievals += 1
        return super().retrieve_subgraph(*args, **kwargs)


class DenySafety:
    def check(self, action):
        return False


def make_graph() -> tuple[RecordingGraph, str]:
    graph = RecordingGraph()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Build feature"))
    return graph, task.id


def test_knowledge_loop_retrieves_before_each_iteration_and_updates_graph() -> None:
    graph, task_id = make_graph()
    gateway = FakeGateway([
        {"status": "in_progress", "reason": "work", "actions": [{"type": "run_command", "parameters": {}}], "expected_result": "done", "confidence": 0.8},
        {"status": "success", "reason": "done", "actions": [], "expected_result": "done", "confidence": 0.9},
    ])
    loop = KnowledgeLoop(gateway, graph=graph)

    result = loop.run(task_id, "Build feature", max_iterations=3)

    assert result.state.state == AgentState.SUCCESS
    assert result.state.iteration == 1
    assert graph.retrievals == 2
    assert len(graph.find_nodes("Result", {})) == 1
    assert "retrieved_graph" in result.context


def test_knowledge_loop_pauses_after_repeated_no_progress_and_safety_blocks_execution() -> None:
    graph, task_id = make_graph()
    gateway = FakeGateway([
        {"status": "stalled", "reason": "blocked", "actions": [{"type": "run_command", "parameters": {}}], "expected_result": "done", "confidence": 0.4},
        {"status": "stalled", "reason": "blocked", "actions": [{"type": "run_command", "parameters": {}}], "expected_result": "done", "confidence": 0.4},
    ])
    loop = KnowledgeLoop(gateway, graph=graph, safety_engine=DenySafety(), state_store=InMemoryStateStore())

    result = loop.run(task_id, "Build feature", max_iterations=5, no_progress_limit=2)

    assert result.state.state == AgentState.PAUSED
    assert result.state.iteration == 2
    assert result.state.history[-1]["request_user"] is True
    assert result.state.history[0]["actions"][0]["allowed"] is False


def test_knowledge_loop_never_exceeds_max_iterations() -> None:
    graph, task_id = make_graph()
    gateway = FakeGateway([
        {"status": "in_progress", "reason": "work", "actions": [], "expected_result": "done", "confidence": 0.5},
    ] * 2)
    loop = KnowledgeLoop(gateway, graph=graph)

    result = loop.run(task_id, "Build feature", max_iterations=2)

    assert result.state.state == AgentState.FAILED
    assert result.state.iteration == 2
    assert len(gateway.calls) == 2