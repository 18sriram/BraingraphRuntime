from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.runtime_event import RuntimeEvent
from app.repositories.runtime_event_repository import RuntimeEventRepository


class RuntimeEventService:
    def __init__(self, session: Session) -> None:
        self.repository = RuntimeEventRepository(session)

    def record_event(self, event_type: str, source: str, message: str, metadata: dict[str, Any] | None = None) -> RuntimeEvent:
        return self.repository.create(
            event_type=event_type,
            source=source,
            message=message,
            metadata=metadata,
        )

    def get_recent_events(self, limit: int = 20) -> Iterable[RuntimeEvent]:
        return self.repository.list_recent(limit=limit)
