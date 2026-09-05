from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.gateway.gateway import ModelGateway
from app.scheduler.schemas import SchedulerStateStore, SchedulerStatus
from app.scheduler.service import SchedulerService

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def get_scheduler() -> SchedulerService:
    settings = get_settings()
    return SchedulerService(
        gateway=ModelGateway(settings=settings),
        state_store=SchedulerStateStore(settings.scheduler_state_file),
        poll_interval_seconds=settings.scheduler_poll_interval_seconds,
    )


@router.get("/{task_id}", response_model=SchedulerStatus)
def scheduler_status(task_id: str) -> SchedulerStatus:
    scheduler = get_scheduler()
    state = scheduler.restore_state(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No scheduler state found for task: {task_id}")
    available = None
    if state.last_checked_at is not None:
        available = state.quota_available
    return SchedulerStatus(
        task_id=task_id,
        state=state,
        provider_available=available,
        message=state.last_error,
    )


@router.get("", response_model=list[SchedulerStatus])
def scheduler_statuses() -> list[SchedulerStatus]:
    scheduler = get_scheduler()
    return [
        SchedulerStatus(
            task_id=state.task_id,
            state=state,
            provider_available=state.quota_available,
            message=state.last_error,
        )
        for state in scheduler.state_store.load_all()
    ]
