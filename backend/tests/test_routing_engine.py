from __future__ import annotations

import json

import pytest

from app.gateway.schemas import ChatResponse
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.routing_engine import RoutingEngine


class FakeQwen:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def chat(self, request):
        self.calls += 1
        return ChatResponse(content=json.dumps(self.payload), provider="ollama", model="qwen3:8b-instruct")


def make_engine(payload: dict) -> tuple[RoutingEngine, FakeQwen, str]:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Investigate failure"))
    graph.create_node(GraphNodeCreate(type="Decision", name="Inspect test report"))
    return RoutingEngine(FakeQwen(payload), ContextBuilder(graph)), FakeQwen(payload), task.id


def test_qwen_controls_call_cloud_and_engine_builds_optimized_context() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Investigate failure"))
    graph.create_node(GraphNodeCreate(type="Decision", name="Inspect test report"))
    qwen = FakeQwen({
        "route": "CALL_CLOUD",
        "reason": "The local context is insufficient.",
        "next_step": "Ask a cloud worker for a focused diagnosis",
        "follow_up_prompt": "Review the test report and identify likely root causes.",
        "progress_score": 0.3,
        "confidence": 0.9,
        "cloud_context": None,
        "selected_provider": None,
    })
    engine = RoutingEngine(qwen, ContextBuilder(graph))

    decision = engine.route(
        task_id=task.id,
        workflow_state={"state": "PLANNING", "iteration": 1},
        latest_observation={"status": "failed"},
        progress={"progress_score": 0.3},
        available_cloud_providers=["anthropic", "openai"],
    )

    assert decision.route == "CALL_CLOUD"
    assert decision.selected_provider == "openai"
    assert decision.cloud_context is not None
    assert decision.cloud_context["brain_graph"]["task"] == "Investigate failure"
    assert qwen.calls == 1


def test_non_cloud_routes_do_not_select_or_call_cloud() -> None:
    for route in ("NO_ACTION", "EXECUTE_LOCAL", "ASK_USER", "PAUSE"):
        qwen = FakeQwen({
            "route": route,
            "reason": "Controller decision",
            "next_step": "Wait for the next runtime event",
            "follow_up_prompt": None,
            "cloud_context": None,
            "selected_provider": None,
            "progress_score": 0.5,
            "confidence": 0.8,
        })
        graph = GraphRepository()
        task = graph.create_node(GraphNodeCreate(type="Task", name="Task"))
        decision = RoutingEngine(qwen, ContextBuilder(graph)).route(
            task_id=task.id,
            workflow_state={},
            latest_observation={},
            available_cloud_providers=["openai"],
        )
        assert decision.route == route
        assert decision.selected_provider is None
        assert decision.cloud_context is None
        assert qwen.calls == 1


def test_call_cloud_requires_available_provider_and_follow_up_prompt() -> None:
    qwen = FakeQwen({
        "route": "CALL_CLOUD",
        "reason": "Need help",
        "next_step": "Ask cloud",
        "follow_up_prompt": "Review this context.",
        "cloud_context": None,
        "selected_provider": None,
        "progress_score": 0.2,
        "confidence": 0.7,
    })
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Task"))
    engine = RoutingEngine(qwen, ContextBuilder(graph))
    with pytest.raises(ValueError, match="no cloud provider"):
        engine.route(task_id=task.id, workflow_state={}, latest_observation={})

    with pytest.raises(ValueError, match="requires a follow-up"):
        engine.validate_response(json.dumps({
            "route": "CALL_CLOUD",
            "reason": "Need help",
            "next_step": "Ask cloud",
            "follow_up_prompt": None,
            "cloud_context": None,
            "selected_provider": None,
            "progress_score": 0.2,
            "confidence": 0.7,
        }))
