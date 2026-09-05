from __future__ import annotations

import json

import pytest

from app.gateway.schemas import ChatResponse
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.follow_up_planner import FollowUpPlanner


class FakeQwen:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def chat(self, request):
        self.prompts.append(request.messages[0].content)
        return ChatResponse(content=json.dumps(self.payload), provider="ollama", model="qwen3:8b-instruct")


def make_planner(payload: dict) -> tuple[FollowUpPlanner, FakeQwen, str]:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix authentication"))
    auth_file = graph.create_node(GraphNodeCreate(type="File", name="auth.py"))
    graph.create_relationship(source_id=task.id, target_id=auth_file.id, type="CONTAINS")
    qwen = FakeQwen(payload)
    return FollowUpPlanner(qwen, ContextBuilder(graph)), qwen, task.id


def test_follow_up_planner_passes_all_observation_inputs_and_generates_cloud_prompt() -> None:
    planner, qwen, task_id = make_planner({
        "decision": "continue",
        "reason": "The failed test is actionable.",
        "next_step": "Ask a cloud worker for a focused diagnosis",
        "cloud_prompt": "Analyze the authentication test failure and recommend a safe next direction.",
        "progress_score": 0.55,
        "confidence": 0.88,
    })

    plan = planner.plan(
        task_id=task_id,
        execution_report={"status": "failed", "summary": "token validation failed"},
        git_diff="- old validation\n+ new validation",
        test_results={"passed": 4, "failed": 1},
        errors=["TokenValidationError"],
        workflow_state={"state": "OBSERVING", "iteration": 2},
        progress={"progress_score": 0.55},
        constraints=["Preserve token behavior"],
    )

    assert plan.decision == "continue"
    assert plan.cloud_prompt is not None
    prompt = qwen.prompts[0]
    for section in ("BRAIN GRAPH", "EXECUTION REPORT", "GIT DIFF", "TEST RESULTS", "ERRORS"):
        assert section in prompt
    assert "TokenValidationError" in prompt
    assert "auth.py" in prompt


def test_follow_up_planner_supports_retry_strategy_and_finish() -> None:
    planner, _, _ = make_planner({
        "decision": "retry",
        "reason": "The previous execution was blocked by a transient error.",
        "next_step": "Retry the same objective with the preserved context",
        "cloud_prompt": "Retry while preserving the current authentication constraints.",
        "progress_score": 0.4,
        "confidence": 0.8,
    })
    assert planner.validate_response(json.dumps({
        "decision": "retry",
        "reason": "retry",
        "next_step": "retry safely",
        "cloud_prompt": "Review the failure and retry.",
        "progress_score": 0.2,
        "confidence": 0.5,
    })).decision == "retry"
    assert planner.validate_response(json.dumps({
        "decision": "finish",
        "reason": "Objective is complete.",
        "next_step": "Stop the loop",
        "cloud_prompt": None,
        "progress_score": 1.0,
        "confidence": 0.99,
    })).decision == "finish"


def test_follow_up_planner_rejects_executable_prompt_content() -> None:
    planner, _, _ = make_planner({})
    with pytest.raises(ValueError, match="executable"):
        planner.validate_response(json.dumps({
            "decision": "continue",
            "reason": "run_command: rm -rf /",
            "next_step": "unsafe",
            "cloud_prompt": "Continue",
            "progress_score": 0.1,
            "confidence": 0.1,
        }))
