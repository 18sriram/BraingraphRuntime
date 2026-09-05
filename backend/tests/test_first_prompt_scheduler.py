from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.gateway.schemas import ChatRequest, ChatResponse, ProviderStatus
from app.models.workspace import Workspace
from app.services.first_prompt_scheduler import FirstPromptScheduler


class FakeGateway:
    def __init__(self, response: str = "Decision ready") -> None:
        self.response = response
        self.calls: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        return ChatResponse(content=self.response, provider="openai", model="gpt-4o-mini", finish_reason="stop")

    def quota_status(self) -> ProviderStatus:
        return ProviderStatus(provider="openai", available=True)


def test_first_prompt_scheduler_runs_only_the_first_prompt_and_transitions_to_decision(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    workspace = Workspace(
        name="Demo workspace",
        project_path=str(tmp_path),
        database_id=1,
        brain_version="1.0",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)

    gateway = FakeGateway("I have a decision")
    scheduler = FirstPromptScheduler(session=session, gateway=gateway)

    scheduled = scheduler.schedule_prompt(
        workspace_id=workspace.id,
        first_prompt="Fix the failing tests.",
        provider="openai",
        quota_resume=True,
        autonomy_enabled=False,
    )

    scheduler.process_due_prompts()
    session.refresh(scheduled)

    assert scheduled.status == "DECISION"
    assert scheduled.response == "I have a decision"
    assert len(gateway.calls) == 1
    assert gateway.calls[0].messages[0].content == "Fix the failing tests."
    assert gateway.calls[0].messages[0].role == "user"


def test_first_prompt_scheduler_keeps_future_prompts_pending_until_due_time(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    workspace = Workspace(
        name="Future workspace",
        project_path=str(tmp_path),
        database_id=1,
        brain_version="1.0",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)

    gateway = FakeGateway()
    scheduler = FirstPromptScheduler(session=session, gateway=gateway)

    future = scheduler.schedule_prompt(
        workspace_id=workspace.id,
        first_prompt="Only later.",
        provider="openai",
        scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=5),
        autonomy_enabled=False,
    )

    scheduler.process_due_prompts(now=datetime.now(timezone.utc))
    session.refresh(future)

    assert future.status == "PENDING"
    assert len(gateway.calls) == 0
