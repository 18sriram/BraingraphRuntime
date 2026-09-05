from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_loop.schemas import AgentState
from app.gateway.schemas import ChatMessage, ChatRequest
from app.models.scheduled_prompt import ScheduledPrompt
from app.models.workspace import Workspace
from app.repositories.graph_repository import GraphRepository
from app.services.workspace_context_builder import WorkspaceContextBuilder


class FirstPromptScheduler:
    """Schedule a single first prompt and execute it only when due."""

    def __init__(self, session: Session, gateway: Any, graph: Any | None = None, control_state: Any | None = None, autonomous_runner: Callable[[ScheduledPrompt], None] | None = None) -> None:
        self.session = session
        self.gateway = gateway
        self.graph = graph or GraphRepository()
        self.control_state = control_state
        self.autonomous_runner = autonomous_runner

    def schedule_prompt(
        self,
        workspace_id: int,
        first_prompt: str,
        provider: str,
        scheduled_time: datetime | None = None,
        quota_resume: bool | None = None,
        autonomy_enabled: bool = False,
    ) -> ScheduledPrompt:
        prompt = first_prompt.strip()
        if not prompt:
            raise ValueError("first_prompt cannot be empty")

        if quota_resume is True:
            execute_on_quota = True
            execute_at = None
        elif scheduled_time is not None:
            execute_on_quota = False
            execute_at = scheduled_time
        else:
            execute_on_quota = bool(quota_resume) if quota_resume is not None else True
            execute_at = None

        record = ScheduledPrompt(
            workspace_id=workspace_id,
            provider=provider,
            first_prompt=prompt,
            execute_at=execute_at,
            execute_on_quota=execute_on_quota,
            autonomy_enabled=bool(autonomy_enabled),
            status="PENDING",
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def process_due_prompts(self, now: datetime | None = None) -> list[ScheduledPrompt]:
        current_time = now or datetime.now(timezone.utc)
        due = self.session.execute(
            select(ScheduledPrompt).where(ScheduledPrompt.status == "PENDING").where(
                (ScheduledPrompt.execute_on_quota.is_(True) & ScheduledPrompt.execute_at.is_(None))
                | (ScheduledPrompt.execute_at.is_not(None) & (ScheduledPrompt.execute_at <= current_time))
            )
        ).scalars().all()

        completed: list[ScheduledPrompt] = []
        for record in due:
            if self.control_state is not None and self.control_state() in {"OFF", AgentState.OFF}:
                break
            if record.execute_on_quota:
                status = self.gateway.quota_status()
                if not status.available:
                    continue
            self._execute_due_prompt(record)
            completed.append(record)
        return completed

    def _execute_due_prompt(self, record: ScheduledPrompt) -> None:
        workspace = self._load_workspace(record.workspace_id)
        brain_graph = self._load_brain_graph()
        self._build_context(workspace, brain_graph)

        response = self.gateway.chat(ChatRequest(messages=[ChatMessage(role="user", content=record.first_prompt)]))

        record.response = response.content
        record.status = "DECISION"
        record.updated_at = datetime.utcnow()
        self.session.add(record)
        self.session.commit()

        if record.autonomy_enabled:
            self._continue_autonomy(record)

    def _load_workspace(self, workspace_id: int) -> Workspace:
        workspace = self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")
        return workspace

    def _load_brain_graph(self) -> Any:
        if self.graph is None:
            self.graph = GraphRepository()
        return self.graph

    def _build_context(self, workspace: Workspace, graph: Any) -> Any:
        builder = WorkspaceContextBuilder(self.session, graph)
        return builder.build(workspace.id, current_task=None)

    def _continue_autonomy(self, record: ScheduledPrompt) -> None:
        if not record.autonomy_enabled:
            return
        if self.autonomous_runner is not None:
            self.autonomous_runner(record)
