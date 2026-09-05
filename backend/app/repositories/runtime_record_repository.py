from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.runtime_record import RuntimeRecord


class RuntimeRecordRepository:
    """Repository for storing basic metadata about runtime events.

    The implementation remains intentionally thin so that future business logic can
    be added without changing the persistence contract.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, event_type: str, source: str, message: str) -> RuntimeRecord:
        record = RuntimeRecord(
            event_type=event_type,
            source=source,
            message=message,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
