from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent_loop.schemas import AgentState
from app.core.database import SessionLocal
from app.schemas.agent_runtime import AgentRuntimeCreate, AgentRuntimeEvent, AgentRuntimeRead
from app.services.agent_runtime import AgentRuntime

router = APIRouter(prefix="/api/agent-runtime", tags=["agent-runtime"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=AgentRuntimeRead, status_code=201)
def create_runtime(payload: AgentRuntimeCreate, db: Session = Depends(get_db)) -> AgentRuntimeRead:
    try:
        record = AgentRuntime(db, payload.task_id).create(payload.objective, payload.workspace_id, payload.autonomous, payload.allow_follow_up_prompts)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AgentRuntimeRead.model_validate(AgentRuntime.as_dict(record))


@router.get("/{task_id}", response_model=AgentRuntimeRead)
def get_runtime(task_id: str, db: Session = Depends(get_db)) -> AgentRuntimeRead:
    record = AgentRuntime(db, task_id).get()
    if record is None:
        raise HTTPException(status_code=404, detail="Agent runtime not found")
    return AgentRuntimeRead.model_validate(AgentRuntime.as_dict(record))


@router.post("/{task_id}/events", response_model=AgentRuntimeRead)
def dispatch_event(task_id: str, payload: AgentRuntimeEvent, db: Session = Depends(get_db)) -> AgentRuntimeRead:
    try:
        record = AgentRuntime(db, task_id).transition(payload.event, payload.payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AgentRuntimeRead.model_validate(AgentRuntime.as_dict(record))