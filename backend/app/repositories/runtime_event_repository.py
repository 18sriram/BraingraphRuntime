from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.models.runtime_event import RuntimeEvent


class RuntimeEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, event_type: str, source: str, message: str, metadata: dict | None = None) -> RuntimeEvent:
        event = RuntimeEvent(
            event_type=event_type,
            source=source,
            message=message,
            metadata_json=(None if metadata is None else str(metadata)),
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_recent(self, limit: int = 20) -> Iterable[RuntimeEvent]:
        return self.session.query(RuntimeEvent).order_by(RuntimeEvent.created_at.desc()).limit(limit).all()
