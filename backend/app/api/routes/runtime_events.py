from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.runtime_event import RuntimeEventCreate, RuntimeEventRead
from app.services.runtime_event_service import RuntimeEventService

router = APIRouter(prefix="/runtime-events", tags=["runtime-events"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=RuntimeEventRead)
def create_runtime_event(event: RuntimeEventCreate, db: Session = Depends(get_db)) -> RuntimeEventRead:
    service = RuntimeEventService(db)
    created = service.record_event(event.event_type, event.source, event.message, event.metadata)
    return RuntimeEventRead(
        id=created.id,
        event_type=created.event_type,
        source=created.source,
        message=created.message,
        metadata=(None if created.metadata_json is None else {"raw": created.metadata_json}),
        created_at=created.created_at,
    )


@router.get("/", response_model=list[RuntimeEventRead])
def list_runtime_events(db: Session = Depends(get_db)) -> list[RuntimeEventRead]:
    service = RuntimeEventService(db)
    events = service.get_recent_events(limit=20)
    return [
        RuntimeEventRead(
            id=event.id,
            event_type=event.event_type,
            source=event.source,
            message=event.message,
            metadata=(None if event.metadata_json is None else {"raw": event.metadata_json}),
            created_at=event.created_at,
        )
        for event in events
    ]
