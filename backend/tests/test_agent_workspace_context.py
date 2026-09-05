from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agent_loop.engine import AgentLoopEngine
from app.schemas.workspace_context import WorkspaceContext


class CapturingGateway:
    def __init__(self) -> None:
        self.requests = []

    def chat(self, request):
        self.requests.append(request)
        return type("Response", (), {
            "content": '{"status":"success","reason":"done","actions":[],"expected_result":"done","confidence":1.0}'
        })()


class NoopSafety:
    def check(self, action):
        return True


class NoopExecutor:
    def execute(self, action):
        return None


def test_agent_plan_includes_workspace_context_by_default() -> None:
    gateway = CapturingGateway()
    engine = AgentLoopEngine(gateway=gateway, safety_engine=NoopSafety(), executor=NoopExecutor())
    context = WorkspaceContext(
        workspace_id=3,
        workspace_name="HouseEats",
        project_path="/tmp/houseeats",
        database_id=8,
        brain_version="1.0",
        current_branch="main",
        modified_files=["app.py"],
        recent_commits=[],
        relevant_graph_nodes=[],
        current_task="Fix menu",
        generated_at=datetime.now(timezone.utc),
    )

    engine._plan("Fix menu", {}, context)

    payload = json.loads(gateway.requests[0].messages[1].content)
    assert payload["workspace_context"]["workspace_name"] == "HouseEats"
    assert payload["workspace_context"]["database_id"] == 8
    assert payload["workspace_context"]["modified_files"] == ["app.py"]
