from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.workspace import Workspace
from app.gateway.schemas import ChatResponse, ProviderStatus
from app.services.first_prompt_scheduler import FirstPromptScheduler


class Gateway:
    def chat(self, request):
        return ChatResponse(content="first result", provider="test", model="test")

    def quota_status(self):
        return ProviderStatus(provider="test", available=True)


def test_scheduler_strategy_controls_autonomous_runner(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'strategy.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    workspace = Workspace(name="Strategy", project_path=str(tmp_path), database_id=1, brain_version="1.0")
    session.add(workspace)
    session.commit()
    runs: list[int] = []
    scheduler = FirstPromptScheduler(
        session,
        gateway=Gateway(),
        autonomous_runner=lambda record: runs.append(record.id),
    )
    prompt = scheduler.schedule_prompt(workspace.id, "First", "test", quota_resume=True, autonomy_enabled=False)
    autonomous = scheduler.schedule_prompt(workspace.id, "First", "test", quota_resume=True, autonomy_enabled=True)
    scheduler.process_due_prompts()

    assert prompt.autonomy_enabled is False
    assert autonomous.autonomy_enabled is True
    assert runs == [autonomous.id]