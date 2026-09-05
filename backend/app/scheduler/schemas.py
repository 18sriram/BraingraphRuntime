from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.agent_loop.schemas import AgentAction


class SchedulerState(BaseModel):
    task_id: str
    current_task: str
    current_iteration: int = Field(ge=0)
    pending_actions: list[AgentAction] = Field(default_factory=list)
    selected_provider: str
    graph_snapshot_id: str | None = None
    quota_available: bool | None = None
    waiting: bool = False
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    resumed_at: datetime | None = None
    last_error: str | None = None


class SchedulerStatus(BaseModel):
    task_id: str
    state: SchedulerState | None = None
    provider_available: bool | None = None
    message: str | None = None


class SchedulerStateStore:
    """Small JSON state store suitable for local runtime coordination."""

    def __init__(self, path: str = "./scheduler-state.json") -> None:
        from pathlib import Path

        self.path = Path(path)

    def save(self, state: SchedulerState) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        records: dict[str, Any] = {}
        if self.path.exists():
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "task_id" not in existing:
                records = existing
            elif isinstance(existing, dict) and "task_id" in existing:
                records = {existing["task_id"]: existing}
        records[state.task_id] = state.model_dump(mode="json")
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def load(self, task_id: str) -> SchedulerState | None:
        import json

        if not self.path.exists():
            return None
        payload: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        record = payload if payload.get("task_id") == task_id else payload.get(task_id)
        return SchedulerState.model_validate(record) if record else None

    def load_all(self) -> list[SchedulerState]:
        import json

        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = list(payload.values()) if isinstance(payload, dict) and "task_id" not in payload else [payload]
        return [SchedulerState.model_validate(record) for record in records]