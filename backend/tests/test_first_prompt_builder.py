from __future__ import annotations

import json

import pytest

from app.gateway.schemas import ChatResponse
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate
from app.services.first_prompt_builder import FirstPromptBuilder


class FakeQwen:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def chat(self, request):
        self.prompts.append(request.messages[0].content)
        return ChatResponse(content=json.dumps(self.payload), provider="ollama", model="qwen3:8b-instruct")


def test_first_prompt_builder_expands_objective_and_stores_both_prompts() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix authentication"))
    graph.create_node(GraphNodeCreate(type="File", name="auth.py"))
    provider = FakeQwen({
        "goal": "Fix authentication",
        "current_state": "Authentication is failing in the current workspace.",
        "relevant_files": ["auth.py"],
        "decisions": ["Preserve existing token behavior"],
        "constraints": ["Do not weaken authentication"],
        "expected_output": "A verified authentication flow with passing tests.",
    })
    builder = FirstPromptBuilder(provider, graph=graph)

    result = builder.build(
        objective="Fix authentication.",
        workspace_metadata={"project_path": "/workspace", "language": "Python"},
        current_task="Fix authentication",
        constraints=["Do not weaken authentication"],
        task_id=task.id,
    )

    assert result.objective == "Fix authentication."
    assert result.structured_prompt.relevant_files == ["auth.py"]
    prompts = graph.find_nodes("Prompt", {})
    assert len(prompts) == 2
    assert {node.properties["kind"] for node in prompts} == {"user_objective", "structured_first_prompt"}
    relationships = list(graph._relationships.values())
    assert {relationship.type for relationship in relationships} == {"GENERATED", "LINKED_TO_TASK"}
    assert "Fix authentication." in provider.prompts[0]
    assert "WORKSPACE METADATA" in provider.prompts[0]
    assert "BRAIN GRAPH" in provider.prompts[0]


def test_first_prompt_builder_rejects_invalid_or_executable_structured_prompt() -> None:
    builder = FirstPromptBuilder(FakeQwen({}))
    with pytest.raises(ValueError, match="structured prompt schema"):
        builder.validate_response(json.dumps({"goal": "only goal"}))
    with pytest.raises(ValueError, match="executable"):
        builder.validate_response(json.dumps({
            "goal": "run_command: rm -rf /",
            "current_state": "state",
            "relevant_files": [],
            "decisions": [],
            "constraints": [],
            "expected_output": "result",
        }))
