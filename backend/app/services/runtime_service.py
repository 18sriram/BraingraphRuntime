from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.runtime_record_repository import RuntimeRecordRepository


class RuntimeService:
    """Minimal infrastructure service used to validate the backend wiring.

    This is intentionally not a business logic implementation. It only exposes a
    persistence entry point for runtime metadata and startup diagnostics.
    """

    def __init__(self, session: Session) -> None:
        self.repository = RuntimeRecordRepository(session)

    def record_startup(self, source: str = "bootstrap") -> str:
        record = self.repository.create(
            event_type="startup",
            source=source,
            message="BrainGraph Runtime booted successfully",
        )
        return f"record:{record.id}"
