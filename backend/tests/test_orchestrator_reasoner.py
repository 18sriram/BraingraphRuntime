from __future__ import annotations

import json

import pytest

from app.gateway.schemas import ChatResponse
from app.local_models.provider import LocalProvider
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.orchestrator_reasoner import OrchestratorReasoner


class FakeProvider:
    name = "fake-local"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def chat(self, request):
        self.prompts.append(request.messages[0].content)
        return ChatResponse(content=json.dumps(self.payload), provider=self.name, model="test")

    def generate(self, prompt: str, model: str | None = None) -> str:
        return ""

    def embedding(self, text: str, model: str | None = None) -> list[float]:
        return []

    def health(self):
        return None

    def model_info(self, model: str | None = None):
        return {}


def make_reasoner(payload: dict) -> tuple[OrchestratorReasoner, FakeProvider, str]:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Improve tests"))
    graph.create_node(GraphNodeCreate(type="Decision", name="Use focused tests"))
    graph.create_relationship(source_id=task.id, target_id="decision-2", type="CONTAINS")
    provider = FakeProvider(payload)
    return OrchestratorReasoner(provider, context_builder=__import__("app.memory.context_builder", fromlist=["ContextBuilder"]).ContextBuilder(graph)), provider, task.id


def test_orchestrator_reasoner_returns_decision_only_json_with_graph_context() -> None:
    reasoner, provider, task_id = make_reasoner({
        "decision": "continue",
        "next_step": "Ask a cloud worker to inspect the failing test summary",
        "follow_up_prompt": "Review the latest test failure summary and suggest the safest next direction.",
        "cloud_reasoning_required": True,
        "progress_score": 0.42,
        "reason": "The graph shows an unresolved test decision.",
        "confidence": 0.87,
    })

    decision = reasoner.decide(
        task_id=task_id,
        workflow_state={"state": "EXECUTING", "iteration": 2},
        latest_observation={"tests": "1 failing"},
        progress={"progress_score": 0.42},
    )

    assert decision.decision == "continue"
    assert decision.cloud_reasoning_required is True
    assert "BRAIN GRAPH" in provider.prompts[0]
    assert "Use focused tests" in provider.prompts[0]


def test_orchestrator_reasoner_supports_pause_and_resume_without_prompt() -> None:
    reasoner, _, _ = make_reasoner({
        "decision": "pause",
        "next_step": "Wait for user guidance",
        "follow_up_prompt": None,
        "cloud_reasoning_required": False,
        "progress_score": 0.1,
        "reason": "Progress has stopped.",
        "confidence": 0.9,
    })
    assert reasoner.decide(task_id="missing", workflow_state={}, latest_observation={}).decision == "pause"


def test_orchestrator_reasoner_rejects_executable_output() -> None:
    reasoner, _, _ = make_reasoner({})
    with pytest.raises(ValueError, match="executable"):
        reasoner.validate_response(json.dumps({
            "decision": "continue",
            "next_step": "run_command: rm -rf /",
            "follow_up_prompt": "Continue",
            "cloud_reasoning_required": False,
            "progress_score": 0.2,
            "reason": "unsafe",
            "confidence": 0.1,
        }))
