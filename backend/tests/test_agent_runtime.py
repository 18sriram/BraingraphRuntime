from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.agent_loop.schemas import AgentState
from app.core.database import Base
from app.main import app
from app.services.agent_runtime import AgentRuntime


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_agent_runtime_persists_explicit_transitions(tmp_path) -> None:
    session = make_session(tmp_path)
    try:
        runtime = AgentRuntime(session, "task-1")
        runtime.create("Build feature", workspace_id=1)
        assert runtime.transition("prepare").current_state == AgentState.READY
        assert runtime.transition("send_first_prompt").current_state == AgentState.SENDING_FIRST_PROMPT
        assert AgentRuntime(session, "task-1").get().current_state == AgentState.SENDING_FIRST_PROMPT
        try:
            runtime.transition("memory_updated")
        except ValueError as error:
            assert "not valid" in str(error)
        else:
            raise AssertionError("invalid transitions must be rejected")
    finally:
        session.close()


def test_dashboard_reports_persisted_agent_state(tmp_path, monkeypatch) -> None:
    session = make_session(tmp_path)
    try:
        runtime = AgentRuntime(session, "task-ws")
        runtime.create("Inspect", workspace_id=1)
        runtime.transition("prepare")
        monkeypatch.setattr("app.api.routes.dashboard.SessionLocal", lambda: session)
        with TestClient(app) as client:
            with client.websocket_connect("/ws/dashboard?task_id=task-ws") as websocket:
                event = websocket.receive_json()
    finally:
        session.close()
    assert event["agent_status"] == AgentState.READY.value
