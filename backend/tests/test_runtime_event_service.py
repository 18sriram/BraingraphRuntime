from app.core.database import Base, SessionLocal, engine
from app.models.runtime_event import RuntimeEvent
from app.services.runtime_event_service import RuntimeEventService


def test_runtime_event_service_records_event() -> None:
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        service = RuntimeEventService(session)
        event = service.record_event(
            event_type="system.started",
            source="bootstrap",
            message="Runtime initialized",
            metadata={"service": "braingraph"},
        )

        assert isinstance(event, RuntimeEvent)
        assert event.event_type == "system.started"
        assert event.message == "Runtime initialized"
        assert event.metadata_json is not None
    finally:
        session.close()
