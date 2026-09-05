from __future__ import annotations

import json

from app.gateway.schemas import ChatMessage, ChatRequest, ChatResponse, ProviderStatus
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.follow_up_reasoner import FollowUpReasoner


class FakeGateway:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        return ChatResponse(
            content=json.dumps(self.payload),
            provider="openai",
            model="gpt-4o-mini",
            finish_reason="stop",
        )

    def quota_status(self) -> ProviderStatus:
        return ProviderStatus(provider="openai", available=True)


def test_follow_up_reasoner_builds_context_without_chat_history_and_validates_json() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix auth", properties={"workspace_id": 1}))
    graph.create_node(GraphNodeCreate(type="File", name="auth.py", properties={"workspace_id": 1}))
    graph.create_node(GraphNodeCreate(type="Decision", name="Add retry after quota", properties={"workspace_id": 1}))
    graph.create_node(GraphNodeCreate(type="Error", name="Timeout", properties={"workspace_id": 1}))
    graph.create_node(GraphNodeCreate(type="Constraint", name="Do not remove auth", properties={"workspace_id": 1}))
    graph.create_relationship(type="CONTAINS", source_id=task.id, target_id=graph.find_nodes("File", {"workspace_id": 1})[0].id)

    gateway = FakeGateway({
        "should_continue": True,
        "reason": "Need one more attempt after the timeout.",
        "next_action": "continue",
        "follow_up_prompt": "Retry with a smaller batch and preserve auth behavior.",
        "confidence": 0.92,
    })
    reasoner = FollowUpReasoner(gateway=gateway)

    decision = reasoner.decide(
        current_task="Fix auth",
        graph=graph,
        workflow_state={"state": "WAITING_FOR_QUOTA", "step": "retry"},
        latest_execution_result={"status": "failed", "output": "Timed out during auth check"},
        git_diff="diff --git a/auth.py b/auth.py\n- token\n+ retry",
        errors=["Timeout"],
        constraints=["Do not remove auth"],
    )

    assert decision.should_continue is True
    assert decision.next_action == "continue"
    assert len(gateway.calls) == 1
    message = gateway.calls[0].messages[0].content
    assert "GOAL" in message
    assert "CURRENT STATE" in message
    assert "RELEVANT FILES" in message
    assert "PREVIOUS DECISIONS" in message
    assert "ERRORS" in message
    assert "CONSTRAINTS" in message
    assert "LATEST OBSERVATION" in message
    assert "chat_history" not in message.lower()


def test_follow_up_reasoner_rejects_invalid_json_before_execution() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix auth", properties={"workspace_id": 2}))
    gateway = FakeGateway({"should_continue": "yes"})
    reasoner = FollowUpReasoner(gateway=gateway)

    try:
        reasoner.validate_response('{"should_continue": "yes"}')
        raise AssertionError("Expected validation to fail")
    except ValueError:
        pass

    try:
        reasoner.decide(
            current_task=task.name,
            graph=graph,
            workflow_state={"state": "READY"},
            latest_execution_result={"status": "ok"},
            git_diff="",
            errors=[],
            constraints=[],
        )
    except ValueError:
        pass
